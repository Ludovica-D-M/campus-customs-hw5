"""The five Campus Customs agents and the wiring that lets them talk.

Boss is the only agent that sees a ticket. It delegates to four specialists by
calling `ask_inventory`, `ask_accounting`, `ask_facilities` and
`ask_customer_service`, each of which runs that specialist as a nested agent
and hands its `SpecialistReport` back.

Every agent reaches the shop only through the MCP server declared in
.mcp.json — no agent opens the database, and no shop fact enters a prompt
except as a tool result. Each specialist sees only the subset of MCP tools its
job needs, so Customer Service cannot move money and Inventory cannot pay an
invoice.

Token and loop budgets are shared across the whole team: the Boss and every
specialist it calls draw from one `RunUsage`, so a chatty specialist spends the
run's budget rather than getting a fresh one.
"""

from __future__ import annotations

import json
import os
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic_ai import Agent, RunContext
from pydantic_ai.mcp import CallToolFunc, MCPToolset, StdioTransport
from pydantic_ai.usage import RunUsage, UsageLimits

from audit import AuditTrail
from config import HW_ROOT, MCP_CONFIG_PATH, MODEL_NAME, build_model
from models import SpecialistReport, TicketResolution

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

# ----------------------------------------------------------------- limits

# One model call is one request. Forty is generous for a three-ticket run and
# low enough that a loop cannot quietly burn the budget.
REQUEST_LIMIT = 40
TOOL_CALLS_LIMIT = 60
TOTAL_TOKENS_LIMIT = 400_000

# Every delegation on a ticket counts against this, whether it came from the
# Boss or from one specialist consulting another. Past this, the delegation
# tools refuse and tell the caller to decide with what it already has, which
# breaks the "ask one more colleague" loop without killing the run.
MAX_DELEGATIONS_PER_TICKET = 10

# How deep a chain of agents may get: boss -> specialist -> peer. A peer is the
# end of the line, so a consultation cannot spawn its own consultation.
MAX_CHAIN_DEPTH = 3

# Specialists consulting each other is capped separately from the Boss's own
# delegations, so a pair of chatty colleagues cannot eat the whole ticket.
MAX_PEER_CONSULTS_PER_TICKET = 5

# A specialist can hand a question back up to the Boss. That is answered by a
# Boss who cannot delegate (see `boss_advisor` below), so escalation is a leaf
# and Boss-and-specialist cannot volley a question between them. The cap is
# here anyway, because a specialist that escalates three times on one ticket is
# stuck rather than thorough.
MAX_BOSS_ESCALATIONS_PER_TICKET = 3

# A specialist is a leaf: it calls tools and reports back. It never delegates.
# This is how many requests a specialist may add on top of whatever the ticket
# has already spent — the budget is shared, so the cap has to be relative.
SPECIALIST_REQUEST_LIMIT = 12

USAGE_LIMITS = UsageLimits(
    request_limit=REQUEST_LIMIT,
    tool_calls_limit=TOOL_CALLS_LIMIT,
    total_tokens_limit=TOTAL_TOKENS_LIMIT,
)

LIMITS_SUMMARY: dict[str, Any] = {
    "request_limit": REQUEST_LIMIT,
    "tool_calls_limit": TOOL_CALLS_LIMIT,
    "total_tokens_limit": TOTAL_TOKENS_LIMIT,
    "max_delegations_per_ticket": MAX_DELEGATIONS_PER_TICKET,
    "max_chain_depth": MAX_CHAIN_DEPTH,
    "max_peer_consults_per_ticket": MAX_PEER_CONSULTS_PER_TICKET,
    "max_boss_escalations_per_ticket": MAX_BOSS_ESCALATIONS_PER_TICKET,
    "cycle_protection": "an agent already in the active chain cannot be consulted again",
    "specialist_request_limit": SPECIALIST_REQUEST_LIMIT,
    "budget_scope": "per ticket, shared by the Boss and every specialist it calls",
}

# ------------------------------------------------------- tool allocations

# Which MCP tools each agent may see. Least privilege: an agent that cannot
# call a tool cannot be argued into misusing it.
READ_CONTEXT = {"get_shop_date", "get_ticket", "list_open_tickets"}

