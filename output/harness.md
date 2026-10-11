# Campus Customs Harness

Reference notes on the Campus Customs operations database, built for the multi-agent operations work in HW5. This file grows as later problems are completed.

## Database files

| File | Role |
|---|---|
| `data/campus_customs.db` | **Original. Never modified.** Clean baseline for comparison or restore. |
| `data/campus_customs_new.db` | **Working copy. All agent writes go here.** |

The working copy was made with a byte-for-byte copy of the original; both files currently hash identically (`f447ca6a…`). Every database change in this and later problems targets `campus_customs_new.db` only.

## Database map

Nine tables. Three cover what the shop sells (`inventory`, `pricing`, `vendors`), three cover its money (`cash_accounts`, `invoices`, `payments`), one covers its space (`leases`), one sets the clock (`desk`), and one holds the work to be done (`tickets`).

### desk

| Field | Type | Notes |
|---|---|---|
| `date_today` | TEXT | The shop's "today" — `2026-08-31` |
| `notes` | TEXT | Free-text scratch space; currently empty |

**Why it matters for the agents:** this is their clock — every "overdue" or "due soon" judgment must be made against `date_today`, not the real system date.

### inventory

| Field | Type | Notes |
|---|---|---|
| `sku` | TEXT | Product code; part of the primary key |
| `name` | TEXT | Human-readable product name |
| `size` | TEXT | `S`/`M`/`L`/`XL` for apparel, `OS` for one-size goods; part of the primary key |
| `qty` | INTEGER | Units on hand for that exact sku + size |
| `location` | TEXT | Aisle where the item is stocked |

**Why it matters for the agents:** it decides whether an order can be filled now, needs a reprint, or must be refused — and because the key is (sku, size), stock is per size, not per product.

Current state: `CC-TEE-WHITE`/`S` = **0**, `CC-MUG-CREST`/`OS` = **0**, `CC-HOOD-NAVY`/`M` = **8**.

### pricing

| Field | Type | Notes |
|---|---|---|
| `sku` | TEXT | Primary key; one row per product, not per size |
| `unit_cost` | REAL | What the shop pays per unit |
| `list_price` | REAL | Standard sticker price per unit |

**Why it matters for the agents:** it is the margin floor — a discount request is only safe to approve if the proposed price still clears `unit_cost`.

### vendors

| Field | Type | Notes |
|---|---|---|
| `id` | INTEGER | Primary key; referenced by `invoices.vendor_id` |
| `name` | TEXT | Vendor name |
| `specialty` | TEXT | apparel reprint / mugs and small goods / local courier |
| `lead_days` | INTEGER | Days from order to delivery |

**Why it matters for the agents:** when stock is short, `specialty` picks the right supplier and `lead_days` converts into the date the agent can promise a customer.

### leases

| Field | Type | Notes |
|---|---|---|
| `id` | INTEGER | Primary key; referenced by `tickets.lease_id` |
| `space_name` | TEXT | Which space |
| `landlord` | TEXT | Who gets paid |
| `monthly_rent` | REAL | Amount owed each month |
| `next_due` | TEXT | Date the next rent payment is due |
| `notes` | TEXT | Free text; currently empty |

**Why it matters for the agents:** it is how a rent demand gets verified against the contract instead of being taken on trust from an email.

### cash_accounts

| Field | Type | Notes |
|---|---|---|
| `name` | TEXT | Primary key; account name (`checking`) |
| `balance` | REAL | Funds available |
| `date` | TEXT | As-of date for the balance |

**Why it matters for the agents:** it is the spending ceiling — no payment should be approved that the balance cannot cover, or that leaves another obligation unpayable. Current: **$3,400** as of 2026-08-31.

### payments

| Field | Type | Notes |
|---|---|---|
| `id` | INTEGER | Primary key |
| `kind` | TEXT | What is being paid (rent, invoice, …) |
| `ref_id` | INTEGER | Points at the `leases.id` or `invoices.id` being settled |
| `amount` | REAL | Amount paid |
| `account` | TEXT | Which cash account it came from |
| `paid_at` | TEXT | Timestamp of payment |
| `approved_by` | TEXT | Who authorized it |

**Why it matters for the agents:** it is the audit trail every money action must write to, and `approved_by` is what makes a payment reviewable after the fact. Currently **empty — nothing has been paid yet.**

### invoices

| Field | Type | Notes |
|---|---|---|
| `id` | INTEGER | Primary key; referenced by `tickets.invoice_id` |
| `vendor_id` | INTEGER | FK → `vendors.id` |
| `amount` | REAL | Amount owed |
| `due_date` | TEXT | When it is due |
| `status` | TEXT | `open` / paid |
| `description` | TEXT | What the invoice covers |

