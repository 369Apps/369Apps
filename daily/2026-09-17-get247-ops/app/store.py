"""In-memory demo store. Swap for Postgres without changing call sites."""

from __future__ import annotations

import hashlib
from threading import Lock

from .models import (
    ApprovalRecord,
    AuditEvent,
    Identity,
    IdentityRole,
    Job,
    Tenant,
    new_id,
)


class Store:
    def __init__(self) -> None:
        self._lock = Lock()
        self.tenants: dict[str, Tenant] = {}
        self.identities: dict[str, Identity] = {}
        self.jobs: dict[str, Job] = {}
        self.approvals: dict[str, ApprovalRecord] = {}
        self.audit: list[AuditEvent] = []
        self.seen_idempotency: set[str] = set()
        self._seed()

    def _seed(self) -> None:
        tenant = Tenant(
            client_id="client_demo",
            name="Demo Dental",
            plan="founding",
            monthly_budget_usd=40.0,
        )
        self.tenants[tenant.client_id] = tenant
        identity = Identity(
            identity_id="id_demo_owner",
            client_id=tenant.client_id,
            channel="whatsapp",
            channel_user_id="wa:+15551234567",
            phone="+15551234567",
            role=IdentityRole.OWNER,
            allowed_actions=[
                "calendar.check_availability",
                "calendar.create_event",
                "calendar.move_event",
                "calendar.cancel_event",
                "brief.research",
                "followup.prepare",
                "desk.escalate",
            ],
        )
        self.identities[identity.identity_id] = identity
        # Secondary lookup by channel key.
        self.identities[f"{identity.channel}:{identity.channel_user_id}"] = identity

    def resolve_identity(self, channel: str, channel_user_id: str) -> Identity | None:
        return self.identities.get(f"{channel}:{channel_user_id}")

    def get_tenant(self, client_id: str) -> Tenant | None:
        return self.tenants.get(client_id)

    def save_job(self, job: Job) -> Job:
        with self._lock:
            self.jobs[job.job_id] = job
            return job

    def get_job(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id)

    def save_approval(self, record: ApprovalRecord) -> ApprovalRecord:
        with self._lock:
            self.approvals[record.approval_id] = record
            return record

    def get_approval(self, approval_id: str) -> ApprovalRecord | None:
        return self.approvals.get(approval_id)

    def append_audit(self, event: AuditEvent) -> AuditEvent:
        with self._lock:
            self.audit.append(event)
            return event

    def mark_idempotent(self, key: str) -> bool:
        """Return True if this key is new; False if already seen."""
        with self._lock:
            if key in self.seen_idempotency:
                return False
            self.seen_idempotency.add(key)
            return True

    def add_spend(self, client_id: str, amount: float) -> None:
        tenant = self.tenants.get(client_id)
        if tenant:
            tenant.monthly_spend_usd = round(tenant.monthly_spend_usd + amount, 4)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_approval_token() -> str:
    return new_id("tok_") + new_id()


STORE = Store()
