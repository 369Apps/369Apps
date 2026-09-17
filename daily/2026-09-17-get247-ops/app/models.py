"""Domain models for the Get247 control plane.

Every job carries a tenant key. The model proposes; policy decides.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str = "") -> str:
    raw = uuid4().hex[:12]
    return f"{prefix}{raw}" if prefix else raw


class ConsequenceClass(str, Enum):
    """Permission follows consequence, not the tool name."""

    A_AUTO = "A"  # read / draft / internal notes
    B_APPROVE = "B"  # create/move appointments, routine send
    C_HUMAN = "C"  # purchases, destructive, sensitive, ambiguous


class JobState(str, Enum):
    RECEIVED = "received"
    MATCHED = "matched"
    NEEDS_CLARIFICATION = "needs_clarification"
    OUT_OF_CATALOG = "out_of_catalog"
    RESERVED = "reserved"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    KILLED = "killed"
    ESCALATED = "escalated"


class IdentityRole(str, Enum):
    OWNER = "owner"
    DELEGATE = "delegate"
    UNKNOWN = "unknown"


class Tenant(BaseModel):
    client_id: str
    name: str
    plan: str = "founding"
    status: str = "active"
    timezone: str = "America/New_York"
    monthly_budget_usd: float = 40.0
    monthly_spend_usd: float = 0.0


class Identity(BaseModel):
    identity_id: str
    client_id: str
    channel: str
    channel_user_id: str
    phone: str | None = None
    role: IdentityRole = IdentityRole.UNKNOWN
    state: str = "active"
    allowed_actions: list[str] = Field(default_factory=list)


class CatalogOp(BaseModel):
    op_id: str
    title: str
    description: str
    consequence: ConsequenceClass
    keywords: list[str]
    required_fields: list[str] = Field(default_factory=list)
    estimated_cost_usd: float = 0.05
    max_tool_calls: int = 8


class ChannelEnvelope(BaseModel):
    """Channel-neutral inbound event. Adapters normalize into this shape."""

    event_id: str = Field(default_factory=lambda: new_id("evt_"))
    channel: str = "whatsapp"
    channel_user_id: str
    phone: str | None = None
    text: str
    media_urls: list[str] = Field(default_factory=list)
    received_at: datetime = Field(default_factory=utcnow)
    idempotency_key: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class BudgetReserve(BaseModel):
    max_cost_usd: float
    max_tool_calls: int
    max_elapsed_sec: int = 120
    reserved_at: datetime = Field(default_factory=utcnow)


class ApprovalRecord(BaseModel):
    approval_id: str
    token_hash: str
    job_id: str
    action_summary: str
    destination: str | None = None
    amount_usd: float | None = None
    expires_at: datetime
    consumed: bool = False
    decided_at: datetime | None = None
    decided_by: str | None = None
    decision: str | None = None  # approved | rejected


class Job(BaseModel):
    job_id: str
    trace_id: str
    client_id: str | None = None
    identity_id: str | None = None
    state: JobState = JobState.RECEIVED
    inbound_text: str
    matched_op: str | None = None
    consequence: ConsequenceClass | None = None
    plan: list[str] = Field(default_factory=list)
    reserve: BudgetReserve | None = None
    actual_cost_usd: float = 0.0
    tool_calls: int = 0
    approval_id: str | None = None
    result: dict[str, Any] | None = None
    failure_reason: str | None = None
    window_opened_at: datetime | None = None
    window_expires_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class AuditEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: new_id("aud_"))
    at: datetime = Field(default_factory=utcnow)
    trace_id: str
    client_id: str | None = None
    actor: str
    action: str
    target: str | None = None
    outcome: str
    detail: dict[str, Any] = Field(default_factory=dict)


class IntakeResponse(BaseModel):
    trace_id: str
    job_id: str
    state: JobState
    matched_op: str | None = None
    consequence: ConsequenceClass | None = None
    message: str
    approval_url: str | None = None
    clarification_needed: list[str] | None = None