**Why it matters for the agents:** it is the payables queue. Invoice **501 — $840, due 2026-08-28, still `open`** — is already past `desk.date_today`, so reading these two tables together flags it as overdue.

### tickets

| Field | Type | Notes |
|---|---|---|
| `id` | INTEGER | Primary key |
| `type` | TEXT | `customer_order`, `rent_notice`, `price_override` |
| `requester` | TEXT | Who is asking |
| `subject` | TEXT | Short summary |
| `sku` / `size` / `qty` | TEXT / TEXT / INTEGER | Product being asked about; null on non-product tickets |
| `lease_id` | INTEGER | FK → `leases.id`; set on rent tickets |
| `invoice_id` | INTEGER | FK → `invoices.id`; set when an invoice is involved |
| `status` | TEXT | `open` / resolved |
| `notes` | TEXT | The request in plain language |
| `created_at` | TEXT | Timestamp with timezone offset |

**Why it matters for the agents:** it is their inbox and the entry point of every run — `type` routes the ticket to the right specialist, and the nullable foreign keys are what let an agent pull the supporting facts needed to verify a request rather than acting on its wording alone.

## The three open tickets and how they connect

All three are `status = open` and were created on 2026-08-31, the same day as `desk.date_today`.

### Ticket 101 — `customer_order`, Tauhid Zaman, "Bulldog tee"

Wants 1 × `CC-TEE-WHITE`, size `S`.

| Connects to | Via | What it reveals |
|---|---|---|
| `inventory` | (`CC-TEE-WHITE`, `S`) | **qty = 0** — cannot be filled from stock |
| `invoices` | `invoice_id = 501` | $840 rush reprint of exactly this sku + size, still `open` and already overdue |
| `vendors` | invoice 501 → `vendor_id = 1` | Bulldog Print Co, apparel reprint, **5 `lead_days`** |
| `pricing` | `CC-TEE-WHITE` | cost $8, list $28 |
| `payments` | *(none yet)* | the reprint has not been paid for |

The order, the empty shelf, the unpaid reprint and the vendor lead time are one connected story: the fix is already in flight but unfunded, and the vendor's 5 lead days is what sets the customer's promise date.

### Ticket 102 — `rent_notice`, Elm City Properties, "Rent due"

No sku, size or qty.

| Connects to | Via | What it reveals |
|---|---|---|
| `leases` | `lease_id = 1` | Chapel Street shop, **$2,400/month**, `next_due = 2026-09-02` |
| `cash_accounts` | the account rent is drawn from | checking, **$3,400** |
| `payments` | *(none yet)* | rent is unpaid; paying it would write the first `payments` row |

The ticket claims rent is due "in 2 days," which matches 2026-08-31 + 2 = 2026-09-02 in the lease row — so the demand verifies against the contract.

### Ticket 103 — `price_override`, Yale AI Club, "Bulk hoodie discount"

Wants 20 × `CC-HOOD-NAVY`, size `M`, at a bulk discount.

| Connects to | Via | What it reveals |
|---|---|---|
| `inventory` | (`CC-HOOD-NAVY`, `M`) | **8 on hand** — 12 short of the 20 requested |
| `pricing` | `CC-HOOD-NAVY` | cost **$22**, list **$58** — the margin band any discount is judged against |
| `vendors` | would route to vendor 1 (apparel reprint) | 5 lead days to cover the 12-unit shortfall |
| `invoices` / `payments` | `invoice_id` is null | nothing has been ordered or committed yet |

Two separate questions in one ticket: *can we supply 20?* (no, not from stock) and *at what price?* (anything above $22/unit keeps the shop above cost).

### The squeeze the three tickets create together

Cash is **$3,400**. Rent is **$2,400** due 2026-09-02 and invoice 501 is **$840** already overdue — **$3,240 of obligations against $3,400 on hand, leaving $160 of headroom** — before any reprint is ordered to cover ticket 103's 12-unit shortfall or to restock the sold-out tee.

The tickets are not independent. They compete for the same balance, and that contention is the core tension the agents have to reason about.

## MCP server and tools

The MCP server lives in [`mcp_server/server.py`](../mcp_server/server.py) (FastMCP, server name `campus-customs-ops`) and is documented in [`mcp_server/README.md`](../mcp_server/README.md). It opens **`data/campus_customs_new.db` only** — the original `data/campus_customs.db` is never touched. Every tool takes the shop's "today" from `desk.date_today` rather than the system clock.

