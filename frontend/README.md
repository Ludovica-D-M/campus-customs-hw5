# Campus Customs — Operations Desk

React + Vite + TypeScript dashboard for the Campus Customs agent team.

## Run it

Start the backend first, from `backend/`:

```bash
uvicorn main:app --reload --port 8000
```

Then, from this folder:

```bash
npm install
npm run dev
```

Vite serves on <http://localhost:5173>, which the backend already allows in its
CORS configuration.

The API base defaults to `http://localhost:8000`. If the API is running
somewhere else, set `VITE_API_BASE` in a `.env` file — see `.env.example`.

## What it shows

Everything comes from the backend; nothing is mocked or computed from a guess.

- **Tickets** — all three with live status, selectable for a run.
- **Agent activity** — the audit trail rendered as a conversation, one colour per agent.
- **The team** — each agent's contribution, counted from the trail. An agent that
  was not needed shows as idle rather than inventing work.
- **Needs a human** — payments the agents staged. Approving requires a name,
  which is recorded against the payment.
- **Checking** — the balance split into rent, unpaid invoices and what is free.
- **Reset shop** — restores the working database. The original is never touched.