TOOLS_FOR: dict[str, set[str]] = {
    "boss": READ_CONTEXT | {"get_cash_balance", "update_ticket_status",
                            "list_payment_approvals"},
    "inventory": READ_CONTEXT | {"check_item_availability", "list_vendors",
                                 "list_unpaid_invoices", "adjust_inventory"},
    "accounting": READ_CONTEXT | {"get_cash_balance", "list_unpaid_invoices",
                                  "quote_bulk_order", "verify_rent_due",
                                  "request_payment_approval",
                                  "list_payment_approvals",
                                  "record_approved_payment"},
    "facilities": READ_CONTEXT | {"verify_rent_due", "get_cash_balance",
                                  "request_payment_approval",
                                  "list_payment_approvals"},
    "customer_service": READ_CONTEXT | {"check_item_availability", "list_vendors",
                                        "draft_customer_message"},
}

# Never handed to any agent: record_human_decision. It is the operator's tool,
# and it is withheld at the toolset level as well as by its token check.


ESCALATION_ADDENDUM = """## You are answering an escalation

One of your specialists has handed a question back up to you because it is
above their authority. You are not running the whole ticket right now — you are
answering this one question.

Give a decision, not a referral. You cannot delegate from here: there are no
`ask_*` tools on this run, deliberately, so that an escalation ends in an
answer instead of bouncing back to the agent that raised it. Use your own tools
if you need to see the ticket or the shop's cash position.

Be direct about the trade-off. If the shop cannot afford both things, say which
one gives way and why. If you genuinely cannot decide without something nobody
has, say exactly what is missing.

Return a `SpecialistReport` with `agent="boss"`: your decision in `summary`,
the figures it rests on in `findings`, and `blocked_reason` only if the
question truly cannot be answered."""


def load_prompt(name: str) -> str:
    """Read an agent's prompt and append the house rules every agent shares."""
    body = (PROMPTS_DIR / f"{name}.md").read_text()
    rules = (PROMPTS_DIR / "_shop_rules.md").read_text()
    return f"{body}\n\n---\n\n{rules}"


# -------------------------------------------------------------- the team


class DelegationRefused(str):
    """A refusal message. Truthy, so `if refusal:` reads naturally."""


def check_delegation(
    chain: tuple[str, ...],
    caller: str,
    who: str,
    known: set[str],
    delegations: int,
    peer_consults: int,
    peer: bool,
    escalations: int = 0,
    escalation: bool = False,
) -> DelegationRefused | None:
    """Decide whether one agent may delegate to another.

    Pure and side-effect free, so the loop protections can be tested exhaustively
    without spending a model call. Returns the refusal text, or None to allow.

    The four brakes, in the order they apply:

    * unknown agent, or an agent delegating to itself;
    * the target is already in the active chain — consulting it would loop;
    * the chain has reached its maximum depth;
    * the ticket's delegation or peer-consult budget is spent.
    """
    if escalation:
        # Escalation deliberately skips the cycle check: the Boss sits at the
        # root of every chain, so "already in the chain" would make the Boss the
        # one colleague nobody could ever ask. What makes that safe is that the
        # escalation is answered by a Boss with no delegation tools, so it
        # cannot come back down and start the volley again.
        if len(chain) >= MAX_CHAIN_DEPTH:
            return DelegationRefused(
                f"Refused: the chain {' -> '.join(chain)} is already "
                f"{MAX_CHAIN_DEPTH} deep. Report back up instead of escalating from here."
            )
        if escalations >= MAX_BOSS_ESCALATIONS_PER_TICKET:
            return DelegationRefused(
                f"Refused: this ticket has already been escalated to the Boss "
                f"{MAX_BOSS_ESCALATIONS_PER_TICKET} times. Say what you could not "
                "establish and let the Boss decide with that."
            )
        if delegations >= MAX_DELEGATIONS_PER_TICKET:
            return DelegationRefused(
                f"Refused: this ticket has already used all {MAX_DELEGATIONS_PER_TICKET} "
                "delegations. Report what you have."
            )
        return None

    if who not in known:
        return DelegationRefused(
            f"There is no agent called {who!r}. Choose one of: {', '.join(sorted(known))}."
        )
    if who == caller:
        return DelegationRefused("An agent cannot delegate to itself.")
    if who in chain:
        return DelegationRefused(
            f"Refused: {who} is already working above you in this chain "
            f"({' -> '.join(chain)}), so consulting it would loop. Answer with what you "
            "have, or report what you still need and let the Boss decide."
        )
    if len(chain) >= MAX_CHAIN_DEPTH:
        return DelegationRefused(
            f"Refused: the chain {' -> '.join(chain)} is already {MAX_CHAIN_DEPTH} deep. "
            "A consultation cannot start its own consultation — report back instead."
        )
    if delegations >= MAX_DELEGATIONS_PER_TICKET:
        return DelegationRefused(
            f"Refused: this ticket has already used all {MAX_DELEGATIONS_PER_TICKET} "
            "delegations. Decide with the information you already have."
        )
    if peer and peer_consults >= MAX_PEER_CONSULTS_PER_TICKET:
        return DelegationRefused(
            f"Refused: specialists have already consulted each other "
            f"{MAX_PEER_CONSULTS_PER_TICKET} times on this ticket. Report what you still "
            "need and let the Boss decide."
        )
    return None