It is the single gateway to the shop: no agent opens the database, and no shop fact reaches a prompt except as a tool result.

### Read tools

| Tool | Tables it reads | Ticket it helps resolve | Why it is useful |
|---|---|---|---|
| `get_shop_date` | `desk` | all | Supplies the only date the shop recognises, so "overdue" and "due in 2 days" mean something fixed. |
| `list_open_tickets` | `tickets`, `desk` | all | The work queue the run starts from. |
| `get_ticket` | `tickets` + linked `inventory`, `pricing`, `leases`, `invoices`, `vendors`, `desk` | all | Resolves a ticket's foreign keys in one call, so an agent judges the request against its supporting records instead of its wording. |
| `check_item_availability` | `inventory`, `pricing`, `desk`, `tickets`→`invoices`→`vendors` | **101**, 103 | Shows the shelf is empty **and** that a reprint for that exact item is already invoiced, overdue and 5 days out — preventing a duplicate order. |
| `verify_rent_due` | `leases`, `desk`, `payments`, `cash_accounts`, `invoices`→`vendors` | **102** | Checks an emailed rent demand against the signed lease and the payments log before any money moves. |
| `quote_bulk_order` | `pricing`, `inventory`, `vendors`, `desk` | **103** | Splits a discount request into its two real questions: can we supply 20, and does the asked price clear cost. |
| `list_vendors` | `vendors`, `desk` | 101, 103 | Turns a shortfall into a date: shop date plus that vendor's `lead_days`. |
| `list_unpaid_invoices` | `invoices`, `vendors`, `desk` | 101, 102, 103 | The claims already standing against the cash, before anything new is spent. |
| `get_cash_balance` | `cash_accounts`, `invoices`, `leases`, `desk` | 102, 103 | Splits obligations into **due now** and **upcoming**, each with its date, so free cash is reported by horizon rather than as one lump. |
| `list_tickets` | `tickets`, `desk` | all | The whole board including resolved tickets, with a count per status. Dashboard-facing; the agents' queue is `list_open_tickets`. |
| `list_payment_approvals` | `approvals`, `desk` | 102 | Lets an agent see whether the operator has decided a staged payment. |

### Write tools

| Tool | Tables it writes | Ticket | Why it is useful |
|---|---|---|---|
| `request_payment_approval` | `approvals` | **102**, 103 | The only way to start a payment. Records a pending request and stops — money never moves on an agent's say-so. |
| `record_approved_payment` | `payments`, `cash_accounts`, `invoices`, `leases`, `approvals` | **102** | Settles a payment the human approved, decrements cash, marks the invoice paid or rolls `next_due` forward. |
| `adjust_inventory` | `inventory`, `inventory_adjustments` | 101, 103 | Reserves, ships or receives stock, with the reason and the agent recorded. |
| `update_ticket_status` | `tickets` | all | Closes the loop: a decision that is not written here did not happen. |
| `draft_customer_message` | `message_drafts` | **101**, **103** | Writes the reply and stores it unsent, which is how "never contact customers or vendors" is enforced rather than promised. |

### Operator-only tool

| Tool | Tables it writes | Why it exists |
|---|---|---|
| `record_human_decision` | `approvals` | Approves or rejects a staged payment. Requires the operator token, which the runner generates and never places in a prompt, and is withheld from every agent's toolset. |

### Tables the agent workflow adds

Created in the working copy on first connect, alongside the shop's originals:

- **`approvals`** — `id`, `kind`, `ref_id`, `amount`, `account`, `reason`, `requested_by`, `ticket_id`, `status`, `requested_at`, `decided_by`, `decided_at`, `payment_id`. The payment gate.
- **`message_drafts`** — `id`, `ticket_id`, `audience`, `recipient`, `subject`, `body`, `drafted_by`, `created_at`, `sent`. `sent` is always 0.
- **`inventory_adjustments`** — `id`, `sku`, `size`, `delta`, `qty_after`, `reason`, `changed_by`, `changed_at`, `ticket_id`. Every stock change and why.

## The agent team

Five PydanticAI agents, all on **`gpt-6-luna` through the Portkey gateway** with `PORTKEY_API_KEY`, built in [`backend/`](../backend/). The key is read from the project `.env` and never printed, logged or placed in a prompt.

The Responses endpoint is used rather than chat completions: this gateway rejects function tools on chat completions when reasoning is enabled, and every agent here has tools.

