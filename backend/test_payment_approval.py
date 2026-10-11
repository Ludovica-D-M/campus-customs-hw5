"""Prove that no payment can be approved without an explicit human authorization.

Runs against the live MCP server and tries every route an agent could take to
get money out of the shop:

    .venv/bin/python backend/test_payment_approval.py

The test leaves the database as it found it.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
from pathlib import Path

HW_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HW_ROOT / "mcp_server"))

from fastmcp import Client  # noqa: E402

OPERATOR_TOKEN = "operator-token-for-this-test"
AGENT_TOOLSETS = HW_ROOT / "backend" / "agents.py"
DB = HW_ROOT / "data" / "campus_customs_new.db"


async def run_checks() -> int:
    os.environ["CAMPUS_CUSTOMS_HUMAN_TOKEN"] = OPERATOR_TOKEN
    import server  # imported after the token is set

    failures = 0

    def report(name: str, ok: bool, detail: str = "") -> None:
        nonlocal failures
        failures += not ok
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
        if detail:
            print(f"         -> {detail}")

    async with Client(server.mcp) as c:
        async def call(name, args):
            return (await c.call_tool(name, args)).data

        start_balance = (await call("get_cash_balance", {}))["accounts"][0]["balance"]

        # 0. No agent is even shown the operator's tool.
        src = AGENT_TOOLSETS.read_text()
        tools_block = src[src.index("TOOLS_FOR: dict[str, set[str]]"):src.index("# Never handed")]
        report("record_human_decision appears in no agent's toolset",
               "record_human_decision" not in tools_block)

        # 1. Staging a payment must not move money.
        appr = await call("request_payment_approval", {
            "kind": "invoice", "ref_id": 501, "amount": 25.0, "account": "checking",
            "reason": "approval-path test", "requested_by": "accounting"})
        aid = appr["approval_id"]
        report("staging a payment leaves it pending and pays nothing",
               appr["ok"] and appr["status"] == "pending", f"approval {aid}: {appr['status']}")

        # 2. An agent cannot pay a pending approval.
        r = await call("record_approved_payment", {"approval_id": aid, "paid_by": "accounting"})
        report("agent cannot pay an approval no human decided",
               not r["ok"] and "not 'approved'" in r["reason"], r["reason"])

        # 3. An agent cannot approve it without the operator token.
        r = await call("record_human_decision", {
            "approval_id": aid, "decision": "approved",
            "decided_by": "accounting", "human_token": "please"})
        report("agent cannot approve without the operator token",
               not r["ok"] and "invalid operator token" in r["reason"], r["reason"])

        # 4. Even with the right token, an agent name is not a person.
        r = await call("record_human_decision", {
            "approval_id": aid, "decision": "approved",
            "decided_by": "boss", "human_token": OPERATOR_TOKEN})
        report("a decision attributed to an agent is refused even with a valid token",
               not r["ok"] and "not a person" in r["reason"], r["reason"])

        # 5. The approval is still pending after all of that.
        rows = (await call("list_payment_approvals", {"status": "pending"}))["approvals"]
        report("the approval is still pending after every attempt",
               any(a["id"] == aid for a in rows))

        # 6. The runner has no automatic approval path.
        runner = (HW_ROOT / "backend" / "run_tickets.py").read_text()
        report("the runner has no auto-approve flag or threshold",
               "auto_approve" not in runner and "auto-approve" not in runner)
        report("approval requires typing an explicit phrase",
               'answer == AUTHORIZE_PHRASE' in runner)
        report("no terminal means the payment is left pending",
               'left PENDING' in runner and 'sys.stdin.isatty()' in runner)

        # 7. Only a named human with the token can approve — and only then does
        #    the money move.
        r = await call("record_human_decision", {
            "approval_id": aid, "decision": "approved",
            "decided_by": "Ludovica (operator, at the terminal)",
            "human_token": OPERATOR_TOKEN})
        report("a named human with the token can approve", r["ok"], json.dumps(r))

        paid = await call("record_approved_payment", {"approval_id": aid, "paid_by": "runner"})
        report("payment only clears after that human decision",
               paid["ok"] and paid["amount"] == 25.0,
               f"payment {paid.get('payment_id')}, balance {paid.get('balance_after')}")

        end_balance = (await call("get_cash_balance", {}))["accounts"][0]["balance"]
        report("cash moved by exactly the approved amount, and only then",
               round(start_balance - end_balance, 2) == 25.0,
               f"${start_balance} -> ${end_balance}")

    return failures


def main() -> int:
    backup = DB.with_suffix(".db.approval-test-backup")
    shutil.copy2(DB, backup)
    try:
        failures = asyncio.run(run_checks())
    finally:
        shutil.copy2(backup, DB)  # leave the shop exactly as we found it
        backup.unlink()
    print(f"\n{'no payment can be approved without a human' if not failures else f'{failures} FAILURE(S)'}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
