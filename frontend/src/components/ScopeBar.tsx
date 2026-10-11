/**
 * Picks which ticket, and which run of it, the activity and roster describe.
 *
 * Without this the feed is every step of every run ever recorded, and the
 * contribution counts silently add up work from unrelated tickets. Scoping is
 * mandatory rather than optional: there is no "all activity" option, because a
 * mixed total is a number nobody can act on.
 */
export interface Scope {
  ticketId: number;
  runId: string;
}

export function ScopeBar({
  tickets,
  runsForTicket,
  scope,
  onChange,
}: {
  tickets: number[];
  runsForTicket: { runId: string; started: string; steps: number }[];
  scope: Scope | null;
  onChange: (next: Scope) => void;
}) {
  if (tickets.length === 0) return null;

  return (
    <div className="scopebar">
      <div className="tickettabs" role="tablist" aria-label="Ticket in focus">
        {tickets.map((id) => (
          <button
            key={id}
            role="tab"
            aria-selected={scope?.ticketId === id}
            className={scope?.ticketId === id ? "on" : ""}
            onClick={() => onChange({ ticketId: id, runId: "" })}
          >
            #{id}
          </button>
        ))}
      </div>

      {scope && runsForTicket.length > 0 && (
        <label className="runpick">
          <span>run</span>
          <select
            value={scope.runId}
            onChange={(e) => onChange({ ticketId: scope.ticketId, runId: e.target.value })}
          >
            {runsForTicket.map((r, i) => (
              <option key={r.runId} value={r.runId}>
                {i === 0 ? "latest" : `#${runsForTicket.length - i}`} · {r.runId.slice(-6)} ·{" "}
                {r.steps} steps
              </option>
            ))}
          </select>
        </label>
      )}
    </div>
  );
}
