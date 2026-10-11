# Operations Desk — design decisions

The dashboard in [`frontend/`](../frontend/) is built for one job: let a person
running a small shop see what five agents did on her behalf, and decide the one
thing the agents are not allowed to decide. Every choice below follows from
that.

React + Vite + TypeScript. Start the backend from `backend/` with
`uvicorn main:app --reload --port 8000`, then `npm run dev` here.

## The premise: a desk, not a chatbot

The obvious design for a multi-agent project is a chat window. It was the wrong
shape here. A shop owner does not want to read a transcript to learn whether
rent got paid — she wants the state of the shop, and the transcript only when
something looks wrong.

So the screen is laid out as a desk with a fixed geography. **Left is the work**
— the tickets, and beneath them what the agents did. **Right is the shop** —
money at the top, the decision waiting on you below it, then the run summary and
the team. The columns never reorder. After a few minutes you stop reading the
headings and go straight to the spot.

## Colour carries one meaning

Black and pink, and pink means **a person is needed**. The approval card, the
pending-payment pill in the top bar, the `awaiting_approval` badge and the
primary action button are the only saturated pink on the screen. Nothing
decorative uses it.

That is why the "N payments need you" pill only appears when the count is above
zero: a permanent indicator becomes furniture, and furniture is invisible.
Everything that is merely informational — chips, timestamps, tool arguments —
sits in grey and stays out of the way.

Green appears in exactly two places, and both mean *settled*: a resolved ticket,
and cash that is genuinely free. Red means stopped: `blocked`, an error, a
refused action.

## How the five agents read differently

The audit trail is a flat list of events from seven actors. Rendered plainly it
is a wall of text, and the thing that matters most — that five *different*
specialists each did a distinct job — disappears.

Each agent therefore gets a **colour and an initial**, carried on a circular
avatar in the activity feed and on its roster card:

| Agent | Mark | Why that colour |
|---|---|---|
| Boss | **B**, shop pink | It owns the ticket; it gets the house colour. |
| Inventory | **I**, soft pink | Closest to the Boss — the first agent on most tickets. |
| Accounting | **A**, violet | Furthest from the shop pink, because it is the one that touches money. |
| Facilities | **F**, coral | Warm and rare; it appears on one ticket only. |
| Customer Service | **C**, amber | The outward-facing voice, visually distinct from the money agents. |
| You | **★**, green | The human. The only mark that is not a letter. |
| System | **·**, grey | Run start and end. Deliberately dull. |

The hues stay inside one family rather than being five arbitrary colours. They
read as a team with roles, not as a legend you have to memorise.

Each line is also phrased as something a person did, not an event code:
*Inventory called `check_item_availability`*, *Boss handed off*, *Accounting
staged a payment*. Delegations show the actual instruction in quotes, so a
handoff reads as one agent asking another a question — which is what it is. Two
event types get a tinted row because they are the plot: a payment being staged
(pink) and a human deciding it (green).

## Scope: one ticket, one run

The audit trail accumulates. After a few runs it holds hundreds of steps across
several tickets, and a feed that shows all of them answers no useful question —
worse, contribution counts computed over the whole trail silently add up work
from unrelated tickets, so "Accounting: 13 tool calls" becomes a number nobody
can act on.

So the activity feed and the roster are **always scoped to one ticket within one
run**. A tab strip above the feed picks the ticket; a dropdown picks which run of
it, newest first and labelled *latest*. Both panels read the same scope, so the
summary always describes exactly the conversation shown beneath it.

There is deliberately **no "all activity" option**. An unscoped view looks
informative and is not: in testing, the unfiltered trail held 429 steps across
nine runs and three tickets, while scoping to ticket 101's run gave 36 steps —
one ticket, one run, and counts that mean something. Filtering is done
server-side by `GET /api/activity?ticket_id=&run_id=`, which also drops the
run-level markers that belong to no ticket.

The scope follows the work: when a run finishes, focus moves to the ticket it
touched, so the newest story is on screen without being asked for. Re-running
the same ticket adds a run to the dropdown rather than mixing into the previous
one — useful for ticket 102, where the second run is what confirms resolution
after a payment clears.

