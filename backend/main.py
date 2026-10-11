"""FastAPI backend for the Campus Customs dashboard.

Start it from this folder:

    uvicorn main:app --reload --port 8000

The dashboard never touches the database, the agents, or the model. Everything
it can see or do goes through the MCP server built in Problem 3, which is where
the shop's rules are enforced:

  * agents stage payments, they never make them;
  * approving one requires the operator token this process holds and never
    hands to a model — a dashboard click is what supplies the human;
  * cash cannot go negative, checked when a payment is staged and again when it
    is settled;
  * nothing is ever sent to a customer or vendor.

The one thing that does not go through MCP is the reset, which replaces the
working database file wholesale. That is deliberate: a reset tool on the MCP
server would be a wipe button sitting next to the agents. Here it lives behind
an HTTP route the agents cannot call, and it only ever copies the pristine
original onto the working copy — never the other way round.
"""

from __future__ import annotations

import asyncio
import json
import secrets
import shutil
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

BACKEND_DIR = Path(__file__).resolve().parent
HW_ROOT = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402
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

ORIGINAL_DB = HW_ROOT / "data" / "campus_customs.db"
WORKING_DB = HW_ROOT / "data" / "campus_customs_new.db"

# Generated once per process, placed only in the MCP server's environment.
# No route returns it and no prompt contains it, so the only way an approval
# can carry it is for a person to have clicked Approve in the dashboard.
OPERATOR_TOKEN = secrets.token_urlsafe(24)

BOSS_BRIEF = """You are handling ticket {ticket_id} for Campus Customs.

Start by calling get_ticket({ticket_id}) to see the request and the records it
links to. Then delegate to the specialists the ticket actually needs, decide,
make sure the work is recorded through the MCP tools, and set the ticket status
before you finish.

Return a TicketResolution for ticket {ticket_id}."""

# In-memory record of runs started this process. Runs are executed in the
# background so a browser request does not sit open for the length of a run.
RUNS: dict[str, dict[str, Any]] = {}


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


@asynccontextmanager
async def ops_session():
    """One short-lived MCP connection, started exactly as .mcp.json describes.

    A fresh stdio subprocess per request keeps the dashboard stateless and
    means a crashed server cannot wedge the whole app.
    """
    trail = AuditTrail(run_id=f"api-{uuid.uuid4().hex[:6]}", model=MODEL_NAME,
                       limits=LIMITS_SUMMARY)
    toolset = build_toolset(trail, OPERATOR_TOKEN)
    async with toolset:
        yield toolset, trail
    trail.finish()


async def call_tool(name: str, args: dict[str, Any] | None = None) -> Any:
    async with ops_session() as (toolset, _trail):
        return await toolset.direct_call_tool(name, args or {})


app = FastAPI(
    title="Campus Customs Operations API",
    description=__doc__,
    version="1.0.0",
)

# The dashboard will be served by Vite on another port during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173",
                   "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ------------------------------------------------------------------ models


class RunRequest(BaseModel):
    ticket_ids: list[int] = Field(
        default_factory=list,
        description="Tickets to work. Empty means every open ticket.",
    )


class ApprovalDecision(BaseModel):
    """A human's decision on a staged payment.

    `authorized_by` is who is accountable for it. The MCP server rejects agent
    names here even when the token is valid, so this cannot be a model's answer
    dressed up as a person's.
    """

    decision: Literal["approve", "reject"]
    authorized_by: str = Field(
        min_length=2,
        description="The person clicking Approve. Recorded against the payment.",
    )


# ------------------------------------------------------------------ routes


@app.get("/api/health", summary="Liveness check and which database is in use")
async def health() -> dict[str, Any]:
    return {
        "ok": True,
        "model": MODEL_NAME,
        "working_db": str(WORKING_DB.relative_to(HW_ROOT)),
        "original_db_is_read_only_reference": True,
        "limits": LIMITS_SUMMARY,
        "at": now(),
    }


