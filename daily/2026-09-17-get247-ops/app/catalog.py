"""Bounded service catalog.

The catalog is the product. Natural language is only the interface.
"""

from __future__ import annotations

import re

from .models import CatalogOp, ConsequenceClass

# Month-1 ship list from the Get247 system blueprint (v1.1, Sept 2026).
CATALOG: list[CatalogOp] = [
    CatalogOp(
        op_id="calendar.check_availability",
        title="Check calendar availability",
        description="Read free/busy for a date range on the client's connected calendar.",
        consequence=ConsequenceClass.A_AUTO,
        keywords=["available", "availability", "free", "busy", "open slots", "when can"],
        required_fields=["date_hint"],
        estimated_cost_usd=0.02,
        max_tool_calls=3,
    ),
    CatalogOp(
        op_id="calendar.create_event",
        title="Create or book appointment",
        description="Create a calendar event with named attendees and time.",
        consequence=ConsequenceClass.B_APPROVE,
        keywords=["book", "schedule", "set up a meeting", "create event", "add to calendar"],
        required_fields=["when", "title"],
        estimated_cost_usd=0.05,
        max_tool_calls=5,
    ),
    CatalogOp(
        op_id="calendar.move_event",
        title="Move or reschedule appointment",
        description="Move an existing event to a new time.",
        consequence=ConsequenceClass.B_APPROVE,
        keywords=["reschedule", "move", "push back", "change time", "postpone"],
        required_fields=["event_hint", "new_when"],
        estimated_cost_usd=0.05,
        max_tool_calls=5,
    ),
    CatalogOp(
        op_id="calendar.cancel_event",
        title="Cancel appointment",
        description="Cancel an existing calendar event and notify attendees if configured.",
        consequence=ConsequenceClass.B_APPROVE,
        keywords=["cancel", "call off", "remove meeting"],
        required_fields=["event_hint"],
        estimated_cost_usd=0.04,
        max_tool_calls=4,
    ),
    CatalogOp(
        op_id="brief.research",
        title="Research and deliver a structured brief",
        description="Research an approved topic and return a structured brief with sources.",
        consequence=ConsequenceClass.A_AUTO,
        keywords=["brief", "research", "summarize", "look up", "prep me", "what should i know"],
        required_fields=["topic"],
        estimated_cost_usd=0.15,
        max_tool_calls=10,
    ),
    CatalogOp(
        op_id="followup.prepare",
        title="Capture request and prepare approved follow-up",
        description="Draft a follow-up message for human approval before send.",
        consequence=ConsequenceClass.B_APPROVE,
        keywords=["follow up", "draft a reply", "prepare a message", "remind them"],
        required_fields=["recipient_hint", "intent"],
        estimated_cost_usd=0.06,
        max_tool_calls=4,
    ),
    CatalogOp(
        op_id="desk.escalate",
        title="Escalate to named human",
        description="Route an exception to the operator queue with context and deadline.",
        consequence=ConsequenceClass.C_HUMAN,
        keywords=["escalate", "talk to a human", "need bobby", "urgent exception"],
        required_fields=["reason"],
        estimated_cost_usd=0.01,
        max_tool_calls=1,
    ),
]


def get_op(op_id: str) -> CatalogOp | None:
    for op in CATALOG:
        if op.op_id == op_id:
            return op
    return None


def match_catalog(text: str) -> tuple[CatalogOp | None, float]:
    """Keyword matcher for demo mode. Replace with LLM classifier later.

    Returns (op, confidence). Confidence < 0.35 means clarify or escalate.
    """
    lowered = text.lower().strip()
    best: CatalogOp | None = None
    best_score = 0.0

    for op in CATALOG:
        hits = [kw for kw in op.keywords if kw in lowered]
        if not hits:
            continue
        # One solid keyword is enough to enter the catalog; more hits raise confidence.
        score = 0.45 + 0.12 * min(len(hits), 4)
        # Prefer longer keyword matches (more specific phrases).
        score += 0.02 * max(len(kw) for kw in hits)
        if score > best_score:
            best = op
            best_score = score

    # Light regex boosts for common patterns.
    if re.search(r"\b(book|schedule)\b.{0,40}\b(meeting|call|appt|appointment)\b", lowered):
        create = get_op("calendar.create_event")
        if create and best_score < 0.75:
            return create, 0.85

    if re.search(r"\b(available|availability|free slots|am i free)\b", lowered):
        check = get_op("calendar.check_availability")
        if check:
            return check, max(best_score, 0.8)

    return best, min(best_score, 0.99)


def missing_fields(op: CatalogOp, text: str) -> list[str]:
    """Naive required-field probe for demo clarification."""
    lowered = text.lower()
    missing: list[str] = []
    for field in op.required_fields:
        if field in {"date_hint", "when", "new_when"}:
            if not re.search(
                r"\b(today|tomorrow|monday|tuesday|wednesday|thursday|friday|"
                r"saturday|sunday|\d{1,2}/\d{1,2}|\d{1,2}:\d{2}|am|pm)\b",
                lowered,
            ):
                missing.append(field)
        elif field == "title" and len(text.split()) < 4:
            missing.append(field)
        elif field == "topic" and len(text.split()) < 3:
            missing.append(field)
        elif field in {"event_hint", "recipient_hint", "intent", "reason"}:
            if len(text.split()) < 3:
                missing.append(field)
    return missing