| Agent | Prompt | MCP tools it can see | Tables reached | Role |
|---|---|---|---|---|
| **Boss** | [`boss.md`](../backend/prompts/boss.md) | `get_shop_date`, `get_ticket`, `list_open_tickets`, `get_cash_balance`, `update_ticket_status`, `list_payment_approvals` + the four delegation tools | `tickets`, `desk`, `cash_accounts`, `approvals` | Owns the ticket. Delegates, decides, records the outcome. |
| **Inventory** | [`inventory.md`](../backend/prompts/inventory.md) | `check_item_availability`, `list_vendors`, `list_unpaid_invoices`, `adjust_inventory` + context reads | `inventory`, `pricing`, `vendors`, `invoices`, `inventory_adjustments` | Stock on hand, shortfalls, reprints already on order, lead times. |
| **Accounting** | [`accounting.md`](../backend/prompts/accounting.md) | `get_cash_balance`, `list_unpaid_invoices`, `quote_bulk_order`, `verify_rent_due`, `request_payment_approval`, `list_payment_approvals`, `record_approved_payment` + context reads | `cash_accounts`, `invoices`, `pricing`, `payments`, `approvals` | Cash, obligations, margin. Stages payments; cannot approve them. |
| **Facilities** | [`facilities.md`](../backend/prompts/facilities.md) | `verify_rent_due`, `get_cash_balance`, `request_payment_approval`, `list_payment_approvals` + context reads | `leases`, `payments`, `cash_accounts`, `approvals` | Verifies a rent demand against the lease on file. |
| **Customer Service** | [`customer_service.md`](../backend/prompts/customer_service.md) | `check_item_availability`, `list_vendors`, `draft_customer_message` + context reads | `inventory`, `vendors`, `message_drafts` | Writes the reply. Has no tool that moves money or stock. |

Every agent also receives [`_shop_rules.md`](../backend/prompts/_shop_rules.md), the eight house rules, appended to its own prompt.

### How they communicate

Delegation runs in all three directions, so work does not have to funnel through the Boss.

**Down — Boss to specialist.** The Boss calls `ask_inventory`, `ask_accounting`, `ask_facilities` or `ask_customer_service`. Each runs that specialist as a nested agent and returns a typed `SpecialistReport` — summary, findings, actions taken, whether human approval is needed, and a blocked reason if it could not finish.

**Sideways — specialist to specialist.** Every specialist has `consult_colleague(colleague, question)` and can go straight to a peer. Inventory can ask Accounting whether a reprint is affordable before recommending it; Customer Service can ask Inventory to confirm an arrival date before putting it in writing. The consulting agent stays responsible for its own answer and folds the reply into its findings rather than forwarding it.

**Up — specialist to Boss.** Every specialist also has `escalate_to_boss(question, why_you_cannot_decide)`, for a judgement that is not theirs to make: which of two competing claims on the shop's cash wins, or which of two defensible options to take. It is for decisions, not lookups — a specialist has its own tools for facts.

Escalation needed its own path rather than reusing `consult_colleague`, because the cycle guard refuses anyone already in the active chain and the Boss sits at the root of every chain — which made the Boss the one colleague nobody could call.

What keeps that safe is **`boss_advisor`**: the same Boss prompt and the same view of the shop, but built with **no delegation tools at all**. A Boss answering an escalation cannot reply "ask Inventory" by actually asking Inventory — which would be the agent that just escalated. So an escalation ends in a decision rather than a volley, structurally rather than by instruction.

Tool access is least-privilege by design. Customer Service has no payment tool, so it cannot spend money however it is prompted; Inventory has no approval tool; no agent at all is given `record_human_decision`.

Shared types live in [`backend/models.py`](../backend/models.py): `SpecialistReport`, `TicketResolution`, `AuditStep`, `RunRecord`.

## Backend API

FastAPI, in [`backend/main.py`](../backend/main.py). Started from the `backend/` folder:

```bash
uvicorn main:app --reload --port 8000
```

The dashboard never touches the database, the agents or the model directly — every route goes through the MCP server, which is where the shop's rules are enforced. Interactive docs are at `/docs`.