@app.get("/api/tickets", summary="The three tickets and their current status")
async def get_tickets(status: str | None = None) -> dict[str, Any]:
    """Every ticket on the board, optionally filtered to one status."""
    return await call_tool("list_tickets", {"status": status} if status else {})


@app.get("/api/tickets/{ticket_id}", summary="One ticket with its linked records")
async def get_one_ticket(ticket_id: int) -> dict[str, Any]:
    result = await call_tool("get_ticket", {"ticket_id": ticket_id})
    if not result.get("found"):
        raise HTTPException(404, result.get("message", "No such ticket."))
    return result


@app.get("/api/cash", summary="Cash balance, what is committed against it, and what is free")
async def get_cash() -> dict[str, Any]:
    return await call_tool("get_cash_balance", {})


@app.post("/api/runs", status_code=202, summary="Run the agent team on selected tickets")
async def start_run(req: RunRequest) -> dict[str, Any]:
    """Start a run in the background and return its id immediately.

    A run can take minutes, so the browser polls `/api/runs/{run_id}` rather
    than holding a request open. Payments staged during the run are left
    `pending` — this route cannot approve anything.
    """
    ticket_ids = req.ticket_ids
    if not ticket_ids:
        listed = await call_tool("list_open_tickets", {})
        ticket_ids = [t["id"] for t in listed.get("open_tickets", [])]
    if not ticket_ids:
        raise HTTPException(400, "No open tickets to run.")

    run_id = f"run-{uuid.uuid4().hex[:8]}"
    RUNS[run_id] = {
        "run_id": run_id,
        "status": "running",
        "ticket_ids": ticket_ids,
        "started_at": now(),
        "finished_at": None,
        "resolutions": [],
        "usage": {},
        "error": None,
    }
    asyncio.create_task(_execute_run(run_id, ticket_ids))
    return {"run_id": run_id, "status": "running", "ticket_ids": ticket_ids,
            "poll": f"/api/runs/{run_id}"}


@app.get("/api/runs/{run_id}", summary="Status and results of one run")
async def get_run(run_id: str) -> dict[str, Any]:
    run = RUNS.get(run_id)
    if run is None:
        raise HTTPException(404, f"No run {run_id} in this process.")
    return run


@app.get("/api/runs", summary="Runs started since the server booted")
async def list_runs() -> dict[str, Any]:
    return {"runs": list(RUNS.values())}


@app.get("/api/activity", summary="Recent agent activity: messages, delegations and tool calls")
async def get_activity(
    limit: int = 60,
    run_id: str | None = None,
    ticket_id: int | None = None,
) -> dict[str, Any]:
    """Flatten the audit trail into the most recent steps, newest last.

    This is the dashboard's window into what the agents actually did: who ran,
    who delegated to whom, which MCP tool was called and what it returned.

    `run_id` and `ticket_id` narrow it. Filtering by `ticket_id` drops the
    run-level markers that carry no ticket, so the result is strictly the work
    done on that one ticket and nothing alongside it.
    """
    if not TRAIL_PATH.exists():
        return {"steps": [], "runs": 0}
    try:
        runs = json.loads(TRAIL_PATH.read_text())
    except json.JSONDecodeError:
        raise HTTPException(500, "The audit trail is not readable JSON.")

    steps: list[dict[str, Any]] = []
    for run in runs:
        if run_id and run.get("run_id") != run_id:
            continue
        for step in run.get("steps", []):
            if ticket_id is not None and step.get("ticket_id") != ticket_id:
                continue
            data = step.get("data") or {}
            steps.append({
                "run_id": run.get("run_id"),
                "step": step.get("step"),
                "at": step.get("at"),
                "agent": step.get("agent"),
                "event": step.get("event"),
                "ticket_id": step.get("ticket_id"),
                "detail": step.get("detail"),
                "tool": data.get("tool"),
                "arguments": data.get("arguments"),
                "instruction": data.get("instruction"),
                "chain": data.get("chain"),
                "usage": step.get("usage") or {},
            })
    return {
        "runs": len(runs),
        "returned": min(limit, len(steps)),
        "filtered_by": {"run_id": run_id, "ticket_id": ticket_id},
        "steps": steps[-limit:],
    }


