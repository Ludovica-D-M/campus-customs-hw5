# AI Prompts Log — HW5: Campus Customs Multi-Agent Operations

This file is a running log of the prompts used with the vibe coder throughout HW5. Each problem section records the problem number and title, the prompt as typed, any follow-up prompt, and a short explanation of why the follow-up was needed — what was missing or needed improving after the first attempt. The file is updated as each problem is completed, not at the end.

## Problem 1 — Vibe coder prompts

### Prompt typed

> Problem 1: Vibe coder prompts
>
> We are starting Homework 5: Campus Customs Multi-Agent Operations.
> We will complete it in steps
>
> Problem 1: Vibe coder prompts
>
> Create AI_prompts.md in the project roots so that you use it to track the prompts I give you throughout this assignment.
> For each problem, include:
> -	Problem number and title
> -	The prompt I gave you
> -	Any follow-up prompt If I give it to you and in that case add a sentence to explain why the followup was needed and what was missing in the first prompt
>
> Ypou need to keep updating this file as we complete each problem

### Follow-up prompt

> keep updating the @Homework/HW5/AI_prompts.md  file without me having to tell you

### Why a follow-up was needed

The first prompt did say to keep the file updated as each problem is completed, and the per-problem sections were being written. What was missing was that *every* prompt counts — not just the one that opens a new problem. Questions and corrections about work already delivered (for Problem 4, asking where `.mcp.json` was and how to reveal it in Finder) were being answered without being logged, so the record of the prompting process had gaps. The follow-up made the rule explicit: log every prompt in the turn it is given, unprompted.

## Problem 2 — Study the Campus Customs database

### Prompt typed

> Problem 2: Study the Campus Customs database
>
> Opoen data/campus_customs.db and study every table and its fields
>
> Make a copy named data/campus_customs_new.db
> Keep the original dd untouched. Make sure that all future database changes only use the new copy (so that the original db remains untouched)
>
> Study the three open tickets and understand how each connects to inventory, vendors, invoices, payments, leases and  other relevant tables
>
> Create output/harness.md
>  For every table, list all its fields and briefly explain why the table matters for the agents (a short line).

### Follow-up prompt

No follow-up prompt was needed for Problem 2.

### Why a follow-up was needed

Not applicable. The first prompt named the database to study, the exact filename of the working copy to create, the rule that the original must stay untouched and all future writes go to the copy, the specific tables to trace the three open tickets against, and the output file plus exactly what each table's entry had to contain.

## Problem 3 — Build the MCP server

### Prompt typed

> Problem 3: Build the MCP server
>
> Create an MCP server in mcp_server/ using FastMCP. It must use data/campus_customs_new.db (never the original database)
>
> Study the three open tickets and I need you to write 3 useful and clearly named MCP tools that will help the agent resolve them. Give the tools intuitive names and bnever invet info.
>
> Update output/harness.md with each tool's tables, the tool’s name and the table it reads, the specific ticket it helps resolve, anda sentenced explaining  why it is useful for those tickets.
>
> Create mcp_server/README.md expliaing the server, which db it uses and the 3 tools

### Follow-up prompt

No follow-up prompt was needed for Problem 3.

### Why a follow-up was needed

Not applicable. The first prompt named the framework (FastMCP), the folder, the database the server must use and the one it must never touch, how many tools to write and the rule that they be intuitively named and invent nothing, and both documentation targets with the exact fields each had to cover.

## Problem 4 — Add the MCP server to vibe coder and test each tool

### Prompt typed

> Problem 4: Add the MCP server to vibe coder and test each tool
>
> Connect the MCP server built in problem 3 to Claude Code so you can call its tools directly
>
> Save the connection in .mcp.json at the project roo
>
> Once connected, test each of the three MCP tools and check that their output matches the actual values in data/campus_customs_new.db
>
> Create output/mcp_smoke.json where you need to save the evidence
>  For each tool, record:
>
> -	The prompt used to test it
> -	The tool name
> -	The actual tool output

### Follow-up prompts

> i dont see .mcp.json in the folder

> give me the command to show it in the folder fro macbook pro

### Why the follow-ups were needed

The first prompt was complete as a specification — it named what to connect, where to save the connection, what to test, what to verify the output against, the evidence file, and the three fields per tool — and all of that was delivered.