| Route | What it does |
|---|---|
| `GET /api/health` | Liveness, the model in use, which database is live, and the active limits. |
| `GET /api/tickets` | Every ticket with its current status, plus a count per status. Optional `?status=`. |
| `GET /api/tickets/{id}` | One ticket with its linked lease, invoice, vendor, inventory and pricing records. |
| `POST /api/runs` | Runs the agent team on `{"ticket_ids": [...]}`, or every open ticket if omitted. Returns a `run_id` immediately; the work happens in the background. |
| `GET /api/runs/{run_id}` | Status, resolutions and token usage for one run — what the dashboard polls. |
| `GET /api/runs` | Every run started since the server booted. |
| `GET /api/activity` | Recent agent activity from the audit trail: who ran, who delegated to whom, which MCP tool was called with what arguments. Optional `?limit=` and `?run_id=`. |
| `GET /api/approvals` | Payments the agents staged and the decision on each. Nothing listed here has moved money. |
| `POST /api/approvals/{id}/decision` | **The human in the loop.** A person approves or rejects a staged payment; only on approval is it settled. |
| `GET /api/cash` | Cash balance, what is committed against it, and what is genuinely uncommitted. |
| `POST /api/reset` | Restores the working database from the untouched original, for a clean run. |

### How the rules survive the HTTP layer

**No agent can be paid without a person.** `POST /api/runs` cannot approve anything — a run that stages a payment ends with it `pending`. The operator token is generated once per process, placed only in the MCP server's environment, and returned by no route, so the only way a decision can carry it is for a person to have posted to the decision route. That route also requires an `authorized_by` name, and the MCP server rejects agent names even with a valid token.

**Cash cannot go negative.** Checked twice, both inside the MCP server: once when the payment is staged, and again at settlement against the live balance. An approval granted for more than the shop holds is still refused, and the route returns 409.

**The reset only ever touches the copy.** `POST /api/reset` copies `data/campus_customs.db` onto `data/campus_customs_new.db` and never the reverse; the original is opened for reading only. Deliberately *not* an MCP tool — a reset tool on that server would be a wipe button sitting next to the agents. Here it lives behind an HTTP route they cannot reach.

### Verified against a running server

Started with the exact command above and every route exercised:

| Check | Result |
|---|---|
| `GET /api/tickets` | all three returned, `{"open": 3}` |
| `GET /api/cash` | $3,400 balance, $3,240 committed, **$160 uncommitted** |
| `POST /api/runs` `[102]` | finished in 8s; ticket 102 → `awaiting_approval`, 21 requests, 72,121 tokens |
| money moved during that run | **none** — `payments` empty, balance still $3,400, approval 1 `pending` |
| `GET /api/activity` | returned the staging sequence: `accounting → request_payment_approval → approval_requested` |
| approve as `"accounting"` | **refused** — *"'accounting' is an agent, not a person"* |
| approve as a named person | paid: payment 1, $2,400, balance $3,400 → **$1,000**, `next_due` rolled to 2026-10-02, ticket 102 → `resolved` |
| approving the same one twice | **409** — *"Approval 1 is already 'paid'"* |
| `POST /api/reset` | cash $1,000 → $3,400, payments cleared, all three tickets back to `open` |
| original database after reset | still hashes `f447ca6a…` — **unchanged** |
| unknown ticket / approval | 404 |

## Dashboard

React + Vite + TypeScript, in [`frontend/`](../frontend/). Design decisions are written up in [`design.md`](design.md).

```bash
# backend first, from backend/
uvicorn main:app --reload --port 8000
# then, from frontend/
npm run dev          # http://localhost:5173, already allowed by the API's CORS
```

The API base defaults to `http://localhost:8000` and can be overridden with `VITE_API_BASE`. Every figure on screen comes from a backend response — there are no fixtures, no placeholder numbers and no optimistic updates.

| Panel | Source | Shows |
|---|---|---|
| Tickets | `GET /api/tickets` | all three with live status, selectable for a run |
| Agent activity | `GET /api/activity?ticket_id=&run_id=` | the audit trail as a conversation, one colour per agent — **scoped to one ticket within one run** |
| The team | same scoped steps | each agent's tool calls, handoffs and reports for that ticket and run only; an unused agent reads as idle rather than zeroed |
| Needs a human | `GET /api/approvals` + `POST /api/approvals/{id}/decision` | staged payments; approving requires typing a name |
| Checking | `GET /api/cash` | uncommitted cash as the headline, with the balance split into rent, invoices and free |
| Latest run | `POST /api/runs`, `GET /api/runs/{id}` | outcomes, delegations, drafts, token usage |
| Reset shop | `POST /api/reset` | restores the working copy; the original is never touched |

### Resolution is earned, not bought

A cleared payment does **not** resolve a ticket. When a human approves a payment the money moves, the payment is recorded, and the ticket returns to **`open`** with a note saying what was paid and that the team still needs to confirm nothing else is outstanding. Only the Boss, on a later run, can set `resolved`.

Paying rent is one piece of work finishing — the customer may still be owed a reply, stock may still need adjusting. Verified end to end: ticket 102 went `awaiting_approval` → payment approved ($3,400 → $1,000) → **`open`** → re-run → `resolved`.

