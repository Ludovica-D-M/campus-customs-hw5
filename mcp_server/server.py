"""Campus Customs operations MCP server.

Every fact the agents know about the shop, and every change they make to it,
goes through this server. It is the only component that opens the database.

Read tools answer questions. Write tools change the working copy and are each
wrapped in a hard guard that cannot be talked out of:

  * money never moves without a human decision recorded in `approvals`;
  * cash can never go negative;
  * nothing is ever sent to a customer or vendor — messages are only drafted.

The server reads and writes data/campus_customs_new.db. The original
data/campus_customs.db is never opened.

Run as an MCP server (stdio):  .venv/bin/python mcp_server/server.py
Run over HTTP:                 .venv/bin/python mcp_server/server.py --http
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

HERE = Path(__file__).resolve().parent
HW_ROOT = HERE.parent

# The working copy only. The original campus_customs.db stays untouched.
DB_PATH = HW_ROOT / "data" / "campus_customs_new.db"

# Shared secret that proves a decision came from the human operator, not from a
# model. The runner generates it, passes it to this process in the environment,
# and never puts it in a prompt — so an agent cannot approve its own payment.
HUMAN_TOKEN_ENV = "CAMPUS_CUSTOMS_HUMAN_TOKEN"

# Names that may never appear as the approver of a payment.
AGENT_NAMES = {"boss", "inventory", "accounting", "facilities", "customer_service",
               "agent", "boss_advisor", "runner"}

mcp = FastMCP("campus-customs-ops")


# ---------------------------------------------------------------- plumbing


def _connect() -> sqlite3.Connection:
    """Open the working-copy database with dict-like rows."""
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Working database not found at {DB_PATH}. "
            "Copy data/campus_customs.db to data/campus_customs_new.db first."
        )
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    _ensure_agent_tables(conn)
    return conn


def _ensure_agent_tables(conn: sqlite3.Connection) -> None:
    """Create the three tables the agent workflow needs, if absent.

    These sit alongside the shop's original tables in the working copy and hold
    the approval gate, the never-sent message drafts, and the stock-change log.
    """
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS approvals (
            id            INTEGER PRIMARY KEY,
            kind          TEXT NOT NULL,
            ref_id        INTEGER,
            amount        REAL NOT NULL,
            account       TEXT NOT NULL,
            reason        TEXT NOT NULL,
            requested_by  TEXT NOT NULL,
            ticket_id     INTEGER,
            status        TEXT NOT NULL DEFAULT 'pending',
            requested_at  TEXT NOT NULL,
            decided_by    TEXT,
            decided_at    TEXT,
            payment_id    INTEGER
        );
        CREATE TABLE IF NOT EXISTS message_drafts (
            id          INTEGER PRIMARY KEY,
            ticket_id   INTEGER,
            audience    TEXT NOT NULL,
            recipient   TEXT NOT NULL,
            subject     TEXT NOT NULL,
            body        TEXT NOT NULL,
            drafted_by  TEXT NOT NULL,
            created_at  TEXT NOT NULL,
            sent        INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS inventory_adjustments (
            id          INTEGER PRIMARY KEY,
            sku         TEXT NOT NULL,
            size        TEXT NOT NULL,
            delta       INTEGER NOT NULL,
            qty_after   INTEGER NOT NULL,
            reason      TEXT NOT NULL,
            changed_by  TEXT NOT NULL,
            changed_at  TEXT NOT NULL,
            ticket_id   INTEGER
        );
        """
    )
    conn.commit()


