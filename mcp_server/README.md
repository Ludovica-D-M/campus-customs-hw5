# Campus Customs Operations MCP Server

A [FastMCP](https://github.com/jlowin/fastmcp) server that gives an agent read access to the Campus Customs shop database. It exposes three tools, one per open ticket in the `tickets` table, so an agent can verify a request against the shop's own records before acting on it.

Server name: `campus-customs-ops` · File: [`server.py`](server.py)

## Which database it uses

| File | Used by this server? |
|---|---|
| `data/campus_customs_new.db` | **Yes — this is the only file the server opens.** |
| `data/campus_customs.db` | **No. Never opened.** It stays as the untouched original. |

The path is set once at the top of `server.py`:

```python
DB_PATH = HW_ROOT / "data" / "campus_customs_new.db"
```

Every query in every tool goes through `_connect()`, which uses that one constant — there is no second path and no way for a tool to reach the original. If the working copy is missing, the server refuses to start rather than falling back to the original.

All three tools are **read-only**: they issue `SELECT` statements only, so running them leaves the working copy byte-identical.

## Design rule: nothing is invented

Each tool returns values that came out of the database, plus arithmetic on those values (totals, shortfalls, margins, days-until-due). No averages, estimates, defaults or placeholder vendors. When a row does not exist the tool returns `"found": false` with a message saying what was missing, rather than guessing. Vendor choice is deliberately left to the agent: `quote_bulk_order` reports every vendor's `specialty` and `lead_days` as stored and assumes no sku-to-vendor mapping.

One more deliberate choice: the shop's "today" comes from `desk.date_today` (currently `2026-08-31`), never from the system clock, so every overdue/due-soon judgment matches the scenario.

## The tools

Fifteen tools: ten that read the shop's records, four that change them, and one that belongs to the human operator alone. Each write tool carries a guard the model cannot argue its way past.

### Read tools

| Tool | Tables read | What it is for |
|---|---|---|
| `get_shop_date` | `desk` | The shop's working date. Every deadline judgment is made against this, never the system clock. |
| `list_open_tickets` | `tickets`, `desk` | The work queue. |
| `get_ticket` | `tickets` + whichever of `inventory`, `pricing`, `leases`, `invoices`, `vendors` it links to, `desk` | Resolves a ticket's foreign keys so the request and its supporting records arrive together. |
| `check_item_availability` | `inventory`, `pricing`, `desk`, `tickets`→`invoices`→`vendors` | Can this order be filled now, and is a reprint already on order for it? |
| `verify_rent_due` | `leases`, `desk`, `payments`, `cash_accounts`, `invoices`→`vendors` | Checks a rent demand against the signed lease and the balance left after paying. |
| `quote_bulk_order` | `pricing`, `inventory`, `vendors`, `desk` | Margin floor and supply position for a discount request. |
| `list_vendors` | `vendors`, `desk` | Specialties and lead times, for turning a shortfall into a date. |
| `list_unpaid_invoices` | `invoices`, `vendors`, `desk` | What is already owed, flagged overdue. |
| `get_cash_balance` | `cash_accounts`, `invoices`, `leases`, `desk` | Balance, what is committed against it, and what is genuinely uncommitted. |
| `list_payment_approvals` | `approvals`, `desk` | Where a staged payment stands. |

### Write tools

| Tool | Tables written | Guard |
|---|---|---|
| `request_payment_approval` | `approvals` (status `pending`) | Does **not** pay. Refuses outright if the account is unknown or the balance will not cover the amount, so an unaffordable payment never even reaches the operator. |
| `record_approved_payment` | `payments`, `cash_accounts`, `invoices`, `leases`, `approvals` | Refuses unless the approval's status is exactly `approved`, it is unpaid, and the balance covers it. |
| `adjust_inventory` | `inventory`, `inventory_adjustments` | Refuses any change that would take stock below zero. |
| `update_ticket_status` | `tickets` | Status must be one of `open`, `resolved`, `blocked`, `awaiting_approval`; the note is appended, never overwritten. |
| `draft_customer_message` | `message_drafts` (always `sent = 0`) | The server has no email, SMS or phone capability. Messages are stored for a human; nothing is transmitted. |

### Operator-only tool

| Tool | Tables written | Guard |
|---|---|---|
| `record_human_decision` | `approvals` (`approved` / `rejected`) | Requires the operator token from `CAMPUS_CUSTOMS_HUMAN_TOKEN`, which the runner generates per run and never puts in a prompt; it is withheld from every agent's toolset; and it refuses any decision attributed to an agent name even when the token is valid. There is no automatic approval path anywhere — a run with no human at a terminal leaves every payment `pending`. |

### Tables this server adds

Three tables are created in the working copy on first connect, alongside the shop's originals:

- **`approvals`** — the payment gate: who asked, for how much, why, and what the human decided.
- **`message_drafts`** — replies written but never sent, with a `sent` flag that is always 0.
- **`inventory_adjustments`** — every stock change, with the reason and the agent that made it.

### Verified guard behaviour

Each guard was tested by calling the tool directly and trying to break it:

| Attempt | Result |
|---|---|
| Stage a payment larger than the balance | `Refused: $2,000.00 exceeds the $1,000.00 available in 'checking'. The shop cannot go cash-negative.` |
| Agent approves its own payment with a guessed token | `Refused: invalid operator token. Only the human operator can approve or reject a payment.` |
| Approval attributed to an agent, with a **valid** token | `Refused: 'boss' is an agent, not a person. A payment approval must be attributed to the human who authorized it.` |
| Pay an approval no human decided | `Refused: approval 2 is 'pending', not 'approved'.` |
| Ship stock the shop does not have | `Refused: 0 on hand, so a change of -5 would leave -5. Stock cannot go negative.` |
| Send a message | Returns `sent: False` — there is no send path to take. |

The cash balance was unchanged after every attempt.

## Setup

From the HW5 folder:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

`requirements.txt` pins `cryptography==48.0.1`, which has a prebuilt wheel for this machine's Python 3.14 — without the pin, pip tries to compile a newer cryptography from source and fails on a missing OpenSSL.

## Running

```bash
# stdio (how an MCP client normally launches it)
.venv/bin/python mcp_server/server.py

# HTTP, for manual poking
.venv/bin/python mcp_server/server.py --http --port 8000
```

The connection is registered as `campus-customs-ops` in `.mcp.json` at the HW5 root and at the course repo root. The agent team in `backend/` launches the server from that same file, so there is one description of the connection, not two.