### Verified

| Check | Result |
|---|---|
| `npm run dev` | Vite serves on 5173; every module compiles (no 500s from the transform pipeline) |
| `tsc --noEmit` and `npm run build` | clean, 0 errors |
| CORS preflight from `http://localhost:5173` | `access-control-allow-origin: http://localhost:5173` |
| run ticket 101 from the dashboard route | finished, `blocked`, 52,762 tokens, reply drafted unsent |
| run ticket 102, approve, re-run | `awaiting_approval` → `open` after payment → `resolved` on confirmation |
| payment timestamp | `payments.paid_at` now carries the **shop date** (2026-08-31), not the wall clock |
| activity scoping | unfiltered trail: 429 steps, 9 runs, 3 tickets. Scoped to ticket 101 + its run: **36 steps, 1 run, 1 ticket**. Ticket 101 against the wrong run: **0 steps** |

## Results — the three tickets worked end to end

A clean start: `data/campus_customs_new.db` restored from the untouched original, checking at **$3,400.00**, `payments` empty, all three tickets `open`.

Five agent runs, **255,707 tokens**, one human approval.

| Ticket | Final status | Outcome | Money |
|---|---|---|---|
| 101 — Bulldog tee | `blocked` | Size S at 0; invoice 501 records no quantity, receipt or ETA, so no date could honestly be promised. Two reply drafts saved, unsent. | none |
| 102 — Rent due | `resolved` | Verified against lease 1, staged, **approved by a person**, paid, then confirmed resolved on a second run. | **−$2,400.00** |
| 103 — Bulk hoodie discount | `resolved` | 10% discount at **$52.20**/unit — above the $22 cost floor. 8 on hand, 12 short, nothing reserved or ordered. Draft saved, unsent. | none |

Full records: [`resolved_tickets.json`](resolved_tickets.json), [`desk_tickets.html`](desk_tickets.html) (Expected vs Actual per ticket, plus the Cash tab), [`resolved_board.html`](resolved_board.html) (dashboard screenshots), [`audit_trail.json`](audit_trail.json).

### Cash, reconciled against the database

| Line | Source | Amount |
|---|---|---|
| Starting balance | `cash_accounts`, after reset | $3,400.00 |
| Rent, ticket 102 | `payments.id = 1` | −$2,400.00 |
| **Computed ending balance** | | **$1,000.00** |
| **Ending balance in the database** | `SELECT balance FROM cash_accounts` | **$1,000.00** |

$3,400.00 − $2,400.00 = $1,000.00. **The arithmetic matches the database.** Cash never went negative. Still outstanding: invoice 501 at $840 (overdue) and October rent at $2,400 (not yet due) — leaving **$160.00 free** after what is already due.

### What the runs demonstrated

- **The human gate held.** The only payment was staged by Accounting and stopped there. It cleared only after an explicit authorization, recorded in both `approvals.decided_by` and `payments.approved_by` as a person's name. No agent approved anything.
- **A payment did not resolve its ticket.** After the rent cleared, ticket 102 returned to `open`; it took a second run, where the Boss confirmed nothing remained, to reach `resolved`.
- **Agents delegated to each other.** Inventory went straight to Accounting on both tickets 101 and 103 — peer handoffs with no Boss in between.
- **Verification caught a discrepancy.** Facilities reported that lease 1's `next_due` is 2026-10-02, not the 2026-09-02 the landlord's email implied.
- **Nothing was sent.** Three drafts were written, all with `sent = 0`.
- **A ticket was allowed to stay unfinished.** Ticket 101 came back `blocked` on two consecutive runs because the database records no ship date for the reprint. It is reported as blocked rather than forced to `resolved` — marking it complete would have been a claim without evidence.
- **The original database is unchanged**, still hashing `f447ca6a…`.

### One defect the agents found

On the confirmation run for ticket 102, the Boss flagged that payment 1's timestamp was *after* the shop date and said the two were "chronologically inconsistent". It was right: `payments.paid_at` was being stamped with the real wall clock while the rest of the ledger runs on the shop calendar. Fixed — `paid_at` now carries `desk.date_today`.

## Safety and limits

### The shop rules, and where each is actually enforced

A rule that lives only in a prompt is a request. These are enforced in the server, where the model cannot reach them.