# The chain of agents currently above this call, e.g. ("boss", "inventory").
# A ContextVar rather than a field on TeamDeps because the Boss can delegate to
# two specialists concurrently: asyncio copies the context into each task, so
# each branch gets its own chain instead of trampling a shared one.
CHAIN: ContextVar[tuple[str, ...]] = ContextVar("agent_chain", default=("boss",))


@dataclass
class TeamDeps:
    """Shared state for one ticket, passed to every agent in the team."""

    trail: AuditTrail
    ticket_id: int | None = None
    delegations: int = 0
    peer_consults: int = 0
    escalations: int = 0
    delegated_to: list[str] = field(default_factory=list)
    actions_taken: list[str] = field(default_factory=list)
    approvals_requested: list[str] = field(default_factory=list)
    drafts_written: list[str] = field(default_factory=list)


def build_toolset(trail: AuditTrail, human_token: str) -> MCPToolset:
    """Start the MCP server exactly as .mcp.json describes it.

    One subprocess serves the whole team. The operator token is placed in the
    server's environment so `record_human_decision` can verify it, and is never
    passed to an agent or written into a prompt.
    """
    config = json.loads(Path(MCP_CONFIG_PATH).read_text())["mcpServers"]["campus-customs-ops"]

    def resolve(path: str) -> str:
        """Make a path from .mcp.json absolute, relative to the HW5 folder.

        The config stores relative paths so the repository is portable and
        carries no one's home directory. Resolving here, against the project
        root rather than the current working directory, means the server starts
        the same way whoever launches it and from wherever.

        `abspath`, not `Path.resolve()`: resolve() follows symlinks, and
        `.venv/bin/python` is a symlink to the system interpreter — which does
        not have this project's dependencies installed.
        """
        p = Path(path)
        return str(p if p.is_absolute() else Path(os.path.abspath(HW_ROOT / p)))

    async def process_tool_call(
        ctx: RunContext[TeamDeps], call_tool: CallToolFunc, name: str, args: dict[str, Any]
    ) -> Any:
        """Log every MCP call and its result to the audit trail."""
        deps = ctx.deps
        # Take the caller's identity from the run context, not from shared
        # state: the Boss can delegate to two specialists concurrently, and a
        # mutable "current agent" field would attribute their tool calls to
        # whichever one happened to run last.
        who = getattr(ctx.agent, "name", None) or "unknown"
        safe_args = {k: v for k, v in args.items() if k != "human_token"}
        deps.trail.log(
            agent=who, event="tool_call", detail=name,
            ticket_id=deps.ticket_id, data={"tool": name, "arguments": safe_args},
        )
        result = await call_tool(name, args)
        summary = result if isinstance(result, dict) else {"result": str(result)[:600]}
        deps.trail.log(
            agent=who, event="tool_result", detail=name,
            ticket_id=deps.ticket_id, data={"tool": name, "result": summary},
        )
        if isinstance(result, dict) and result.get("ok"):
            if name == "request_payment_approval":
                deps.approvals_requested.append(
                    f"approval {result.get('approval_id')} — ${args.get('amount')} "
                    f"{args.get('kind')} (pending human decision)"
                )
                deps.trail.log(
                    agent=who, event="approval_requested",
                    ticket_id=deps.ticket_id, detail=f"approval {result.get('approval_id')}",
                    data=result,
                )
            elif name == "draft_customer_message":
                deps.drafts_written.append(
                    f"draft {result.get('draft_id')} to {args.get('recipient')} "
                    f"({args.get('audience')}, not sent)"
                )
            elif name in {"adjust_inventory", "update_ticket_status",
                          "record_approved_payment"}:
                deps.actions_taken.append(f"{name}({safe_args}) -> ok")
        return result

    transport = StdioTransport(
        command=resolve(config["command"]),
        args=[resolve(a) for a in (config.get("args") or [])],
        env={"CAMPUS_CUSTOMS_HUMAN_TOKEN": human_token, "PATH": "/usr/bin:/bin"},
        cwd=resolve(config.get("cwd") or "."),
    )
    return MCPToolset(transport, id="campus-customs-ops", process_tool_call=process_tool_call)