## Summarising contributions without inventing them

The roster counts each agent's tool calls, handoffs and reports **from the steps
in scope** — one ticket, one run. Nothing is declared in advance, and nothing
from another ticket is counted.

The important case is the agent that did nothing. The ticket plans deliberately
leave agents out — Facilities has no business in a discount request — so an
agent with no activity renders dimmed, with *"not needed yet"* instead of three
zeroes. Zeroes would imply it was asked and failed. Dimming says it was never
needed, which is the truth and is also a design decision the plans made on
purpose.

Each active card ends with that agent's last reported sentence, so the roster
answers "what did Accounting actually conclude" without opening the feed.

## How resolved tickets appear, and why it is hard to get there

Status is carried twice: a **coloured left edge** for scanning the column, and a
**worded badge** for reading one ticket. Four states, four edges — grey `open`,
pink `awaiting_approval`, red `blocked`, green `resolved`.

`resolved` is the only green on the ticket board, and it is meant to be rare and
earned. The rule the backend enforces:

> A cleared payment does **not** resolve a ticket.

When you approve a payment, the money moves, the payment is recorded, and the
ticket goes back to **`open`** with a note saying what was paid and that the
team still needs to confirm nothing else is outstanding. Only the Boss, on a
later run, can set `resolved` — and only when the rest of the ticket is actually
done.

This is deliberate. Paying rent is one piece of work finishing; the customer may
still be owed a reply, stock may still need adjusting. A board that flipped to
green the moment money left the account would be reporting the most expensive
action as though it were the whole job. Verified end to end: ticket 102 went
`awaiting_approval` → payment approved → **`open`** → re-run → `resolved`.

`blocked` is shown as a legitimate outcome, not a failure. Ticket 101 ends
blocked because the database records no date the reprint will arrive — the right
answer there is to say so, and the board should not make that look like a bug.

## How cash appears, and why not just the balance

The headline figure is **not the balance**. It is the *uncommitted* amount,
with the balance underneath as context:

```
  $160.00
  uncommitted, of $3,400.00 on hand — thin
```

$3,400 looks like a healthy shop. It is not: $2,400 of rent and an $840 unpaid
invoice are already claimed against it, leaving $160. Leading with $3,400 would
be technically true and practically misleading, and this is the number a person
uses to decide whether to approve a $264 purchase.

Beneath it, a single stacked bar splits the balance into **rent**, **unpaid
invoices** and **free**, so the shape of the commitment is visible without
reading three figures. The headline turns **amber** when free cash drops below a
tenth of the balance, and **red** if commitments exceed the balance — the shop
cannot go cash-negative, but it can be over-committed, and that is worth seeing
before approving anything.

All four numbers come from `GET /api/cash`, which derives them in the MCP
server. The dashboard does no arithmetic on money beyond the bar's percentages.

## Approvals: making the click mean something

The approval card shows the amount large, then the reason the agent gave, then
who staged it and when — followed by the line *"no money has moved"*.

Approving requires **typing a name**. Two reasons: it is recorded against the
payment in the `payments` table and the audit trail, so the decision has an
owner; and a two-character minimum stops an approval being a reflex click on a
button that moves thousands of dollars. The backend rejects agent names here
even with a valid operator token, so the field cannot be filled with "Boss".

Refusals from the shop's rules — an approval already decided, a balance that
will not cover it — surface as a red banner with the server's own wording rather
than a generic error. Those messages are the rules speaking, and they are worth
reading.

## Honesty about data

The API client is the only module that talks to the backend, and every figure on
screen traces to a response. There are no mock fixtures, no placeholder numbers
and no optimistic updates: after you approve a payment the dashboard re-fetches
rather than assuming what the server did, because the server might have refused.

When the backend is unreachable the top bar flips to a red *"API unreachable"*
pill and panels show their empty state. Nothing is filled in with a plausible
guess — a dashboard that invents a balance is worse than one that admits it
cannot reach the shop.

Polling is adaptive: every 5 seconds at rest, every 1.5 seconds while a run is
in flight, with the activity feed auto-scrolled to the newest step so a running
team reads as live without a websocket.
