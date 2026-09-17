"""Deterministic policy engine.

The model proposes a plan. Policy, approval, and budget decide whether it may run.
"""

from __future__ import annotations

from dataclasses import dataclass

from .catalog import CatalogOp
from .models import ConsequenceClass, Identity, IdentityRole, Tenant


@dataclass
class PolicyDecision:
    allowed: bool
    reason: str
    requires_approval: bool = False
    requires_human: bool = False


def evaluate(
    *,
    tenant: Tenant | None,
    identity: Identity | None,
    op: CatalogOp,
) -> PolicyDecision:
    if tenant is None or tenant.status != "active":
        return PolicyDecision(False, "No active tenant for this identity.")

    if identity is None or identity.role == IdentityRole.UNKNOWN:
        return PolicyDecision(
            False,
            "Identity has zero authority. Relink through a trusted channel.",
        )

    if identity.state != "active":
        return PolicyDecision(False, f"Identity state is {identity.state}.")

    if op.op_id not in identity.allowed_actions:
        return PolicyDecision(False, f"Identity is not permitted to run {op.op_id}.")

    remaining = tenant.monthly_budget_usd - tenant.monthly_spend_usd
    if remaining < op.estimated_cost_usd:
        return PolicyDecision(
            False,
            f"Monthly budget exhausted ({remaining:.2f} USD remaining).",
        )

    if op.consequence == ConsequenceClass.C_HUMAN:
        return PolicyDecision(
            True,
            "Consequence class C: named human must control this action.",
            requires_human=True,
        )

    if op.consequence == ConsequenceClass.B_APPROVE:
        return PolicyDecision(
            True,
            "Consequence class B: one-time approval link required.",
            requires_approval=True,
        )

    return PolicyDecision(True, "Consequence class A: auto-run permitted.")


def kill_switch_tripped(
    *,
    actual_cost: float,
    tool_calls: int,
    max_cost: float,
    max_tool_calls: int,
) -> str | None:
    if actual_cost > max_cost:
        return f"Cost kill-switch: {actual_cost:.4f} > reserved {max_cost:.4f}"
    if tool_calls > max_tool_calls:
        return f"Call kill-switch: {tool_calls} > reserved {max_tool_calls}"
    return None