def _tools_for(toolset: MCPToolset, agent_name: str) -> Any:
    """Give one agent only the MCP tools its role needs."""
    allowed = TOOLS_FOR[agent_name]
    return toolset.filtered(lambda ctx, tool_def: tool_def.name in allowed)


def build_specialist(name: str, toolset: MCPToolset, model: Any) -> Agent[TeamDeps, SpecialistReport]:
    """Build one specialist agent with its own prompt and tool subset."""
    return Agent(
        model,
        deps_type=TeamDeps,
        output_type=SpecialistReport,
        instructions=load_prompt(name),
        toolsets=[_tools_for(toolset, name)],
        name=name,
        retries=2,
    )


def build_team(toolset: MCPToolset) -> tuple[Agent[TeamDeps, TicketResolution], dict[str, Agent]]:
    """Build the Boss and its four specialists, all sharing one model and server."""
    model = build_model()

    specialists = {
        n: build_specialist(n, toolset, model)
        for n in ("inventory", "accounting", "facilities", "customer_service")
    }

    boss = Agent(
        model,
        deps_type=TeamDeps,
        output_type=TicketResolution,
        instructions=load_prompt("boss"),
        toolsets=[_tools_for(toolset, "boss")],
        name="boss",
        retries=2,
    )

    # The Boss, reachable from below. Same prompt and the same view of the shop,
    # but no delegation tools at all — which is what stops an escalation from
    # turning into a volley: the Boss cannot answer "ask Inventory" by actually
    # asking Inventory, which would be the agent that just escalated.
    boss_advisor = Agent(
        model,
        deps_type=TeamDeps,
        output_type=SpecialistReport,
        instructions=load_prompt("boss") + "\n\n---\n\n" + ESCALATION_ADDENDUM,
        toolsets=[_tools_for(toolset, "boss")],
        name="boss",
        retries=2,
    )

    def _refusal(who: str, reason: str) -> SpecialistReport:
        return SpecialistReport(
            agent=who if who in specialists else "boss",  # type: ignore[arg-type]
            summary="Delegation refused.",
            blocked_reason=reason,
        )

    async def delegate(
        ctx: RunContext[TeamDeps], who: str, instruction: str, *, peer: bool = False
    ) -> SpecialistReport:
        """Run one agent on behalf of another, sharing the ticket's budget.

        Four separate brakes apply, each refusing with an explanation the caller
        can act on rather than raising and ending the run:

        * the agent is unknown;
        * it is already in the active chain, so consulting it would be a cycle;
        * the chain is already at its maximum depth;
        * the ticket's delegation or peer-consult budget is spent.
        """
        deps = ctx.deps
        caller = getattr(ctx.agent, "name", None) or "boss"
        chain = CHAIN.get()
        escalation = who == "boss"

        refusal = check_delegation(
            chain=chain, caller=caller, who=who, known=set(specialists),
            delegations=deps.delegations, peer_consults=deps.peer_consults, peer=peer,
            escalations=deps.escalations, escalation=escalation,
        )
        if refusal:
            deps.trail.log(agent=caller, event="limit_reached", ticket_id=deps.ticket_id,
                           detail=f"{caller} -> {who} refused",
                           data={"chain": list(chain), "peer": peer, "reason": str(refusal)})
            return _refusal(who if who in specialists else caller, str(refusal))

        deps.delegations += 1
        if peer:
            deps.peer_consults += 1
        if escalation:
            deps.escalations += 1
        deps.delegated_to.append(who)
        kind = "escalation" if escalation else ("peer" if peer else "delegation")
        deps.trail.log(
            agent=caller, event="delegation", ticket_id=deps.ticket_id,
            detail=f"{caller} -> {who} ({kind})",
            data={"instruction": instruction, "chain": list(chain),
                  "peer": peer, "escalation": escalation},
        )

        callee = boss_advisor if escalation else specialists[who]
        token = CHAIN.set(chain + (who if not escalation else "boss_advisor",))
        try:
            result = await callee.run(
                instruction,
                deps=deps,
                usage=ctx.usage,  # one shared budget for the whole ticket
                # The limits below are checked against the shared usage object,
                # which already carries what the Boss spent. So the specialist's
                # allowance is expressed relative to that, not from zero —
                # otherwise the second specialist on a ticket starts over the
                # line before it has made a single call.
                usage_limits=UsageLimits(
                    request_limit=ctx.usage.requests + SPECIALIST_REQUEST_LIMIT,
                    tool_calls_limit=TOOL_CALLS_LIMIT,
                    total_tokens_limit=TOTAL_TOKENS_LIMIT,
                ),
            )
        finally:
            CHAIN.reset(token)

        deps.trail.log(
            agent=who, event="agent_finished", ticket_id=deps.ticket_id,
            detail=result.output.summary,
            data=result.output.model_dump(mode="json"),
            usage={"input_tokens": ctx.usage.input_tokens,
                   "output_tokens": ctx.usage.output_tokens,
                   "requests": ctx.usage.requests},
        )
        return result.output

    for _name, _agent in specialists.items():
        @_agent.tool
        async def escalate_to_boss(
            ctx: RunContext[TeamDeps], question: str, why_you_cannot_decide: str
        ) -> SpecialistReport:
            """Hand a question back up to the Boss when it is above your authority.

            Use this when finishing your task needs a judgement that is not yours
            to make — whether to spend the shop's cash on this ticket rather than
            another, whether to accept a worse outcome here to protect something
            else, or which of two defensible options the shop should take.

            Do not use it to avoid work you can do, and do not use it to ask the
            Boss to look something up: you have your own tools for facts.

            The Boss answers directly and cannot delegate the question back down,
            so what you get is a decision, not another round of questions.

            Args:
                question: The decision you need, stated so it can be answered.
                why_you_cannot_decide: What makes this the Boss's call, in a sentence.
            """
            return await delegate(
                ctx, "boss", f"{question}\n\nWhy this is being escalated: "
                             f"{why_you_cannot_decide}",
            )

    # Specialists can go straight to a colleague instead of routing every
    # question back through the Boss. The guards above are what make that safe.
    for _name, _agent in specialists.items():
        @_agent.tool
        async def consult_colleague(
            ctx: RunContext[TeamDeps], colleague: str, question: str
        ) -> SpecialistReport:
            """Ask another specialist a question directly, without going via the Boss.

            Use this when answering your own task needs something that is
            genuinely another specialist's to know — Inventory asking Accounting
            whether a reprint is affordable, Customer Service asking Inventory to
            confirm a date before putting it in writing.

            Do not use it to hand off your own job, and do not consult someone who
            is already waiting on you: that is refused as a loop.

            Args:
                colleague: One of "inventory", "accounting", "facilities",
                    "customer_service".
                question: A specific question, naming the ticket and the figures
                    you need.
            """
            return await delegate(ctx, colleague, question, peer=True)

    @boss.tool
    async def ask_inventory(ctx: RunContext[TeamDeps], instruction: str) -> SpecialistReport:
        """Ask the Inventory agent about stock, shortfalls, reprints or lead times.

        Give it a specific instruction naming the ticket, sku, size and
        quantity. It can also adjust stock when you have decided to move units.
        """
        return await delegate(ctx, "inventory", instruction)

    @boss.tool
    async def ask_accounting(ctx: RunContext[TeamDeps], instruction: str) -> SpecialistReport:
        """Ask the Accounting agent about cash, invoices, margins or staging a payment.

        It can stage a payment for the human operator but cannot approve one.
        """
        return await delegate(ctx, "accounting", instruction)

    @boss.tool
    async def ask_facilities(ctx: RunContext[TeamDeps], instruction: str) -> SpecialistReport:
        """Ask the Facilities agent about the lease, rent amounts or rent dates.

        Use it to verify a rent demand against the lease before any money moves.
        """
        return await delegate(ctx, "facilities", instruction)

    @boss.tool
    async def ask_customer_service(
        ctx: RunContext[TeamDeps], instruction: str
    ) -> SpecialistReport:
        """Ask Customer Service to draft the reply to whoever raised the ticket.

        Drafts are stored for a human to send. Nothing is ever transmitted.
        """
        return await delegate(ctx, "customer_service", instruction)

    return boss, specialists


__all__ = [
    "LIMITS_SUMMARY",
    "MODEL_NAME",
    "TeamDeps",
    "USAGE_LIMITS",
    "build_team",
    "build_toolset",
    "RunUsage",
]
