"""Run the Campus Customs agent team over the shop's open tickets.

    .venv/bin/python backend/run_tickets.py              # all open tickets
    .venv/bin/python backend/run_tickets.py --ticket 101 # just one

Every run appends a record to output/audit_trail.json; nothing already in that
file is rewritten.

Payments pause for a human. When the team stages one, this script prints the
request and waits for a person to type an explicit authorization at the
terminal. There is no flag, threshold or policy that can approve a payment
without that — a run with no terminal leaves every payment pending and pays
nothing.

The operator token that makes a decision count is generated here, lives only in
the MCP server's environment, and is never shown to a model, so an agent cannot
approve its own payment even if it tries.
"""

from __future__ import annotations

import argparse
import asyncio
import secrets
import sys
import uuid
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_DIR))

from pydantic_ai.usage import RunUsage  # noqa: E402

from agents import (  # noqa: E402
    LIMITS_SUMMARY,
    MODEL_NAME,
    USAGE_LIMITS,
    TeamDeps,
    build_team,
    build_toolset,
)
from audit import TRAIL_PATH, AuditTrail  # noqa: E402
from models import TicketResolution  # noqa: E402

def _accumulate(totals: dict[str, int], usage: RunUsage) -> None:
    """Fold one ticket's usage into the run totals."""
    totals["requests"] += usage.requests
    totals["input_tokens"] += usage.input_tokens
    totals["output_tokens"] += usage.output_tokens
    totals["total_tokens"] += usage.total_tokens
    totals["tool_calls"] += usage.tool_calls


BOSS_BRIEF = """You are handling ticket {ticket_id} for Campus Customs.

Start by calling get_ticket({ticket_id}) to see the request and the records it
links to. Then delegate to the specialists the ticket actually needs, decide,
make sure the work is recorded through the MCP tools, and set the ticket status
before you finish.

Return a TicketResolution for ticket {ticket_id}."""


# What the operator has to type, exactly. A bare "y" is too easy to hit by
# reflex for a key that moves the shop's money.
AUTHORIZE_PHRASE = "approve"