What it could not anticipate was a presentation problem on the user's side: `.mcp.json` is a dotfile, and macOS Finder hides dotfiles by default, so the saved connection looked absent even though both copies existed on disk. The first follow-up was needed to confirm the file was actually written; the second asked for the Finder command to reveal hidden files (`Cmd`+`Shift`+`.`, or `defaults write com.apple.finder AppleShowAllFiles -bool true && killall Finder`). Neither indicated a defect in the work — only that a deliverable the grader has to *see* should have come with a note that it is hidden by default.

### Note on how the test was run

Claude Code loads `.mcp.json` when a session starts, so the newly registered `campus-customs-ops` tools do not appear inside the session that just wrote the file. The smoke test therefore launched the server as a subprocess using exactly the `command`, `args` and `cwd` stored in `.mcp.json` and spoke MCP over stdio to it — the same connection Claude Code will use — rather than asserting from an in-process import. Every value each tool returned was then re-queried straight from `data/campus_customs_new.db` and compared: 30 field checks across the three tools, all matching.

## Problem 5 — Build the agent team and grow the MCP tools

### Prompt typed

> Problem 5: Build the agent team and grow the MCP tools
>
> Build the five Campus Customs agents using PydanticAI: Boss, Inventory, Accounting, Facilities, and Customer Service
>
> Give each agent detailed prompt in backend/prompts/ and  put shared data types in backend/models.py, and put the agent code under backend/
>
> Make sure you only use gpt-6-luna through portkey with PORTKEY_API_KEY for every agent
>
> Make the agents os sthat they can communicate and delegate tasks to each other. Add any MCP tools that are needed to work on the three open tickets. All shop information and database changes must go through the MCP server and data/campus_customs_new.db
>
> Follow the shop rules: use the shop’s date, check the vendor lead times and unpaid invoices, require human approval for every payment, never allow spending kore cansh than available (do not allow negative cash balances), and never actually contact customers or vendors
>
> Make the agents record their loop steps to output/audit_trail.json without overwriting previous records. Include reasonable limits on loops and how many tokes they’re using
>
> Update output/harness.md with all agents, MCP tools, their database tables, and a short section on safety and token limits
>
> Update mcp_server/README.md with the complete tool list

### Follow-up prompt

> can agents delegate work to each other without necessarely having the boss do it all the time
> arnd make sure you reasonable limits are setso sgents dont get stuck in loops

### Why the follow-up was needed

The first prompt said the agents must "communicate and delegate tasks to each other", and the first build satisfied that only through the Boss: the Boss delegated to specialists, and specialists reported back to the Boss. A specialist that needed something from a colleague had to return and wait to be asked again. That is a hub-and-spoke team, not agents delegating to each other.

The follow-up made the requirement explicit — specialists must be able to consult each other directly — and paired it with the constraint that makes that safe. Peer-to-peer delegation is what introduces the risk of a cycle (Inventory asks Accounting, which asks Inventory back), so the second half of the prompt asked for loop limits. The first build had delegation and token caps but no cycle protection, because with only the Boss delegating, a cycle was not reachable.

### Second follow-up prompt

> make sure agensts can also delegate back to the boss

### Why the second follow-up was needed

After the first follow-up, delegation ran downward (Boss to specialist) and sideways (specialist to specialist), but not upward. A specialist that hit something above its authority — a decision needing the shop's whole position, or a judgement another ticket depended on — could only mark itself blocked and wait to be asked again.

The gap was partly caused by the fix for the first follow-up: the cycle guard refuses any agent already in the active chain, and the Boss is at the root of every chain, so the Boss was the one colleague no specialist could ever call. Escalation therefore needed its own path rather than reusing `consult_colleague`, and its own protection against the Boss and a specialist handing work back and forth forever.

### Third follow-up prompt

> check that there are no automatic payment approvals. Only approve payments if a human explicitely authorizes you (agents cannot  approve payments themselves)

### Why the third follow-up was needed

The original Problem 5 prompt said "require human approval for every payment", and the build enforced that against the *agents*: no agent is given the approval tool, and the server rejects any decision without the operator token.

What it did not enforce was that a human is actually present. The runner carried a `--auto-approve-under` flag, used so a run could be exercised unattended, which applied an operator *policy* with the operator's token — approving anything at or under a threshold with no person in the loop at that moment. Both verification runs used it, so every payment in the audit trail had been approved by a rule rather than by a person.

That is a defensible engineering choice and it was documented, but it is not what "require human approval for every payment" means. The follow-up closed the gap: the flag was removed, approval now requires typing an explicit phrase at the terminal, and a run with no terminal leaves every payment pending rather than deciding it.