| Rule | Enforcement |
|---|---|
| Use the shop's date | Every tool reads `desk.date_today` and returns it as `as_of_date`. Agents are never given a date to assume. |
| Check vendor lead times | `check_item_availability`, `list_vendors` and `quote_bulk_order` all return `lead_days` with the vendor it belongs to. |
| Check unpaid invoices | `get_cash_balance` reports commitments beside the balance; `list_unpaid_invoices` and `verify_rent_due` surface what is owed. |
| Human approval for every payment | Four independent barriers; see **The payment gate** below. |
| Never go cash-negative | Checked twice: at request time and again at payment time, against the live balance. |
| Never contact customers or vendors | The server has no email, SMS or phone capability. `draft_customer_message` writes a row with `sent = 0`; there is no send path to take. |
| Never invent information | Every tool returns database values plus arithmetic on them. A missing row returns `found: false` with a message rather than a default. No sku-to-vendor mapping is assumed — `quote_bulk_order` lists all vendors and lets the agent choose. |

### The payment gate

No payment can be approved by anything other than a person typing an authorization. There is no flag, threshold, policy or default that approves a payment, and a run with no terminal leaves every payment pending.

Four barriers, each independent of the others:

1. **Agents cannot see the tool.** `record_human_decision` is in no agent's `TOOLS_FOR` entry. It is not something an agent declines to call — it does not exist in its toolset.
2. **The token.** The tool requires `CAMPUS_CUSTOMS_HUMAN_TOKEN`, generated per run by the runner, passed only into the MCP server's environment, and stripped from the audit trail before anything is logged. It never enters a prompt, so there is nothing for a model to repeat back.
3. **An agent's name is not a person.** Even with a valid token, a decision attributed to `boss`, `accounting` or any other agent is refused. This should be unreachable given barrier 2; it is there so that if it ever is reached, it fails closed.
4. **Payment re-checks the decision.** `record_approved_payment` refuses unless the approval's status is already exactly `approved`, it is unpaid, and the balance covers it.

At the terminal, the operator sees the amount, account, requester and reason, and must type `approve` — not `y`, which is too easy to hit by reflex for a key that moves the shop's money. Any other answer, an empty line, a closed stdin or no terminal at all leaves the payment `pending`.

#### Verified

[`backend/test_payment_approval.py`](../backend/test_payment_approval.py) runs every route an agent could take, against the live server, and restores the database afterwards. **12 checks, all passing:**

```
[PASS] record_human_decision appears in no agent's toolset
[PASS] staging a payment leaves it pending and pays nothing
[PASS] agent cannot pay an approval no human decided
         -> Refused: approval 2 is 'pending', not 'approved'.
[PASS] agent cannot approve without the operator token
         -> Refused: invalid operator token.
[PASS] a decision attributed to an agent is refused even with a valid token
         -> Refused: 'boss' is an agent, not a person.
[PASS] the approval is still pending after every attempt
[PASS] the runner has no auto-approve flag or threshold
[PASS] approval requires typing an explicit phrase
[PASS] no terminal means the payment is left pending
[PASS] a named human with the token can approve
[PASS] payment only clears after that human decision   -> balance 3400.0 -> 3375.0
[PASS] cash moved by exactly the approved amount, and only then
```

An end-to-end run with no human present confirms the same thing from the outside: the team staged the $2,400 rent payment, the runner printed it and left it `pending`, and the `payments` table stayed **empty** with checking still at **$3,400**.

### Loop and token limits

Delegation that runs sideways and upward is what makes a cycle reachable — Inventory asks Accounting, which asks Inventory back; or the Boss and a specialist volleying one question. The brakes below are what let the team talk freely.

| Limit | Value | Why |
|---|---|---|
| `request_limit` | 40 per ticket | A ticket needing more than 40 model calls is looping, not working. |
| `tool_calls_limit` | 60 per ticket | Catches a tool-call loop that is not burning requests. |
| `total_tokens_limit` | 400,000 per ticket | Hard spend ceiling. |
| `MAX_DELEGATIONS_PER_TICKET` | 10 | Every delegation counts — down, sideways or up. |
| `MAX_PEER_CONSULTS_PER_TICKET` | 5 | Capped separately, so two chatty colleagues cannot eat a ticket. |
| `MAX_BOSS_ESCALATIONS_PER_TICKET` | 3 | A specialist escalating three times on one ticket is stuck, not thorough. |
| `MAX_CHAIN_DEPTH` | 3 | `boss → specialist → peer`. A consultation cannot spawn its own. |
| Cycle protection | — | An agent already in the active chain cannot be consulted again. Escalation is exempt, because the Boss is always at the root — and is made safe instead by `boss_advisor` having no delegation tools. |
| `SPECIALIST_REQUEST_LIMIT` | 12 **additional** requests | A specialist is a leaf and should not need more. |