@app.get("/api/approvals", summary="Payments staged by the agents and awaiting a human")
async def get_approvals(status: str | None = None) -> dict[str, Any]:
    """List staged payments. Nothing here has moved any money."""
    result = await call_tool("list_payment_approvals",
                             {"status": status} if status else {})
    result["note"] = ("Every row listed here is a request. No money moves until a "
                      "person decides it through POST /api/approvals/{id}/decision.")
    return result


@app.post("/api/approvals/{approval_id}/decision",
          summary="A human approves or rejects a staged payment")
async def decide_approval(approval_id: int, body: ApprovalDecision) -> dict[str, Any]:
    """Record the human's decision, and settle the payment only if approved.

    This route is the human in the loop. The click is the authorization: it is
    the only place in the system where the operator token is attached to a
    decision, and no agent can reach it.

    Approval is still not sufficient on its own — the MCP server re-checks that
    the balance covers the amount before releasing it, so a payment approved
    for more than the shop holds is refused here too.
    """
    async with ops_session() as (toolset, trail):
        pending = await toolset.direct_call_tool("list_payment_approvals", {})
        match = next((a for a in pending.get("approvals", [])
                      if a["id"] == approval_id), None)
        if match is None:
            raise HTTPException(404, f"No approval {approval_id}.")
        if match["status"] != "pending":
            raise HTTPException(409,
                                f"Approval {approval_id} is already {match['status']!r}.")

        decision = "approved" if body.decision == "approve" else "rejected"
        who = body.authorized_by.strip()

        recorded = await toolset.direct_call_tool("record_human_decision", {
            "approval_id": approval_id, "decision": decision,
            "decided_by": who, "human_token": OPERATOR_TOKEN,
        })
        if not recorded.get("ok"):
            raise HTTPException(400, recorded.get("reason", "Decision refused."))

        trail.log(agent="human operator", event="human_decision",
                  ticket_id=match.get("ticket_id"),
                  detail=f"approval {approval_id}: {decision} via dashboard",
                  data={"approval_id": approval_id, "decision": decision,
                        "decided_by": who})

        if decision == "rejected":
            return {"approval_id": approval_id, "decision": decision,
                    "decided_by": who, "paid": False,
                    "note": "Rejected. No money moved."}

        paid = await toolset.direct_call_tool(
            "record_approved_payment", {"approval_id": approval_id, "paid_by": who})
        if not paid.get("ok"):
            # Approved but refused at settlement — the balance guard caught it.
            raise HTTPException(409, paid.get("reason", "Payment refused."))

        trail.log(agent="human operator", event="tool_result",
                  ticket_id=match.get("ticket_id"), detail="record_approved_payment",
                  data=paid)

        # The payment clearing does not resolve the ticket. Money moving is one
        # piece of work finishing, not proof that the rest of the ticket is
        # done — the customer may still be owed a reply, stock may still need
        # adjusting. The ticket goes back to `open` with the payment recorded,
        # and only the Boss can judge it resolved on a later run.
        if match.get("ticket_id"):
            await toolset.direct_call_tool("update_ticket_status", {
                "ticket_id": match["ticket_id"], "status": "open",
                "resolution_note": (
                    f"Approval {approval_id} approved by {who} in the dashboard; "
                    f"payment {paid['payment_id']} of ${paid['amount']:,.2f} left "
                    f"{paid['account']} at ${paid['balance_after']:,.2f}. "
                    "Reopened so the team can confirm whether anything else on this "
                    "ticket is outstanding before it is resolved."),
                "updated_by": "dashboard (post-approval)",
            })

        return {"approval_id": approval_id, "decision": decision, "decided_by": who,
                "paid": True, "payment": paid}