## Problem 6 — Plan the three tickets

### Prompt typed

> Problem 6: Plan the three tickets
>
> Create output/desk_tickets.html as a a page I can open directly in my browser
>
> Make five tabs: Ticket 101, Ticket 102, Ticket 103, Cash (leve the tab empty with a short coming soon message), and Reflection (leve the tab empty with a short coming soon message)
> For the ticket tabs only fill an expected section (leave an empty Actual section for each ticket so we can compare the plans with what really happens later)
>
> For each ticket, write an Expected section explaining:
>
> -	Which agent the Boss should contact first and why
> -	Which other agents should get involved and in what order
> -	Which MCP tools the agents will likely use
>
> Make the plans specific to each ticket.make sure you do not  involve every agent unless they're actually needed
>
> Use the actual ticket info and the MCP tools we've built so far. Keep the page simple, clear, and easy to navigate.

### Follow-up prompt

> Make sure the expected workflows and fields aare realistic and in line with the database and prompt. Make sure the agents move in the right order, that all data and assumptions are accurate and that the estimated and proposed decision make sense from a business standpoint

### Why the follow-up was needed

The first prompt asked for plans that were specific and used the real ticket data, and the page did — but it asked for the plans to be *written*, not *audited*. Three problems only surfaced under a deliberate check:

1. **Ticket 103's order contradicted its own reasoning.** The plan put Accounting first because the ticket is typed `price_override`, while the very next step argued "a discount on goods the shop cannot supply is worthless" — which is the case for Inventory going first. Reordered to Inventory → Accounting.
2. **An inference was presented as a fact.** The ticket 101 plan said invoice 501 being overdue meant "the goods may not ship until it is paid". Nothing in the database links invoice payment to shipment, and no agent has a tool that could confirm it. Rewritten as the judgement it is: the $840 is owed regardless, so the real question is whether to pay it ahead of rent to protect one $28 order.
3. **Assumptions were invisible.** The 5-day lead time gives 2026-09-05 only if the clock starts at the shop date, and invoice 501 records no order date. Each ticket now carries an explicit "Assumptions to check against the run" block so the later Actual comparison tests the reasoning rather than only the outcome.

The follow-up also prompted verifying every figure and tool name mechanically rather than by eye — 15 facts against the database and every tool against each agent's actual toolset.

### Second follow-up prompt

> Make sure the  expected workflow starts with the Boss that receives and delegates the ticket (like the actual structure)
> Make sure assumptions are  supported by the db

### Why the second follow-up was needed

Two gaps remained after the audit.

The plans began with whichever specialist was contacted first, because the original prompt asked "which agent the Boss should contact first" — so the page answered that question literally and left the Boss implicit. But that is not how a run actually begins: the Boss receives every ticket and calls `get_ticket` before it delegates anything. Each plan now opens with that step, showing what the resolved ticket reveals and why its shape routes the work where it does, and closes with the Boss setting the status.

The assumption blocks were accurate but unsourced — a reader had no way to tell a schema fact from an inference. Each bullet now names the table and columns behind it, and every claim was re-checked programmatically: `invoices` has no shipping or order-date column, `leases` has no grace period or late fee and lease 1's notes are empty, `payments` is empty, no discount or promotion table exists, `pricing` has no tiers, no table joins a sku to a vendor, and `inventory` has no reserved column. Eleven checks, all passing.

### Third follow-up prompt

> Make sure the that the expected fields do not contain assumptions as facts for example see invoice 501 etc. The explainantoipn must be financially realistic and consistent with the db

### Why the third follow-up was needed

The previous pass put the assumptions in their own block but left the step-by-step prose still asserting them. Invoice 501 was the clearest case: the plan called it a reprint that was "already in flight" and spoke of the goods being "released", when all the database actually holds is `status = 'open'`, `due_date = '2026-08-28'` and a free-text `description` reading "Rush reprint CC-TEE-WHITE S". Nothing records whether those goods exist, have shipped, or are waiting on payment. The prose now says what the record proves and what it does not, and the expected outcome changed accordingly: ticket 101 is likely `blocked`, because the one thing the customer wants — a date — cannot be derived.