The three budgets are independent: spending the peer cap does not block the Boss's own delegations, nor an escalation.

The budget is **per ticket, shared by the Boss and every agent it reaches** — nested runs receive the same `RunUsage`, so a chatty specialist spends the ticket's allowance rather than getting a fresh one. The specialist cap is expressed relative to what the ticket has already spent; an absolute cap would have meant the second specialist on a ticket starting over the line before making a single call.

Every brake **refuses with an explanation and lets the run continue**, rather than raising. A refused agent is told to answer with what it has and report back, so a loop ends in a decision instead of a crash.

The active chain is tracked in a `ContextVar`, not on the shared deps object: the Boss can delegate to two specialists at once, and asyncio copies the context into each task, so the branches cannot corrupt each other's chain.

#### Verified

The guards are a pure function, `check_delegation` in [`backend/agents.py`](../backend/agents.py), so every refusal path is tested without a model call — [`backend/test_delegation_guards.py`](../backend/test_delegation_guards.py), **18 cases, all passing**:

```
[PASS] CYCLE: consulting someone already in the chain
         -> Refused: accounting is already working above you in this chain
            (boss -> accounting -> inventory), so consulting it would loop...
[PASS] CYCLE: consulting the agent two levels up
[PASS] SELF: an agent delegating to itself
[PASS] DEPTH: chain already at the maximum
[PASS] UNKNOWN: no such agent
[PASS] ESCALATE: specialist hands a question back to the Boss
[PASS] ESCALATE: from inside a peer consultation
[PASS] ESCALATE: refused once the chain is at maximum depth
[PASS] delegation cap reached   [PASS] peer cap reached   [PASS] escalation cap reached
[PASS] peer cap does not block the Boss
[PASS] peer cap does not block escalation
```

Both new directions were then exercised against the live model:

- **Sideways.** Inventory was asked to check stock on ticket 103 and consult Accounting directly. It did, with no Boss involved — trail entry `inventory -> accounting (peer)`, `chain=['boss','inventory']` — and reported that the 12-unit shortfall costs $264 against a $160 balance, so it is unaffordable.
- **Upward.** Accounting was given a trade-off it could not settle and escalated. The Boss answered with a decision, not a referral: *"protect the next rent commitment and decline/defer funding the shortfall… $160 checking − $2,400 next rent = −$2,240 uncommitted; the shortfall would cost $264."* Trail entry `accounting -> boss (escalation)`, `escalation=True`.

### Audit trail

[`output/audit_trail.json`](audit_trail.json) is a JSON array of run records, **appended to, never overwritten**. Each run records its id, model, shop date, limits, tickets handled, resolutions, every step, and total usage.

A step is written for every agent start and finish, every delegation, every MCP tool call and its result, every approval request, every human decision, and every limit hit or error. Steps are flushed to disk as they happen, so a run that hits a limit or crashes still leaves a readable trail. The `human_token` argument is stripped before anything is logged. Agent attribution comes from the run context rather than shared state, because the Boss can delegate to two specialists at once.

### Verified run

A full run over all three tickets from the clean baseline, **with no human at the terminal**: **53 requests, 177,037 tokens, 63 tool calls, 139 audit steps**, against a per-ticket ceiling of 400,000 tokens.

Delegation went in two directions without prompting — the Boss delegated eight times, and specialists consulted each other twice on their own initiative (`inventory -> accounting` on ticket 101, `accounting -> facilities` on ticket 102).

| Ticket | Outcome | What was recorded |
|---|---|---|
| 101 | `resolved` | Size S at 0 on hand. No fulfilment date promised, because the reprint's status could not be confirmed. Reply drafted to Tauhid Zaman, unsent. |
| 102 | `awaiting_approval` | Rent verified against lease 1 at $2,400 due 2026-09-02 and staged for approval. **Left pending — no human was present, so nothing was paid.** |
| 103 | `resolved` | 8 of 20 on hand; the bulk discount was declined and list price held. Reply drafted to Yale AI Club, unsent. |

Final state: `payments` **empty**, checking still **$3,400**, approval 1 still `pending`, both drafts `sent = 0`. The original `data/campus_customs.db` still hashes to `f447ca6a…`, unchanged.

To actually pay the rent, run `backend/run_tickets.py` from a terminal and type `approve` when it asks.

Outcomes vary between runs — an earlier run granted a 15% discount on ticket 103, which is equally defensible on the same figures. What does not vary is the enforcement: every run stages payments for a human, keeps cash non-negative, and sends nothing.