def _rows(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def _one(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> dict[str, Any] | None:
    rows = _rows(conn, sql, params)
    return rows[0] if rows else None


def _today(conn: sqlite3.Connection) -> str:
    """The shop's current date, from the desk table — not the system clock."""
    row = _one(conn, "SELECT date_today FROM desk LIMIT 1")
    return row["date_today"] if row else ""


def _stamp() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


# ------------------------------------------------------------- read tools


@mcp.tool
def get_shop_date() -> dict[str, Any]:
    """Get the shop's current working date.

    Reads: desk.

    Always use this instead of real-world "today". Every due-date, overdue and
    lead-time judgment in the shop is made against this date.
    """
    conn = _connect()
    try:
        row = _one(conn, "SELECT date_today, notes FROM desk LIMIT 1")
        return row or {"date_today": None, "notes": None}
    finally:
        conn.close()


@mcp.tool
def list_open_tickets() -> dict[str, Any]:
    """List every ticket still open, with its type and what it refers to.

    Reads: tickets, desk.

    This is the work queue. Use it to see what needs handling before picking a
    ticket to work on.
    """
    conn = _connect()
    try:
        return {
            "as_of_date": _today(conn),
            "open_tickets": _rows(
                conn,
                """
                SELECT id, type, requester, subject, sku, size, qty,
                       lease_id, invoice_id, status, notes, created_at
                FROM tickets WHERE status = 'open' ORDER BY id
                """,
            ),
        }
    finally:
        conn.close()


@mcp.tool
def list_tickets(status: str | None = None) -> dict[str, Any]:
    """List every ticket, or only those in one status, with a count per status.

    Reads: tickets, desk.

    Where `list_open_tickets` is the agents' work queue, this is the whole
    board — it is what a dashboard needs to show a ticket that has already been
    resolved or is sitting at awaiting_approval.
    """
    conn = _connect()
    try:
        sql = """
            SELECT id, type, requester, subject, sku, size, qty, lease_id,
                   invoice_id, status, notes, created_at
            FROM tickets {where} ORDER BY id
        """
        rows = (_rows(conn, sql.format(where="WHERE status = ?"), (status,))
                if status else _rows(conn, sql.format(where="")))
        counts: dict[str, int] = {}
        for r in _rows(conn, "SELECT status, COUNT(*) AS n FROM tickets GROUP BY status"):
            counts[r["status"]] = r["n"]
        return {"as_of_date": _today(conn), "tickets": rows, "counts_by_status": counts}
    finally:
        conn.close()


@mcp.tool
def get_ticket(ticket_id: int) -> dict[str, Any]:
    """Get one ticket together with every record it points at.

    Reads: tickets, and whichever of inventory, pricing, leases, invoices and
    vendors the ticket links to, plus desk.

    Use this first on any ticket: it resolves the ticket's foreign keys so you
    see the request and its supporting facts in one place, instead of acting on
    the ticket's wording alone.
    """
    conn = _connect()
    try:
        as_of = _today(conn)
        ticket = _one(
            conn,
            """
            SELECT id, type, requester, subject, sku, size, qty, lease_id,
                   invoice_id, status, notes, created_at
            FROM tickets WHERE id = ?
            """,
            (ticket_id,),
        )
        if ticket is None:
            return {"as_of_date": as_of, "found": False,
                    "message": f"No ticket with id {ticket_id}."}

        linked: dict[str, Any] = {}
        if ticket["sku"]:
            linked["pricing"] = _one(
                conn, "SELECT sku, unit_cost, list_price FROM pricing WHERE sku = ?",
                (ticket["sku"],),
            )
            if ticket["size"]:
                linked["inventory"] = _one(
                    conn,
                    "SELECT sku, name, size, qty, location FROM inventory "
                    "WHERE sku = ? AND size = ?",
                    (ticket["sku"], ticket["size"]),
                )
        if ticket["lease_id"]:
            linked["lease"] = _one(
                conn,
                "SELECT id, space_name, landlord, monthly_rent, next_due, notes "
                "FROM leases WHERE id = ?",
                (ticket["lease_id"],),
            )
        if ticket["invoice_id"]:
            linked["invoice"] = _one(
                conn,
                """
                SELECT i.id, i.amount, i.due_date, i.status, i.description,
                       v.id AS vendor_id, v.name AS vendor_name,
                       v.specialty AS vendor_specialty, v.lead_days
                FROM invoices i JOIN vendors v ON v.id = i.vendor_id
                WHERE i.id = ?
                """,
                (ticket["invoice_id"],),
            )
            if linked["invoice"] and as_of:
                linked["invoice"]["is_overdue"] = (
                    linked["invoice"]["due_date"] < as_of
                    and linked["invoice"]["status"] != "paid"
                )

        return {"as_of_date": as_of, "found": True, "ticket": ticket, "linked": linked}
    finally:
        conn.close()


@mcp.tool
def check_item_availability(sku: str, size: str, qty_requested: int = 1) -> dict[str, Any]:
    """Check whether a product can be filled from stock now, and what is already on order for it.

    Reads: inventory, pricing, desk, and tickets -> invoices -> vendors.

    Use this for customer-order tickets such as ticket 101 (1 x CC-TEE-WHITE,
    size S): it says whether the shelf covers the order and, if not, whether a
    reprint is already invoiced and how long that vendor takes.
    """
    conn = _connect()
    try:
        as_of = _today(conn)
        item = _one(
            conn,
            "SELECT sku, name, size, qty, location FROM inventory WHERE sku = ? AND size = ?",
            (sku, size),
        )
        if item is None:
            return {
                "as_of_date": as_of,
                "found": False,
                "message": f"No inventory row for sku {sku!r} in size {size!r}.",
                "sizes_carried": [
                    r["size"]
                    for r in _rows(
                        conn, "SELECT size FROM inventory WHERE sku = ? ORDER BY size", (sku,)
                    )
                ],
            }

        on_hand = item["qty"]
        shortfall = max(0, qty_requested - on_hand)
        price = _one(conn, "SELECT unit_cost, list_price FROM pricing WHERE sku = ?", (sku,))

        related_invoices = _rows(
            conn,
            """
            SELECT DISTINCT i.id, i.amount, i.due_date, i.status, i.description,
                   v.name AS vendor_name, v.specialty AS vendor_specialty, v.lead_days
            FROM tickets t
            JOIN invoices i ON i.id = t.invoice_id
            JOIN vendors  v ON v.id = i.vendor_id
            WHERE t.sku = ? AND t.size = ?
            ORDER BY i.id
            """,
            (sku, size),
        )
        for inv in related_invoices:
            inv["is_overdue"] = bool(
                as_of and inv["due_date"] < as_of and inv["status"] != "paid"
            )

        return {
            "as_of_date": as_of,
            "found": True,
            "item": {
                "sku": item["sku"],
                "name": item["name"],
                "size": item["size"],
                "qty_on_hand": on_hand,
                "location": item["location"],
            },
            "pricing": price,
            "request": {
                "qty_requested": qty_requested,
                "can_fill_from_stock": shortfall == 0,
                "shortfall": shortfall,
            },
            "related_invoices": related_invoices,
        }
    finally:
        conn.close()


@mcp.tool
def verify_rent_due(lease_id: int = 1) -> dict[str, Any]:
    """Verify a rent demand against the lease on file and check the shop can afford it.

    Reads: leases, desk, payments, cash_accounts, invoices joined to vendors.

    Use this for rent-notice tickets such as ticket 102, where an email claims
    rent is due: this confirms the amount and date against the signed lease
    rather than trusting the message, and shows the balance left after paying.
    """
    conn = _connect()
    try:
        as_of = _today(conn)
        lease = _one(
            conn,
            "SELECT id, space_name, landlord, monthly_rent, next_due, notes "
            "FROM leases WHERE id = ?",
            (lease_id,),
        )
        if lease is None:
            return {"as_of_date": as_of, "found": False,
                    "message": f"No lease with id {lease_id}."}

        days_until_due = None
        if as_of:
            row = _one(
                conn,
                "SELECT CAST(julianday(?) - julianday(?) AS INTEGER) AS d",
                (lease["next_due"], as_of),
            )
            days_until_due = row["d"] if row else None

        already_paid = _rows(
            conn,
            "SELECT id, kind, ref_id, amount, account, paid_at, approved_by "
            "FROM payments WHERE kind = 'rent' AND ref_id = ? ORDER BY paid_at",
            (lease_id,),
        )
        cash = _one(conn, "SELECT name, balance, date FROM cash_accounts "
                          "ORDER BY balance DESC LIMIT 1")
        open_invoices = _rows(
            conn,
            """
            SELECT i.id, i.amount, i.due_date, i.status, i.description, v.name AS vendor_name
            FROM invoices i JOIN vendors v ON v.id = i.vendor_id
            WHERE i.status != 'paid' ORDER BY i.due_date
            """,
        )
        other_obligations = round(sum(i["amount"] for i in open_invoices), 2)
        rent = lease["monthly_rent"]
        balance = cash["balance"] if cash else 0.0

        return {
            "as_of_date": as_of,
            "found": True,
            "lease": lease,
            "due": {
                "amount": rent,
                "next_due": lease["next_due"],
                "days_until_due": days_until_due,
                "is_overdue": bool(as_of and lease["next_due"] < as_of),
            },
            "already_paid": already_paid,
            "cash": cash,
            "if_paid": {
                "balance_after_rent": round(balance - rent, 2),
                "covers_rent": balance >= rent,
                "other_open_invoices_total": other_obligations,
                "covers_rent_and_open_invoices": balance >= rent + other_obligations,
            },
            "open_invoices": open_invoices,
        }
    finally:
        conn.close()


@mcp.tool
def quote_bulk_order(
    sku: str, size: str, qty: int, proposed_unit_price: float | None = None
) -> dict[str, Any]:
    """Price a bulk or discounted order and check it stays above cost and is supplyable.

    Reads: pricing, inventory, vendors, desk.

    Use this for price-override tickets such as ticket 103 (20 x CC-HOOD-NAVY,
    size M): it separates the two questions the ticket really asks — can we
    supply this quantity, and does the proposed price still clear what the shop
    paid for the goods.
    """
    conn = _connect()
    try:
        as_of = _today(conn)
        price = _one(conn, "SELECT sku, unit_cost, list_price FROM pricing WHERE sku = ?", (sku,))
        if price is None:
            return {"as_of_date": as_of, "found": False,
                    "message": f"No pricing row for sku {sku!r}."}

        unit_cost = price["unit_cost"]
        list_price = price["list_price"]
        item = _one(
            conn, "SELECT name, qty, location FROM inventory WHERE sku = ? AND size = ?",
            (sku, size),
        )
        on_hand = item["qty"] if item else 0
        shortfall = max(0, qty - on_hand)

        quote: dict[str, Any] = {
            "list_unit_price": list_price,
            "list_total": round(list_price * qty, 2),
            "unit_cost": unit_cost,
            "cost_total": round(unit_cost * qty, 2),
            "margin_at_list_total": round((list_price - unit_cost) * qty, 2),
            "break_even_unit_price": unit_cost,
            "max_discount_pct_before_loss": round(
                (list_price - unit_cost) / list_price * 100, 1
            ) if list_price else None,
        }
        if proposed_unit_price is not None:
            quote["proposed"] = {
                "unit_price": proposed_unit_price,
                "total": round(proposed_unit_price * qty, 2),
                "discount_pct_off_list": round(
                    (list_price - proposed_unit_price) / list_price * 100, 1
                ) if list_price else None,
                "margin_per_unit": round(proposed_unit_price - unit_cost, 2),
                "margin_total": round((proposed_unit_price - unit_cost) * qty, 2),
                "above_cost": proposed_unit_price > unit_cost,
            }

        return {
            "as_of_date": as_of,
            "found": True,
            "item": {
                "sku": sku,
                "name": item["name"] if item else None,
                "size": size,
                "qty_on_hand": on_hand,
                "location": item["location"] if item else None,
            },
            "supply": {
                "qty_requested": qty,
                "can_fill_from_stock": shortfall == 0,
                "shortfall": shortfall,
            },
            "quote": quote,
            # Vendor choice is left to the caller: specialty and lead_days are
            # reported as stored, with no sku-to-vendor mapping assumed.
            "vendors": _rows(
                conn, "SELECT id, name, specialty, lead_days FROM vendors ORDER BY lead_days"
            ),
        }
    finally:
        conn.close()


@mcp.tool
def list_vendors() -> dict[str, Any]:
    """List every vendor with its specialty and lead time in days.

    Reads: vendors, desk.

    Use this to turn a stock shortfall into a realistic promise date. The
    earliest possible arrival is the shop date plus that vendor's lead_days.
    """
    conn = _connect()
    try:
        return {
            "as_of_date": _today(conn),
            "vendors": _rows(
                conn, "SELECT id, name, specialty, lead_days FROM vendors ORDER BY lead_days"
            ),
        }
    finally:
        conn.close()


@mcp.tool
def list_unpaid_invoices() -> dict[str, Any]:
    """List every invoice not yet paid, flagged overdue against the shop date.

    Reads: invoices, vendors, desk.

    Use this before approving any spending: these are the claims already
    standing against the shop's cash.
    """
    conn = _connect()
    try:
        as_of = _today(conn)
        invoices = _rows(
            conn,
            """
            SELECT i.id, i.amount, i.due_date, i.status, i.description,
                   v.id AS vendor_id, v.name AS vendor_name, v.lead_days
            FROM invoices i JOIN vendors v ON v.id = i.vendor_id
            WHERE i.status != 'paid' ORDER BY i.due_date
            """,
        )
        for inv in invoices:
            inv["is_overdue"] = bool(as_of and inv["due_date"] < as_of)
        return {
            "as_of_date": as_of,
            "unpaid_invoices": invoices,
            "total_unpaid": round(sum(i["amount"] for i in invoices), 2),
            "overdue_count": sum(1 for i in invoices if i["is_overdue"]),
        }
    finally:
        conn.close()


@mcp.tool
def get_cash_balance() -> dict[str, Any]:
    """Get cash on hand split by when each obligation actually falls due.

    Reads: cash_accounts, invoices, leases, desk.

    A single "committed" total mixes horizons and misleads: rent that is not
    due for another month is a real obligation, but it is not competing with
    today's cash the way an overdue invoice is. So obligations are split into
    `due_now` (on or before the shop date) and `upcoming` (after it), with the
    date attached to each.

    `free_now` is what is genuinely spendable today — balance minus what is
    already due. `free_after_all_known` also subtracts the upcoming items and
    can be negative, which means the shop is solvent today but has not yet
    covered what is coming.
    """
    conn = _connect()
    try:
        as_of = _today(conn)
        accounts = _rows(conn, "SELECT name, balance, date FROM cash_accounts ORDER BY name")
        total = round(sum(a["balance"] for a in accounts), 2)

        due_now: list[dict[str, Any]] = []
        upcoming: list[dict[str, Any]] = []

        for inv in _rows(
            conn,
            "SELECT i.id, i.amount, i.due_date, i.description, v.name AS vendor_name "
            "FROM invoices i JOIN vendors v ON v.id = i.vendor_id "
            "WHERE i.status != 'paid' ORDER BY i.due_date",
        ):
            row = {"kind": "invoice", "ref_id": inv["id"], "amount": inv["amount"],
                   "due_date": inv["due_date"],
                   "label": f"invoice {inv['id']} — {inv['vendor_name']}"}
            (due_now if (as_of and inv["due_date"] <= as_of) else upcoming).append(row)

        for lease in _rows(
            conn, "SELECT id, space_name, monthly_rent, next_due FROM leases ORDER BY id"
        ):
            row = {"kind": "rent", "ref_id": lease["id"], "amount": lease["monthly_rent"],
                   "due_date": lease["next_due"],
                   "label": f"rent — {lease['space_name']}"}
            (due_now if (as_of and lease["next_due"] <= as_of) else upcoming).append(row)

        due_now_total = round(sum(r["amount"] for r in due_now), 2)
        upcoming_total = round(sum(r["amount"] for r in upcoming), 2)

        return {
            "as_of_date": as_of,
            "accounts": accounts,
            "total_balance": total,
            "due_now": {"total": due_now_total, "items": due_now},
            "upcoming": {"total": upcoming_total, "items": upcoming},
            "free_now": round(total - due_now_total, 2),
            "free_after_all_known": round(total - due_now_total - upcoming_total, 2),
            # Kept so older callers keep working; `due_now`/`upcoming` is the
            # breakdown that should be used.
            "committed": {
                "unpaid_invoices": round(
                    sum(r["amount"] for r in due_now + upcoming if r["kind"] == "invoice"), 2),
                "next_rent": round(
                    sum(r["amount"] for r in due_now + upcoming if r["kind"] == "rent"), 2),
                "total": round(due_now_total + upcoming_total, 2),
            },
            "uncommitted": round(total - due_now_total - upcoming_total, 2),
        }
    finally:
        conn.close()


@mcp.tool
def list_payment_approvals(status: str | None = None) -> dict[str, Any]:
    """List payment approval requests and where each one stands.

    Reads: approvals, desk.

    Use this to check whether a payment you requested has been decided by the
    human operator yet. Agents cannot change these rows.
    """
    conn = _connect()
    try:
        if status:
            rows = _rows(conn, "SELECT * FROM approvals WHERE status = ? ORDER BY id", (status,))
        else:
            rows = _rows(conn, "SELECT * FROM approvals ORDER BY id")
        return {"as_of_date": _today(conn), "approvals": rows}
    finally:
        conn.close()


# ------------------------------------------------------------ write tools


@mcp.tool
def request_payment_approval(
    kind: str,
    amount: float,
    account: str,
    reason: str,
    requested_by: str,
    ref_id: int | None = None,
    ticket_id: int | None = None,
) -> dict[str, Any]:
    """Ask the human operator to approve a payment. This does NOT pay anything.

    Writes: approvals (one row, status 'pending'). Reads: cash_accounts,
    invoices, leases, desk.

    This is the only way to start a payment. Money never leaves on an agent's
    say-so: the row sits at 'pending' until a human decides it, and only then
    can `record_approved_payment` move the cash.

    The request is refused outright if the account does not exist or the
    balance would not cover the amount — an unaffordable payment is never even
    put in front of the operator.

    Args:
        kind: What is being paid, e.g. "rent" or "invoice".
        amount: Amount in dollars.
        account: Cash account to draw from, e.g. "checking".
        reason: Why this payment should happen, in one or two sentences.
        requested_by: Name of the agent making the request.
        ref_id: The leases.id or invoices.id being settled, if any.
        ticket_id: The ticket this request came from, if any.
    """
    conn = _connect()
    try:
        as_of = _today(conn)
        if amount <= 0:
            return {"ok": False, "reason": "Amount must be greater than zero."}

        acct = _one(conn, "SELECT name, balance FROM cash_accounts WHERE name = ?", (account,))
        if acct is None:
            return {"ok": False, "reason": f"No cash account named {account!r}."}
        if amount > acct["balance"]:
            return {
                "ok": False,
                "reason": (
                    f"Refused: ${amount:,.2f} exceeds the ${acct['balance']:,.2f} "
                    f"available in {account!r}. The shop cannot go cash-negative."
                ),
                "balance": acct["balance"],
            }

        cur = conn.execute(
            """
            INSERT INTO approvals
                (kind, ref_id, amount, account, reason, requested_by, ticket_id,
                 status, requested_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)
            """,
            (kind, ref_id, amount, account, reason, requested_by, ticket_id, _stamp()),
        )
        conn.commit()
        return {
            "ok": True,
            "approval_id": cur.lastrowid,
            "status": "pending",
            "as_of_date": as_of,
            "balance_if_approved": round(acct["balance"] - amount, 2),
            "note": (
                "Recorded as pending. No money has moved. A human operator must "
                "decide this before record_approved_payment will do anything."
            ),
        }
    finally:
        conn.close()


@mcp.tool
def record_approved_payment(approval_id: int, paid_by: str) -> dict[str, Any]:
    """Pay an approval the human operator has already approved.

    Writes: payments (new row), cash_accounts (balance decreased), invoices
    (status set to paid when the approval refers to one), leases (next_due
    rolled forward a month for rent), approvals (marked paid).

    Refuses unless the approval exists and its status is exactly 'approved',
    it has not already been paid, and the account balance covers the amount.
    An agent cannot approve its own request: only `record_human_decision`,
    which requires the operator's token, can set an approval to 'approved'.
    """
    conn = _connect()
    try:
        appr = _one(conn, "SELECT * FROM approvals WHERE id = ?", (approval_id,))
        if appr is None:
            return {"ok": False, "reason": f"No approval with id {approval_id}."}
        if appr["status"] == "paid":
            return {"ok": False, "reason": "That approval has already been paid.",
                    "payment_id": appr["payment_id"]}
        if appr["status"] != "approved":
            return {
                "ok": False,
                "reason": (
                    f"Refused: approval {approval_id} is {appr['status']!r}, not 'approved'. "
                    "A human operator has to approve it first."
                ),
            }

        acct = _one(
            conn, "SELECT name, balance FROM cash_accounts WHERE name = ?", (appr["account"],)
        )
        if acct is None:
            return {"ok": False, "reason": f"No cash account named {appr['account']!r}."}
        if appr["amount"] > acct["balance"]:
            return {
                "ok": False,
                "reason": (
                    f"Refused: paying ${appr['amount']:,.2f} would overdraw "
                    f"{appr['account']!r}, which holds ${acct['balance']:,.2f}. "
                    "Cash balances may not go negative."
                ),
            }

        # Stamped with the shop's date, not the wall clock. `payments` is shop
        # ledger data and sits beside `invoices.due_date` and `leases.next_due`,
        # which are all on the shop calendar — a real-world timestamp here reads
        # as a payment made in the future and makes the agents distrust it.
        paid_at = _today(conn) or _stamp()
        cur = conn.execute(
            """
            INSERT INTO payments (kind, ref_id, amount, account, paid_at, approved_by)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (appr["kind"], appr["ref_id"], appr["amount"], appr["account"],
             paid_at, appr["decided_by"] or "human operator"),
        )
        payment_id = cur.lastrowid
        new_balance = round(acct["balance"] - appr["amount"], 2)
        conn.execute(
            "UPDATE cash_accounts SET balance = ?, date = ? WHERE name = ?",
            (new_balance, _today(conn), appr["account"]),
        )
        if appr["kind"] == "invoice" and appr["ref_id"]:
            conn.execute("UPDATE invoices SET status = 'paid' WHERE id = ?", (appr["ref_id"],))
        if appr["kind"] == "rent" and appr["ref_id"]:
            conn.execute(
                "UPDATE leases SET next_due = date(next_due, '+1 month') WHERE id = ?",
                (appr["ref_id"],),
            )
        conn.execute(
            "UPDATE approvals SET status = 'paid', payment_id = ? WHERE id = ?",
            (payment_id, approval_id),
        )
        conn.commit()
        return {
            "ok": True,
            "payment_id": payment_id,
            "amount": appr["amount"],
            "account": appr["account"],
            "approved_by": appr["decided_by"],
            "paid_at": paid_at,
            "balance_after": new_balance,
        }
    finally:
        conn.close()


@mcp.tool
def record_human_decision(
    approval_id: int, decision: str, decided_by: str, human_token: str
) -> dict[str, Any]:
    """Record the human operator's decision on a pending payment approval.

    Writes: approvals (status set to 'approved' or 'rejected').

    NOT FOR AGENT USE. This tool requires the operator's token, which is given
    to the server process in its environment and is never placed in any prompt.
    An agent calling it without the token is refused, which is what keeps the
    human in the loop genuine rather than ceremonial.
    """
    expected = os.getenv(HUMAN_TOKEN_ENV, "")
    if not expected:
        return {"ok": False, "reason": f"{HUMAN_TOKEN_ENV} is not set on the server; "
                                       "no human decision can be recorded."}
    if human_token != expected:
        return {"ok": False, "reason": "Refused: invalid operator token. Only the human "
                                       "operator can approve or reject a payment."}
    if decision not in {"approved", "rejected"}:
        return {"ok": False, "reason": "decision must be 'approved' or 'rejected'."}
    # Defence in depth: even with a valid token, a decision attributed to one of
    # the agents is not a human decision. The token should make this
    # unreachable; it is here so that if it ever is reached, it fails closed.
    if decided_by.strip().lower().replace(" ", "_") in AGENT_NAMES:
        return {"ok": False, "reason": (
            f"Refused: {decided_by!r} is an agent, not a person. A payment "
            "approval must be attributed to the human who authorized it."
        )}

    conn = _connect()
    try:
        appr = _one(conn, "SELECT * FROM approvals WHERE id = ?", (approval_id,))
        if appr is None:
            return {"ok": False, "reason": f"No approval with id {approval_id}."}
        if appr["status"] != "pending":
            return {"ok": False, "reason": f"Approval {approval_id} is already "
                                           f"{appr['status']!r}."}
        conn.execute(
            "UPDATE approvals SET status = ?, decided_by = ?, decided_at = ? WHERE id = ?",
            (decision, decided_by, _stamp(), approval_id),
        )
        conn.commit()
        return {"ok": True, "approval_id": approval_id, "status": decision,
                "decided_by": decided_by}
    finally:
        conn.close()


@mcp.tool
def adjust_inventory(
    sku: str,
    size: str,
    delta: int,
    reason: str,
    changed_by: str,
    ticket_id: int | None = None,
) -> dict[str, Any]:
    """Change the units on hand for one sku and size, and log why.

    Writes: inventory (qty), inventory_adjustments (one row).

    Use a negative delta to reserve or ship stock, a positive one to receive
    it. Refused if the row does not exist or the change would take stock below
    zero — the shop cannot ship goods it does not have.
    """
    conn = _connect()
    try:
        item = _one(
            conn, "SELECT sku, name, size, qty FROM inventory WHERE sku = ? AND size = ?",
            (sku, size),
        )
        if item is None:
            return {"ok": False, "reason": f"No inventory row for {sku!r} in size {size!r}."}
        new_qty = item["qty"] + delta
        if new_qty < 0:
            return {
                "ok": False,
                "reason": (
                    f"Refused: {item['qty']} on hand, so a change of {delta} would leave "
                    f"{new_qty}. Stock cannot go negative."
                ),
                "qty_on_hand": item["qty"],
            }
        conn.execute(
            "UPDATE inventory SET qty = ? WHERE sku = ? AND size = ?", (new_qty, sku, size)
        )
        conn.execute(
            """
            INSERT INTO inventory_adjustments
                (sku, size, delta, qty_after, reason, changed_by, changed_at, ticket_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (sku, size, delta, new_qty, reason, changed_by, _stamp(), ticket_id),
        )
        conn.commit()
        return {"ok": True, "sku": sku, "size": size, "delta": delta,
                "qty_before": item["qty"], "qty_after": new_qty}
    finally:
        conn.close()


@mcp.tool
def update_ticket_status(
    ticket_id: int, status: str, resolution_note: str, updated_by: str
) -> dict[str, Any]:
    """Set a ticket's status and append the resolution to its notes.

    Writes: tickets (status, notes).

    Only close a ticket once the work behind it is actually recorded — stock
    adjusted, payment made or approval pending, customer reply drafted. The
    note should say what was decided and why, so the trail stands on its own.
    """
    allowed = {"open", "resolved", "blocked", "awaiting_approval"}
    if status not in allowed:
        return {"ok": False, "reason": f"status must be one of {sorted(allowed)}."}
    conn = _connect()
    try:
        ticket = _one(conn, "SELECT id, status, notes FROM tickets WHERE id = ?", (ticket_id,))
        if ticket is None:
            return {"ok": False, "reason": f"No ticket with id {ticket_id}."}
        note = (ticket["notes"] or "").rstrip()
        note = f"{note}\n[{_stamp()}] {updated_by}: {resolution_note}".strip()
        conn.execute("UPDATE tickets SET status = ?, notes = ? WHERE id = ?",
                     (status, note, ticket_id))
        conn.commit()
        return {"ok": True, "ticket_id": ticket_id, "status_before": ticket["status"],
                "status_after": status}
    finally:
        conn.close()


@mcp.tool
def draft_customer_message(
    audience: str,
    recipient: str,
    subject: str,
    body: str,
    drafted_by: str,
    ticket_id: int | None = None,
) -> dict[str, Any]:
    """Save a reply to a customer or vendor as a draft. Nothing is ever sent.

    Writes: message_drafts (one row, always sent = 0).

    This server has no email, SMS or phone capability at all. Drafts are stored
    for a human to review and send, which is how the shop's "never actually
    contact customers or vendors" rule is enforced rather than merely promised.

    Args:
        audience: "customer" or "vendor".
        recipient: Who the message is addressed to.
        subject: Subject line.
        body: The message itself.
        drafted_by: Name of the agent writing it.
        ticket_id: The ticket this reply belongs to, if any.
    """
    if audience not in {"customer", "vendor"}:
        return {"ok": False, "reason": "audience must be 'customer' or 'vendor'."}
    conn = _connect()
    try:
        cur = conn.execute(
            """
            INSERT INTO message_drafts
                (ticket_id, audience, recipient, subject, body, drafted_by, created_at, sent)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (ticket_id, audience, recipient, subject, body, drafted_by, _stamp()),
        )
        conn.commit()
        return {
            "ok": True,
            "draft_id": cur.lastrowid,
            "sent": False,
            "note": "Saved as a draft only. Nothing was transmitted to anyone.",
        }
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--http", action="store_true", help="Serve over HTTP instead of stdio.")
    parser.add_argument("--port", type=int, default=8000, help="Port for --http.")
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f"error: {DB_PATH} not found", file=sys.stderr)
        raise SystemExit(1)

    if args.http:
        mcp.run(transport="http", port=args.port)
    else:
        mcp.run()


if __name__ == "__main__":
    main()
