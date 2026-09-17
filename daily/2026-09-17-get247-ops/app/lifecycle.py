"""Request lifecycle: receive → match → reserve → approve → execute → close."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from .catalog import get_op, match_catalog, missing_fields
from .models import (
    ApprovalRecord,
    AuditEvent,
    BudgetReserve,
    ChannelEnvelope,
    ConsequenceClass,
    IntakeResponse,
    Job,
    JobState,
    utcnow,
    new_id,
)
from .policy import evaluate, kill_switch_tripped
from .store import STORE, hash_token, issue_approval_token


def _audit(
    *,
    trace_id: str,
    client_id: str | None,
    actor: str,
    action: str,
    outcome: str,
    target: str | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    STORE.append_audit(
        AuditEvent(
            trace_id=trace_id,
            client_id=client_id,
            actor=actor,
            action=action,
            target=target,
            outcome=outcome,
            detail=detail or {},
        )
    )


def _demo_execute(op_id: str, text: str) -> dict[str, Any]:
    """Deterministic stub actions for demo mode. No external side effects."""
    if op_id == "calendar.check_availability":
        return {
            "proof": "availability",
            "slots": ["Tue 10:00", "Tue 14:30", "Wed 09:00"],
            "source": "demo-calendar",
        }
    if op_id.startswith("calendar."):
        return {
            "proof": "calendar_mutation_staged",
            "op": op_id,
            "summary": text[:160],
            "status": "applied-in-demo",
        }
    if op_id == "brief.research":
        return {
            "proof": "brief",
            "title": "Structured brief (demo)",
            "bullets": [
                "Request matched to brief.research catalog op.",
                "Sources would be attached in production research adapter.",
                f"Topic seed: {text[:120]}",
            ],
            "sources": ["demo://approved-source"],
        }
    if op_id == "followup.prepare":
        return {
            "proof": "draft",
            "draft": f"Hi — following up as requested. ({text[:100]})",
            "status": "awaiting_send_approval_in_prod",
        }
    return {"proof": "escalation", "queue": "operator", "reason": text[:160]}


def process_intake(envelope: ChannelEnvelope, *, public_base: str = "http://localhost:8000") -> IntakeResponse:
    trace_id = new_id("tr_")
    job_id = new_id("job_")

    idem = envelope.idempotency_key or envelope.event_id
    if not STORE.mark_idempotent(idem):
        existing = next((j for j in STORE.jobs.values() if j.inbound_text == envelope.text), None)
        if existing:
            return IntakeResponse(
                trace_id=existing.trace_id,
                job_id=existing.job_id,
                state=existing.state,
                matched_op=existing.matched_op,
                consequence=existing.consequence,
                message="Duplicate event ignored (idempotency).",
            )

    now = utcnow()
    job = Job(
        job_id=job_id,
        trace_id=trace_id,
        inbound_text=envelope.text,
        state=JobState.RECEIVED,
        window_opened_at=now,
        window_expires_at=now + timedelta(hours=24),
    )
    STORE.save_job(job)
    _audit(
        trace_id=trace_id,
        client_id=None,
        actor="edge",
        action="receive",
        outcome="ok",
        detail={"channel": envelope.channel, "event_id": envelope.event_id},
    )

    identity = STORE.resolve_identity(envelope.channel, envelope.channel_user_id)
    tenant = STORE.get_tenant(identity.client_id) if identity else None
    job.identity_id = identity.identity_id if identity else None
    job.client_id = identity.client_id if identity else None
    job.updated_at = utcnow()
    STORE.save_job(job)

    if identity is None:
        job.state = JobState.ESCALATED
        job.failure_reason = "Unknown identity. Controlled relink required."
        STORE.save_job(job)
        _audit(
            trace_id=trace_id,
            client_id=None,
            actor="identity",
            action="resolve",
            outcome="unknown",
        )
        return IntakeResponse(
            trace_id=trace_id,
            job_id=job_id,
            state=job.state,
            message="We do not recognize this number yet. A human will send a relink link.",
        )

    op, confidence = match_catalog(envelope.text)
    if op is None or confidence < 0.35:
        job.state = JobState.OUT_OF_CATALOG
        job.updated_at = utcnow()
        STORE.save_job(job)
        _audit(
            trace_id=trace_id,
            client_id=job.client_id,
            actor="catalog",
            action="match",
            outcome="out_of_catalog",
            detail={"confidence": confidence},
        )
        return IntakeResponse(
            trace_id=trace_id,
            job_id=job_id,
            state=job.state,
            message=(
                "That request is outside the Get247 catalog. "
                "I can schedule, reschedule, cancel, research a brief, "
                "prepare a follow-up, or escalate to your named contact."
            ),
        )

    needed = missing_fields(op, envelope.text)
    if needed:
        job.state = JobState.NEEDS_CLARIFICATION
        job.matched_op = op.op_id
        job.consequence = op.consequence
        job.updated_at = utcnow()
        STORE.save_job(job)
        return IntakeResponse(
            trace_id=trace_id,
            job_id=job_id,
            state=job.state,
            matched_op=op.op_id,
            consequence=op.consequence,
            message=f"Matched {op.title}. Need a bit more detail.",
            clarification_needed=needed,
        )

    job.state = JobState.MATCHED
    job.matched_op = op.op_id
    job.consequence = op.consequence
    job.plan = [f"run:{op.op_id}"]
    STORE.save_job(job)
    _audit(
        trace_id=trace_id,
        client_id=job.client_id,
        actor="catalog",
        action="match",
        outcome="matched",
        target=op.op_id,
        detail={"confidence": confidence},
    )

    decision = evaluate(tenant=tenant, identity=identity, op=op)
    if not decision.allowed:
        job.state = JobState.FAILED
        job.failure_reason = decision.reason
        STORE.save_job(job)
        _audit(
            trace_id=trace_id,
            client_id=job.client_id,
            actor="policy",
            action="deny",
            outcome="denied",
            detail={"reason": decision.reason},
        )
        return IntakeResponse(
            trace_id=trace_id,
            job_id=job_id,
            state=job.state,
            matched_op=op.op_id,
            consequence=op.consequence,
            message=decision.reason,
        )

    reserve = BudgetReserve(
        max_cost_usd=max(op.estimated_cost_usd * 3, 0.25),
        max_tool_calls=op.max_tool_calls,
    )
    job.reserve = reserve
    job.state = JobState.RESERVED
    STORE.save_job(job)
    _audit(
        trace_id=trace_id,
        client_id=job.client_id,
        actor="budget",
        action="reserve",
        outcome="ok",
        detail=reserve.model_dump(mode="json"),
    )

    if decision.requires_human or op.consequence == ConsequenceClass.C_HUMAN:
        job.state = JobState.ESCALATED
        job.result = {"queue": "operator", "reason": decision.reason}
        STORE.save_job(job)
        return IntakeResponse(
            trace_id=trace_id,
            job_id=job_id,
            state=job.state,
            matched_op=op.op_id,
            consequence=op.consequence,
            message="Escalated to your named human. They will see the full job context.",
        )

    if decision.requires_approval:
        token = issue_approval_token()
        approval_id = new_id("appr_")
        expires = utcnow() + timedelta(hours=2)
        record = ApprovalRecord(
            approval_id=approval_id,
            token_hash=hash_token(token),
            job_id=job_id,
            action_summary=f"{op.title}: {envelope.text[:180]}",
            destination=identity.phone,
            expires_at=expires,
        )
        STORE.save_approval(record)
        job.approval_id = approval_id
        job.state = JobState.AWAITING_APPROVAL
        STORE.save_job(job)
        _audit(
            trace_id=trace_id,
            client_id=job.client_id,
            actor="approval",
            action="issue",
            outcome="pending",
            target=approval_id,
        )
        url = f"{public_base}/approve/{approval_id}?token={token}"
        return IntakeResponse(
            trace_id=trace_id,
            job_id=job_id,
            state=job.state,
            matched_op=op.op_id,
            consequence=op.consequence,
            message="Approval required. Open the one-time link to authorize the exact action.",
            approval_url=url,
        )

    return _execute_job(job)


def _execute_job(job: Job) -> IntakeResponse:
    assert job.matched_op and job.reserve
    op = get_op(job.matched_op)
    assert op

    job.state = JobState.EXECUTING
    job.updated_at = utcnow()
    STORE.save_job(job)

    # Demo execution: one synthetic tool call + estimated cost.
    job.tool_calls += 1
    job.actual_cost_usd = round(job.actual_cost_usd + op.estimated_cost_usd, 4)
    tripped = kill_switch_tripped(
        actual_cost=job.actual_cost_usd,
        tool_calls=job.tool_calls,
        max_cost=job.reserve.max_cost_usd,
        max_tool_calls=job.reserve.max_tool_calls,
    )
    if tripped:
        job.state = JobState.KILLED
        job.failure_reason = tripped
        STORE.save_job(job)
        _audit(
            trace_id=job.trace_id,
            client_id=job.client_id,
            actor="kill_switch",
            action="stop",
            outcome="killed",
            detail={"reason": tripped},
        )
        return IntakeResponse(
            trace_id=job.trace_id,
            job_id=job.job_id,
            state=job.state,
            matched_op=job.matched_op,
            consequence=job.consequence,
            message=tripped,
        )

    result = _demo_execute(op.op_id, job.inbound_text)
    job.result = result
    job.state = JobState.COMPLETED
    job.updated_at = utcnow()
    STORE.save_job(job)
    if job.client_id:
        STORE.add_spend(job.client_id, job.actual_cost_usd)
    _audit(
        trace_id=job.trace_id,
        client_id=job.client_id,
        actor="action",
        action="execute",
        outcome="completed",
        target=op.op_id,
        detail={"cost_usd": job.actual_cost_usd, "proof": result.get("proof")},
    )
    return IntakeResponse(
        trace_id=job.trace_id,
        job_id=job.job_id,
        state=job.state,
        matched_op=job.matched_op,
        consequence=job.consequence,
        message=f"Done. Proof: {result.get('proof')}.",
    )


def decide_approval(approval_id: str, token: str, decision: str, actor: str = "client") -> IntakeResponse:
    record = STORE.get_approval(approval_id)
    if record is None:
        raise ValueError("Unknown approval.")
    if record.consumed:
        raise ValueError("Approval token already used.")
    if utcnow() > record.expires_at:
        raise ValueError("Approval link expired.")
    if hash_token(token) != record.token_hash:
        raise ValueError("Invalid approval token.")

    record.consumed = True
    record.decided_at = utcnow()
    record.decided_by = actor
    record.decision = decision
    STORE.save_approval(record)

    job = STORE.get_job(record.job_id)
    if job is None:
        raise ValueError("Job missing for approval.")

    _audit(
        trace_id=job.trace_id,
        client_id=job.client_id,
        actor=actor,
        action="approval_decision",
        outcome=decision,
        target=approval_id,
    )

    if decision != "approved":
        job.state = JobState.FAILED
        job.failure_reason = "Client rejected the approval."
        STORE.save_job(job)
        return IntakeResponse(
            trace_id=job.trace_id,
            job_id=job.job_id,
            state=job.state,
            matched_op=job.matched_op,
            consequence=job.consequence,
            message="Canceled. No action was taken.",
        )

    job.state = JobState.APPROVED
    STORE.save_job(job)
    return _execute_job(job)
