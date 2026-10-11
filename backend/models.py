"""Shared data types for the Campus Customs agent team.

Everything that crosses a boundary — between an agent and its caller, between
the team and the audit trail — is one of these models. Keeping them in one file
means the Boss and the specialists agree on shape without importing each other.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

AgentName = Literal["boss", "inventory", "accounting", "facilities", "customer_service"]

TicketOutcome = Literal["resolved", "awaiting_approval", "blocked"]


def now_stamp() -> str:
    """Wall-clock timestamp for the audit trail.

    This is the real time the run happened, deliberately distinct from the
    shop's business date in `desk.date_today`, which the agents use for every
    due-date judgment.
    """
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


class SpecialistReport(BaseModel):
    """What a specialist agent hands back to the Boss.

    The Boss reads `findings` to decide what to do next, so a specialist that
    could not establish something says so there rather than guessing.
    """

    agent: AgentName = Field(description="Which specialist produced this report.")
    summary: str = Field(description="One or two sentences: what was found or done.")
    findings: list[str] = Field(
        default_factory=list,
        description="Concrete facts read from the shop database, each with its numbers.",
    )
    actions_taken: list[str] = Field(
        default_factory=list,
        description="Changes actually written through the MCP server, if any.",
    )
    needs_human_approval: bool = Field(
        default=False,
        description="True when the next step is a payment awaiting the operator's decision.",
    )
    blocked_reason: str | None = Field(
        default=None,
        description="Set when the specialist could not finish, explaining what stopped it.",
    )


class TicketResolution(BaseModel):
    """The Boss's final answer on one ticket."""

    ticket_id: int
    outcome: TicketOutcome = Field(
        description=(
            "resolved = the work is recorded and the ticket is closed; "
            "awaiting_approval = everything is staged but a human must decide a payment; "
            "blocked = something outside the agents' authority stopped it."
        )
    )
    summary: str = Field(description="What was decided about this ticket, in plain language.")
    reasoning: str = Field(description="Why, citing the shop figures the decision rests on.")
    delegated_to: list[AgentName] = Field(
        default_factory=list, description="Specialists the Boss consulted, in order."
    )
    actions_taken: list[str] = Field(
        default_factory=list, description="Database changes made through the MCP server."
    )
    human_approval_needed: list[str] = Field(
        default_factory=list, description="Payments staged and waiting on the operator."
    )
    customer_or_vendor_drafts: list[str] = Field(
        default_factory=list,
        description="Messages drafted but deliberately not sent to anyone.",
    )


class AuditStep(BaseModel):
    """One entry in the append-only loop log.

    A step is written for every agent call, every delegation and every tool
    invocation, so the trail reconstructs the run without needing the model.
    """

    run_id: str
    step: int
    at: str = Field(default_factory=now_stamp)
    agent: str
    event: Literal[
        "run_started", "agent_started", "agent_finished", "delegation",
        "tool_call", "tool_result", "approval_requested", "human_decision",
        "limit_reached", "error", "run_finished",
    ]
    ticket_id: int | None = None
    detail: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    usage: dict[str, Any] = Field(default_factory=dict)


class RunRecord(BaseModel):
    """One complete execution of the team, appended to output/audit_trail.json."""

    run_id: str
    started_at: str
    finished_at: str | None = None
    model: str
    shop_date: str | None = None
    limits: dict[str, Any] = Field(default_factory=dict)
    tickets_handled: list[int] = Field(default_factory=list)
    resolutions: list[TicketResolution] = Field(default_factory=list)
    steps: list[AuditStep] = Field(default_factory=list)
    total_usage: dict[str, Any] = Field(default_factory=dict)
    stopped_early: bool = False
    stop_reason: str | None = None