The financial reasoning needed the same treatment. Three corrections: the $264 to cover ticket 103's shortfall is an estimate from `pricing.unit_cost`, not a vendor quote for this order; the $36-a-unit hoodie margin is *gross* margin only, since the database records no labour, carriage or overhead, so a discount near the 62.1% floor is less safe than the arithmetic suggests; and $1,160 of revenue on 20 units holds only if all 20 sell at list. Ticket 101's economics were restated honestly too — one tee is about $20 of gross margin ($28 list against $8 cost), which cannot justify moving $840 ahead of $2,400 of rent, so settling invoice 501 is a timing decision about a liability already owed, not a cost of serving the order.

One arithmetic error was caught in the same pass: $160 left after rent and invoice 501 was described as "under 5% of a month's rent" when it is 6.7%.

## Problem 7 — Backend routes

### Prompt typed

> Problem 7: Backend routes
>
> Create the FastAPI backend in backend/main.py so the React dashboard will later be able to communicate with our agent team
>
> Add routes that let the dashboard do the follwoing:
>
> -	See the three tickets and their current status
> -	Run the agents on a selected ticket ids
> -	See recent agent activity including messages and tools used
> -	Approve payments or purchases after a human clicks (before any money is actuallyspent)
> -	Checkand return the current cash balance
> -	Reset the working database to its original state when you want to try a fresh run
>
> Make sure the backend connects to the agents and MCP tools we already built
>
> Make sure you  kee the shop rules that are in place especially tat agents cannot make payments without human approval and cash can never go negative (the reset should only affect the copied working db never the original db)
>
> Make sure the server can start from the backend/ folder using:
>
> uvicorn main:app --reload --port 8000
>
> Update output/harness.md with a short description of each route in one line what URL / what it does)

### Follow-up prompt

> The agent activity  contribution summaries need to be viewd for a specific ticket and its run (do not mix previous activity or unrelated tickets)

### Why the follow-up was needed

The first build read the whole audit trail into both the activity feed and the contribution roster. That was fine on the first run and wrong from the second onward: the trail accumulates across runs, so by the time three tickets had been worked it held 429 steps from nine runs, and the roster's counts silently summed work from unrelated tickets. "Accounting: 13 tool calls" was arithmetic over a mixture, not a fact about anything.

The original prompt asked the dashboard to "show the activity and conversations of the five agents" and "summarize each agent's contributions" without saying *of what*, and the build answered "of everything" — which looks informative and answers no question. The follow-up fixed the unit of analysis: a ticket within a run.

The fix added a `ticket_id` filter to `GET /api/activity`, a ticket tab strip and run dropdown above the feed, and made both the feed and the roster read the same scope. There is deliberately no "all activity" option, because a mixed total is the thing that caused the problem.

## Problem 8 — Agent dashboard

### Prompt typed

> Problem 8: Agent dashboard
>
> Create a polished nice and  creative frontend in frontend/ using React, Vite, and TypeScript
>
> Connect it to the FastAPI backend from Problem 7 at http://localhost:8000, and on the backend allow the vite page origin (usually http://localhost:5173)
>
> The dashboard should at minimum: display the three tickets, run the agent taem on selected ticket, show the activity and conversations of the five agents, summarize each agent's contributions, show  ticket statuses, let hmans approve payment/purchase, and show the live checking balance
>
> Make the dashboard feel like a real operations desk. You have creative freedom but always make sure it is clear, user friendly and has a distinctive design
>
> Make sure you use real backend data (do not invent naything), remember the human approval that is mandatory for every payment / purchase, and only mark tickes as resolved when their resolution is confirmed and there is no remaining work to do (do not resolve themn only because money was actually paid)

### Added to the same prompt

> Make sure the board can with:
> npm run dev
>
> Write output/design.md explaining your design decisions, how agents read differenlt and how resolved tickets and cash appers and why

### Follow-up prompt

> The agent activity  contribution summaries need to be viewd for a specific ticket and its run (do not mix previous activity or unrelated tickets)

### Why the follow-up was needed

The first build read the whole audit trail into both the activity feed and the contribution roster. That was fine on the first run and wrong from the second onward: the trail accumulates across runs, so by the time three tickets had been worked it held 429 steps from nine runs, and the roster's counts silently summed work from unrelated tickets. "Accounting: 13 tool calls" was arithmetic over a mixture, not a fact about anything.

The original prompt asked the dashboard to "show the activity and conversations of the five agents" and "summarize each agent's contributions" without saying *of what*, and the build answered "of everything" — which looks informative and answers no question. The follow-up fixed the unit of analysis: a ticket within a run.

The fix added a `ticket_id` filter to `GET /api/activity`, a ticket tab strip and run dropdown above the feed, and made both the feed and the roster read the same scope. There is deliberately no "all activity" option, because a mixed total is the thing that caused the problem.

