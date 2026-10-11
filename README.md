# Campus Customs — Multi-Agent Operations

**MGT 409 · Homework 5 · Ludovica Di Mizio**

Five PydanticAI agents run the operations desk of Campus Customs, a small Yale
campus shop. They read and change the shop's records only through an MCP
server, and they cannot spend a dollar without a person approving it.

Work arrives as tickets. The **Boss** picks one up, delegates to **Inventory**,
**Accounting**, **Facilities** and **Customer Service**, and records an outcome.
A React dashboard shows what they did and is where a human approves payments.

---

## What is in here

| Path | What it is |
|---|---|
| `data/campus_customs.db` | The original shop database. **Never modified.** |
| `data/campus_customs_new.db` | The working copy. Everything the agents change happens here. |
| `mcp_server/` | FastMCP server — the single gateway to the shop. 17 tools. |
| `backend/` | The five agents, their prompts, the audit trail, the FastAPI app. |
| `backend/prompts/` | One prompt per agent, plus the shared house rules. |
| `frontend/` | React + Vite + TypeScript dashboard. |
| `output/` | Every deliverable: the harness, the planning and results pages, the audit trail, screenshots. |
| `AI_prompts.md` | Every prompt given to the vibe coder, with follow-ups and why each was needed. |

### Deliverables in `output/`

- **`harness.md`** — the full reference: database, MCP tools, the five agents, the API, the dashboard, safety rules, and the results.
- **`desk_tickets.html`** — five tabs. Expected plans per ticket (written before the run), Actual outcomes, the Cash tab, and the Reflection.
- **`resolved_board.html`** — real screenshots of the dashboard for each ticket.
- **`resolved_tickets.json`** — per ticket: final status, outcome, agent contributions, human approvals.
- **`audit_trail.json`** — every run, append-only. Each agent call, delegation and tool call.
- **`design.md`** — the dashboard's design decisions.
- **`mcp_smoke.json`** — evidence the MCP tools match the database.

---

## Setup

Requires Python 3.14 and Node 20+.

```bash
# 1. Python environment
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 2. The Portkey API key
cp .env.example .env
# then edit .env and put your real PORTKEY_API_KEY in it

# 3. Dashboard dependencies
cd frontend && npm install && cd ..
```

`.env` is gitignored and must never be committed. The key is read at import
time and is never printed, logged, or placed in a prompt.

---

## Reset the working database

Do this **before every full three-ticket run**, so the run starts from the same
state the graded one did — checking at $3,400.00, `payments` empty, all three
tickets `open`.

```bash
cp data/campus_customs.db data/campus_customs_new.db
```

Or, with the API running, `POST /api/reset` — the dashboard's **Reset shop**
button does the same thing.

The copy only ever goes **original → working**. `data/campus_customs.db` is
opened for reading and never written, so a reset cannot damage the baseline.
Confirm with:

```bash
shasum data/campus_customs.db      # f447ca6a2766a90f3c1f81215c8f774ab109ea4c
```

---

## Running it

### 1. The MCP server

The agents and the API start this themselves, as a stdio subprocess described
in `.mcp.json`. You only need to run it by hand to poke at it directly:

```bash
.venv/bin/python mcp_server/server.py              # stdio
.venv/bin/python mcp_server/server.py --http --port 8000   # HTTP
```

To use it from Claude Code, `.mcp.json` in this folder already registers it as
`campus-customs-ops`. Paths there are relative, so it works from any clone.

### 2. FastAPI backend

From the `backend/` folder:

```bash
cd backend
uvicorn main:app --reload --port 8000
```

Interactive docs at <http://localhost:8000/docs>.

### 3. React dashboard

From the `frontend/` folder, in a second terminal:

```bash
cd frontend
npm run dev
```

Open <http://localhost:5173>. The backend already allows that origin. The API
base defaults to `http://localhost:8000`; override with `VITE_API_BASE` if you
run the API elsewhere.

---

## A full three-ticket run

```bash
# 1. Clean start
cp data/campus_customs.db data/campus_customs_new.db

# 2. Record the starting balance
sqlite3 data/campus_customs_new.db "SELECT balance FROM cash_accounts;"   # 3400.0

# 3. Start the backend, and the dashboard in a second terminal
cd backend && uvicorn main:app --reload --port 8000
cd frontend && npm run dev

# 4. In the dashboard: select all three tickets and Run the team.
#    When a payment appears under "Needs a human", type your name and Approve.
#    Re-run the ticket afterwards so the team can confirm it is finished.
```

Or headless, from the project root:

```bash
.venv/bin/python backend/run_tickets.py            # every open ticket
.venv/bin/python backend/run_tickets.py --ticket 102
```

The headless runner pauses at a terminal prompt for each payment and requires
you to type `approve`. With no terminal attached it leaves the payment pending
and pays nothing.

---

## The rules, and where they are enforced

Not in the prompts — in the MCP server, where a model cannot reach them.

- **Every payment needs a human.** Agents can only call
  `request_payment_approval`, which records a pending row. Approving requires an
  operator token that lives solely in the server's environment and is withheld
  from every agent's toolset. A decision attributed to an agent name is refused
  even with a valid token.
- **Cash can never go negative.** Checked when a payment is staged and again at
  settlement, against the live balance.
- **Nobody is ever contacted.** There is no email, SMS or phone capability.
  Replies are written with `draft_customer_message`, which always stores
  `sent = 0`.
- **The shop's date is the only date.** Every judgment is made against
  `desk.date_today`, never the real clock.
- **Nothing is invented.** Tools return database values and arithmetic on them.
  A missing row returns `found: false`, not a plausible default.
- **A payment does not resolve a ticket.** When money clears, the ticket returns
  to `open`; only the Boss, on a later run, can mark it `resolved`.

### Checking the rules hold

```bash
.venv/bin/python backend/test_delegation_guards.py   # 18 loop/cycle cases
.venv/bin/python backend/test_payment_approval.py    # 12 approval cases
```

Both run without a model call. The approval test restores the database
afterwards.

---

## Results of the graded run

Clean start at **$3,400.00**. Five runs, 255,707 tokens, one human approval.

| Ticket | Final status | Money |
|---|---|---|
| 101 — Bulldog tee | `blocked` — size S at 0 and no confirmed ETA for the reprint, so no date was promised | none |
| 102 — Rent due | `resolved` — verified against the lease, approved by a person, paid, then confirmed | **−$2,400.00** |
| 103 — Bulk hoodie discount | `resolved` — 10% discount at $52.20/unit, above the $22 cost floor | none |

Ending balance **$1,000.00**, which matches `cash_accounts` exactly. Cash never
went negative, three customer replies were drafted and none sent, and the
original database is unchanged.

Full detail in [`output/harness.md`](output/harness.md) and
[`output/desk_tickets.html`](output/desk_tickets.html).