@app.post("/api/reset", summary="Restore the working database from the untouched original")
async def reset_database() -> dict[str, Any]:
    """Copy the pristine original over the working copy, for a clean run.

    The copy only ever goes original -> working. The original is opened for
    reading and is never written, so a reset cannot damage the baseline no
    matter how often it is called.
    """
    if not ORIGINAL_DB.exists():
        raise HTTPException(500, f"Original database missing at {ORIGINAL_DB}.")

    before = await call_tool("get_cash_balance", {})
    shutil.copy2(ORIGINAL_DB, WORKING_DB)
    RUNS.clear()
    after = await call_tool("get_cash_balance", {})

    return {
        "ok": True,
        "restored": str(WORKING_DB.relative_to(HW_ROOT)),
        "restored_from": str(ORIGINAL_DB.relative_to(HW_ROOT)),
        "original_modified": False,
        "cash_before": before.get("total_balance"),
        "cash_after": after.get("total_balance"),
        "at": now(),
    }


# ------------------------------------------------------------- background


async def _execute_run(run_id: str, ticket_ids: list[int]) -> None:
    """Work each ticket with the agent team, leaving payments for a human."""
    record = RUNS[run_id]
    trail = AuditTrail(run_id=run_id, model=MODEL_NAME, limits=LIMITS_SUMMARY)
    toolset = build_toolset(trail, OPERATOR_TOKEN)
    totals = {"requests": 0, "input_tokens": 0, "output_tokens": 0,
              "total_tokens": 0, "tool_calls": 0}
    try:
        boss, _ = build_team(toolset)
        async with toolset:
            shop_date = (await toolset.direct_call_tool("get_shop_date", {})
                         ).get("date_today")
            trail.record.shop_date = shop_date
            trail.record.tickets_handled = list(ticket_ids)
            trail.log(agent="runner", event="run_started",
                      detail=f"dashboard run, model={MODEL_NAME}, shop date {shop_date}")

            for ticket_id in ticket_ids:
                usage = RunUsage()
                deps = TeamDeps(trail=trail, ticket_id=ticket_id)
                trail.log(agent="boss", event="agent_started", ticket_id=ticket_id,
                          detail=f"handling ticket {ticket_id}")
                result = await boss.run(
                    BOSS_BRIEF.format(ticket_id=ticket_id),
                    deps=deps, usage=usage, usage_limits=USAGE_LIMITS)
                resolution: TicketResolution = result.output
                resolution.delegated_to = list(dict.fromkeys(deps.delegated_to))  # type: ignore[assignment]
                resolution.actions_taken = deps.actions_taken or resolution.actions_taken
                resolution.human_approval_needed = deps.approvals_requested
                resolution.customer_or_vendor_drafts = deps.drafts_written

                trail.record.resolutions.append(resolution)
                trail.log(agent="boss", event="agent_finished", ticket_id=ticket_id,
                          detail=resolution.summary,
                          data=resolution.model_dump(mode="json"))
                record["resolutions"].append(resolution.model_dump(mode="json"))

                for key, val in (("requests", usage.requests),
                                 ("input_tokens", usage.input_tokens),
                                 ("output_tokens", usage.output_tokens),
                                 ("total_tokens", usage.total_tokens),
                                 ("tool_calls", usage.tool_calls)):
                    totals[key] += val
                record["usage"] = dict(totals)

            trail.log(agent="runner", event="run_finished",
                      detail=f"{len(trail.record.resolutions)} ticket(s) handled",
                      usage=dict(totals))
        record["status"] = "finished"
    except Exception as exc:  # limit hit, gateway error, bad output
        record["status"] = "failed"
        record["error"] = f"{type(exc).__name__}: {exc}"
        trail.log(agent="runner", event="error", detail=record["error"])
    finally:
        record["finished_at"] = now()
        record["usage"] = dict(totals)
        trail.finish(total_usage=dict(totals),
                     stopped_early=record["status"] == "failed",
                     stop_reason=record["error"])