## Problem 9 — Resolve the tickets

### Prompt typed

> Problem 9: Resolve the tickets
>
> Before the anges work on the tickes: Reset data/campus_customs_new.db from the original database (clean start) and record the starting checking balance
>
> Run the real agents on tickets 101, 102, and 103 until each is resolved
>
> Update output/desk_tickets.html (from problem 6), you need to keep the Expected sections and fill in Actual agents, delegations, tools, and outcomes
>
> On its Cash tab, show starting balance, actual cash changes for each ticket resolved and why (which pay or purchase and the $ amount), and ending balance (verify the math against the working db it must match cash_accounts)
>
> Save output/resolved_tickets.json where for each ticket show id, final status, outcome, agent contributions, and human approvals
>
> Create output/resolved_board.html with real screenshots of the React dashboard for each of the resolbved tickes (101,102,  103)
>
> Append the real runs to output/audit_trail.json
>
> Complete output/harness.md covering the db, MCP tools, five agents, API, dashboard, and safety rules
>
> Do nopt invet info and do not mark tickets as competed without evidence

### Follow-up prompt

_(none yet — updated as follow-ups arrive)_

## Problem 10 — Reflection

### Prompt typed

> Problem 10: Reflection
>
> Complete problem 10 in the Reflection tab of output/desk_tickets.html
>
> Write detailed, natural, and specific answers that cover the folllwiung:
>
> -	Evaluate agent performance on the  tickets 101, 102, and 103 and explain why
> -	Compare Actual vs. Expected for each ticket
> -	Explain what would be simpler with one agent using tools and explain why
> -	Give three new problems the existing agents and tools could solve.
> -	Give three problems they couldn't solve, and what new agents/tools would be needed
>
> Use evidence from the ticket tabs, Cash tab and audit trail
> Make sure to refrerence actual outcomes
>
> Do not invent info
>
> Make sure the reflection is thoughtful, critical, and personal (not something genereic, make references)

### Follow-up prompt

_(none yet — updated as follow-ups arrive)_

## Problem 11 — Submit to GitHub

### Prompt typed

> Problem 11: Submit to GitHub
>
> Before finalizing the assignment make sure you log also this prompt into AI_prompts.md
>
> Update README.md with instructions to reset the working database, start the MCP server, start FastAPI, and run the React dashboard, reset the DB before a full three ticket run
>
> Ensure you exclude  .env, API keys, node_modules, and other secrets and make sure to never expose API keys or commit .env
>
> Include both data/campus_customs.db and data/campus_customs_new.db in GitHub
>
> Save the repository URL in output/github_url.txt
>
> Report the GitHub URL and if tehre are issues
>
> Verify all required files are present and check the project matches the expected file layout in the assignment screenshot (attached)
>
> Run final checks, then push the project to a public GitHub repository.
>
> Do not submit to Canvas automatically I'll paste the repo URL myself

### Follow-up prompt

_(none yet — updated as follow-ups arrive)_

### Follow-up prompt (Problem 11)

> Compare my GitHub repository against the exact expected file layout for Problem 11
>
> Tell me if there are Identify:
>
> -	Required files that are missing
> -	Extra files that are necessary for the app to work
> -	Extra files that are unnecessary and safe to remove
>
> DO NOT delete anything, just check at this point and give me a concise list first
>
> Also check that there are no secrets
>
> And add this prompt in AI_prompts.md

### Why the follow-up was needed

The push in Problem 11 verified that every required file was present, but not the
converse — whether anything in the repository was surplus. The assignment's expected
layout was supplied as a screenshot that did not come through in the prompt, so the
first pass checked against the structure the assignment text implies rather than against
the picture itself. This follow-up asked for the audit in both directions, and
explicitly asked for a list before any deletion.

### Follow-up prompt (Problem 11, cont.)

> Push the latest AI_prompts.md
>
> Remove personal file paths from output/mcp_smoke.json but still make it accessible
>
> Keep everything else unchanged

### Why the follow-up was needed

The layout audit turned up one non-secret but personal detail: `output/mcp_smoke.json`
recorded the Problem 4 connection with absolute paths, so the home directory appeared
three times in a public repository. The file is evidence and had to stay readable, so the
fix was to rewrite the paths into the same relative form `.mcp.json` now uses rather than
to remove or truncate the file. The instruction to keep everything else unchanged also
settled the open question from the audit: the two test scripts and the Vite leftovers stay.
