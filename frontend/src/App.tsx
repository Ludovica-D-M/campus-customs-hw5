import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  ApiError,
  type Approval,
  type ActivityStep,
  type Cash,
  type Run,
  type Ticket,
} from "./api";
import { ActivityFeed } from "./components/ActivityFeed";
import { AgentRoster } from "./components/AgentRoster";
import { Approvals } from "./components/Approvals";
import { CashPanel } from "./components/CashPanel";
import { RunPanel } from "./components/RunPanel";
import { ScopeBar, type Scope } from "./components/ScopeBar";
import { TicketBoard } from "./components/TicketBoard";

/** How often the desk refreshes. Fast while a run is in flight, slow otherwise. */
const IDLE_MS = 5000;
const LIVE_MS = 1500;

export default function App() {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [shopDate, setShopDate] = useState<string>("");
  const [cash, setCash] = useState<Cash | null>(null);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  // Every step the trail holds. The feed and the roster never read this
  // directly — they read `scopedSteps`, which is one ticket within one run.
  const [allSteps, setAllSteps] = useState<ActivityStep[]>([]);
  const [scope, setScope] = useState<Scope | null>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [online, setOnline] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deciding, setDeciding] = useState<number | null>(null);
  const [starting, setStarting] = useState(false);

  const runIdRef = useRef<string | null>(null);
  const feedRef = useRef<HTMLDivElement | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [t, c, a, act] = await Promise.all([
        api.tickets(),
        api.cash(),
        api.approvals(),
        api.activity({ limit: 400 }),
      ]);
      setTickets(t.tickets);
      setShopDate(t.as_of_date);
      setCash(c);
      setApprovals(a.approvals);
      setAllSteps(act.steps);
      if (runIdRef.current) setRun(await api.run(runIdRef.current));
      setOnline(true);
      setError(null);
    } catch (e) {
      setOnline(false);
      setError(e instanceof ApiError ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Poll faster while a run is in flight so the feed reads as live.
  useEffect(() => {
    const live = run?.status === "running";
    const id = setInterval(() => void refresh(), live ? LIVE_MS : IDLE_MS);
    return () => clearInterval(id);
  }, [refresh, run?.status]);

  // Which tickets have any recorded activity, and which runs touched each one.
  const ticketsWithActivity = useMemo(() => {
    const ids = new Set<number>();
    for (const s of allSteps) if (s.ticket_id !== null) ids.add(s.ticket_id);
    return [...ids].sort((a, b) => a - b);
  }, [allSteps]);

  const runsForTicket = useMemo(() => {
    if (!scope) return [];
    const byRun = new Map<string, { runId: string; started: string; steps: number }>();
    for (const s of allSteps) {
      if (s.ticket_id !== scope.ticketId) continue;
      const row = byRun.get(s.run_id) ?? { runId: s.run_id, started: s.at, steps: 0 };
      row.steps += 1;
      byRun.set(s.run_id, row);
    }
    // Newest first, so "latest" is the default and sits at the top.
    return [...byRun.values()].reverse();
  }, [allSteps, scope?.ticketId]);

  // One ticket, one run. Anything outside that is another ticket's story.
  const scopedSteps = useMemo(() => {
    if (!scope) return [];
    const runId = scope.runId || runsForTicket[0]?.runId;
    if (!runId) return [];
    return allSteps.filter((s) => s.ticket_id === scope.ticketId && s.run_id === runId);
  }, [allSteps, scope, runsForTicket]);

  // Focus the newest ticket with activity until the user picks another.
  useEffect(() => {
    if (ticketsWithActivity.length === 0) {
      if (scope) setScope(null);
      return;
    }
    if (scope && ticketsWithActivity.includes(scope.ticketId)) return;
    const newest = [...allSteps].reverse().find((s) => s.ticket_id !== null);
    setScope({ ticketId: newest?.ticket_id ?? ticketsWithActivity[0], runId: "" });
  }, [ticketsWithActivity, allSteps, scope]);

  // Keep the newest activity in view, which is where a running team is working.
  useEffect(() => {
    const el = feedRef.current?.querySelector(".feed");
    if (el) el.scrollTop = el.scrollHeight;
  }, [scopedSteps.length]);

  const toggle = (id: number) =>
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  const startRun = async () => {
    setStarting(true);
    setError(null);
    try {
      const { run_id } = await api.startRun([...selected]);
      runIdRef.current = run_id;
      setRun(await api.run(run_id));
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setStarting(false);
    }
  };

  const decide = async (id: number, decision: "approve" | "reject", by: string) => {
    setDeciding(id);
    setError(null);
    try {
      await api.decide(id, decision, by);
    } catch (e) {
      // The refusals the shop's rules produce land here — an agent name, an
      // approval already decided, a balance that will not cover it.
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setDeciding(null);
      await refresh();
    }
  };

  const reset = async () => {
    if (!confirm("Restore the working database to its original state? The run history on the board will clear. The original database is not touched.")) return;
    try {
      await api.reset();
      runIdRef.current = null;
      setRun(null);
      setSelected(new Set());
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    }
  };

  const pending = approvals.filter((a) => a.status === "pending").length;
  const running = run?.status === "running";
  const counts = tickets.reduce<Record<string, number>>((acc, t) => {
    acc[t.status] = (acc[t.status] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <div className="desk">
      <header className="topbar">
        <div className="brand">
          <h1>
            Campus Customs <span>Operations Desk</span>
          </h1>
          {shopDate && <span className="date">shop date {shopDate}</span>}
        </div>

        {pending > 0 && (
          <span className="pill" style={{ borderColor: "var(--pink)", color: "var(--pink)" }}>
            <span className="dot" style={{ background: "var(--pink)" }} />
            {pending} payment{pending > 1 ? "s" : ""} need you
          </span>
        )}
        <span className={`pill ${online ? "" : "off"}`}>
          <span className="dot" />
          {online ? "API connected" : "API unreachable"}
        </span>
        <button className="btn ghost small danger" onClick={reset}>
          Reset shop
        </button>
      </header>

      {error && (
        <div style={{ padding: "12px 24px 0" }}>
          <div className="banner">{error}</div>
        </div>
      )}

      <div className="layout">
        {/* ------------------------------------------------ left column */}
        <div className="col">
          <section className="card">
            <header>
              <h2>Tickets</h2>
              <span className="spacer" />
              {Object.entries(counts).map(([s, n]) => (
                <span className={`badge ${s}`} key={s}>
                  {n} {s.replace(/_/g, " ")}
                </span>
              ))}
            </header>
            <div className="body" style={{ display: "grid", gap: 14 }}>
              <TicketBoard tickets={tickets} selected={selected} onToggle={toggle} />
              <div className="runbar">
                <button
                  className="btn primary"
                  disabled={selected.size === 0 || running || starting}
                  onClick={startRun}
                >
                  {running || starting ? (
                    <>
                      <span className="spin" /> Team is working…
                    </>
                  ) : (
                    `Run the team on ${selected.size || "…"} ticket${selected.size === 1 ? "" : "s"}`
                  )}
                </button>
                <button
                  className="btn"
                  disabled={running}
                  onClick={() => setSelected(new Set(tickets.map((t) => t.id)))}
                >
                  Select all
                </button>
                {selected.size > 0 && (
                  <button className="btn ghost" disabled={running} onClick={() => setSelected(new Set())}>
                    Clear
                  </button>
                )}
                <span className="hint">
                  Agents never pay. Anything costing money comes back here for you.
                </span>
              </div>
            </div>
          </section>

          <section className="card" ref={feedRef}>
            <header>
              <h2>Agent activity</h2>
              <span className="spacer" />
              <span className="pill">
                {scope ? `ticket ${scope.ticketId} · ${scopedSteps.length} steps` : "no runs yet"}
              </span>
            </header>
            {ticketsWithActivity.length > 0 && (
              <ScopeBar
                tickets={ticketsWithActivity}
                runsForTicket={runsForTicket}
                scope={scope ? { ...scope, runId: scope.runId || runsForTicket[0]?.runId || "" } : null}
                onChange={setScope}
              />
            )}
            <ActivityFeed steps={scopedSteps} />
          </section>
        </div>

        {/* ----------------------------------------------- right column */}
        <div className="col">
          <CashPanel cash={cash} />

          <section className="card">
            <header>
              <h2>Needs a human</h2>
              {pending > 0 && (
                <>
                  <span className="spacer" />
                  <span className="badge awaiting_approval">{pending} pending</span>
                </>
              )}
            </header>
            <div className="body">
              <Approvals approvals={approvals} onDecide={decide} busy={deciding} />
            </div>
          </section>

          <section className="card">
            <header>
              <h2>Latest run</h2>
            </header>
            <div className="body">
              <RunPanel run={run} />
            </div>
          </section>

          <section className="card">
            <header>
              <h2>The team</h2>
              <span className="spacer" />
              {scope && (
                <span className="pill">
                  ticket {scope.ticketId} · {(scope.runId || runsForTicket[0]?.runId || "").slice(-6)}
                </span>
              )}
            </header>
            <div className="body">
              {scope ? (
                <AgentRoster steps={scopedSteps} />
              ) : (
                <div className="empty">
                  Run the team on a ticket to see who contributed what.
                </div>
              )}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