async def decide_approvals(
    toolset: Any,
    trail: AuditTrail,
    human_token: str,
    ticket_id: int | None,
) -> list[dict[str, Any]]:
    """Put every pending payment in front of a person and record what they decide.

    There is no automatic path through this function. Approval requires a human
    at a terminal typing the authorization phrase for that specific payment,
    having seen its amount, account and reason. Anything else — no terminal, a
    different answer, an empty line, a closed stdin — leaves the payment pending
    and moves no money.
    """
    pending = await toolset.direct_call_tool("list_payment_approvals", {"status": "pending"})
    decisions: list[dict[str, Any]] = []

    for appr in pending.get("approvals", []):
        print(f"\n{'=' * 70}\nPAYMENT APPROVAL NEEDED")
        print(f"  approval id : {appr['id']}")
        print(f"  kind        : {appr['kind']}  (ref {appr['ref_id']})")
        print(f"  amount      : ${appr['amount']:,.2f} from {appr['account']}")
        print(f"  requested by: {appr['requested_by']}")
        print(f"  reason      : {appr['reason']}")
        print("=" * 70)

        if not sys.stdin.isatty():
            print("  -> no human at a terminal; left PENDING. Nothing was paid.")
            trail.log(agent="runner", event="human_decision", ticket_id=ticket_id,
                      detail=f"approval {appr['id']}: left pending, no operator present",
                      data={"approval_id": appr["id"], "decision": "pending",
                            "reason": "no interactive terminal"})
            decisions.append({"approval_id": appr["id"], "decision": "pending"})
            continue

        try:
            answer = input(
                f"  Type {AUTHORIZE_PHRASE!r} to authorize this payment, "
                "anything else to reject: "
            ).strip().lower()
        except EOFError:
            answer = ""
        decision = "approved" if answer == AUTHORIZE_PHRASE else "rejected"
        who = "human operator at the terminal"

        result = await toolset.direct_call_tool(
            "record_human_decision",
            {"approval_id": appr["id"], "decision": decision,
             "decided_by": who, "human_token": human_token},
        )
        print(f"  -> {decision} by {who}")
        trail.log(agent="human operator", event="human_decision", ticket_id=ticket_id,
                  detail=f"approval {appr['id']}: {decision}",
                  data={"approval_id": appr["id"], "decision": decision, "decided_by": who})

        if decision == "approved" and result.get("ok"):
            paid = await toolset.direct_call_tool(
                "record_approved_payment", {"approval_id": appr["id"], "paid_by": who}
            )
            print(f"  -> payment: {paid}")
            trail.log(agent="human operator", event="tool_result", ticket_id=ticket_id,
                      detail="record_approved_payment", data=paid)
            # The Boss stopped at `awaiting_approval` because the decision was
            # not its to make. Now that it has been made, record the payment and
            # put the ticket back to `open` — a cleared payment is one piece of
            # work finishing, not evidence that the rest of the ticket is done.
            # Only the Boss, on a later run, can judge it resolved.
            if paid.get("ok") and appr.get("ticket_id"):
                closed = await toolset.direct_call_tool("update_ticket_status", {
                    "ticket_id": appr["ticket_id"],
                    "status": "open",
                    "resolution_note": (
                        f"Approval {appr['id']} was {decision} by {who}; payment "
                        f"{paid['payment_id']} of ${paid['amount']:,.2f} left "
                        f"{appr['account']} at ${paid['balance_after']:,.2f}. "
                        "Reopened so the team can confirm nothing else is outstanding."
                    ),
                    "updated_by": "runner (post-approval)",
                })
                trail.log(agent="runner", event="tool_result",
                          ticket_id=appr["ticket_id"], detail="update_ticket_status",
                          data=closed)
            decisions.append({"approval_id": appr["id"], "decision": decision, "payment": paid})
        else:
            decisions.append({"approval_id": appr["id"], "decision": decision})

    return decisions


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticket", type=int, action="append",
                        help="Ticket id to handle. Repeatable. Default: every open ticket.")
    args = parser.parse_args()

    run_id = f"run-{uuid.uuid4().hex[:8]}"
    human_token = secrets.token_urlsafe(24)  # never enters a prompt

    trail = AuditTrail(run_id=run_id, model=MODEL_NAME, limits=LIMITS_SUMMARY)
    toolset = build_toolset(trail, human_token)
    boss, _specialists = build_team(toolset)

    # One budget per ticket, not per run: a three-ticket run must not let the
    # first ticket spend the third one's allowance. Run totals are summed
    # separately for the trail.
    run_totals = {"requests": 0, "input_tokens": 0, "output_tokens": 0,
                  "total_tokens": 0, "tool_calls": 0}
    stopped_early, stop_reason = False, None

    async with toolset:
        shop_date = (await toolset.direct_call_tool("get_shop_date", {})).get("date_today")
        trail.record.shop_date = shop_date
        trail.log(agent="runner", event="run_started",
                  detail=f"model={MODEL_NAME} shop_date={shop_date}",
                  data={"limits": LIMITS_SUMMARY})

        if args.ticket:
            ticket_ids = args.ticket
        else:
            open_tickets = await toolset.direct_call_tool("list_open_tickets", {})
            ticket_ids = [t["id"] for t in open_tickets.get("open_tickets", [])]

        print(f"run {run_id} — model {MODEL_NAME} — shop date {shop_date}")
        print(f"tickets: {ticket_ids}\n")
        trail.record.tickets_handled = list(ticket_ids)

        for ticket_id in ticket_ids:
            usage = RunUsage()
            deps = TeamDeps(trail=trail, ticket_id=ticket_id)
            trail.log(agent="boss", event="agent_started", ticket_id=ticket_id,
                      detail=f"handling ticket {ticket_id}")
            try:
                result = await boss.run(
                    BOSS_BRIEF.format(ticket_id=ticket_id),
                    deps=deps,
                    usage=usage,
                    usage_limits=USAGE_LIMITS,
                )
                resolution: TicketResolution = result.output
            except Exception as exc:  # limit hit, gateway error, bad output
                stopped_early, stop_reason = True, f"{type(exc).__name__}: {exc}"
                trail.log(agent="boss", event="error", ticket_id=ticket_id,
                          detail=stop_reason)
                print(f"ticket {ticket_id}: stopped — {stop_reason}")
                _accumulate(run_totals, usage)
                break

            # Fill in what the tools actually recorded, so the resolution
            # reflects the database rather than the model's recollection.
            resolution.delegated_to = list(dict.fromkeys(deps.delegated_to))  # type: ignore[assignment]
            resolution.actions_taken = deps.actions_taken or resolution.actions_taken
            resolution.human_approval_needed = deps.approvals_requested
            resolution.customer_or_vendor_drafts = deps.drafts_written

            trail.record.resolutions.append(resolution)
            trail.log(agent="boss", event="agent_finished", ticket_id=ticket_id,
                      detail=resolution.summary,
                      data=resolution.model_dump(mode="json"),
                      usage={"input_tokens": usage.input_tokens,
                             "output_tokens": usage.output_tokens,
                             "requests": usage.requests})

            print(f"ticket {ticket_id}: {resolution.outcome} — {resolution.summary}")

            await decide_approvals(toolset, trail, human_token, ticket_id)
            _accumulate(run_totals, usage)

        trail.log(agent="runner", event="run_finished",
                  detail=f"{len(trail.record.resolutions)} ticket(s) resolved",
                  usage=dict(run_totals))

    trail.finish(
        total_usage=dict(run_totals),
        stopped_early=stopped_early,
        stop_reason=stop_reason,
    )

    print(f"\nusage: {run_totals['requests']} requests, "
          f"{run_totals['total_tokens']} tokens across {len(ticket_ids)} ticket(s) "
          f"(per-ticket limit {LIMITS_SUMMARY['total_tokens_limit']})")
    print(f"audit trail appended to {TRAIL_PATH.relative_to(BACKEND_DIR.parent)}")
    return 1 if stopped_early else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
