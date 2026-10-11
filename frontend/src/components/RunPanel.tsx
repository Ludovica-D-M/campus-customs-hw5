import type { Run } from "../api";
import { titleCase } from "../format";

/** The most recent run: what the Boss concluded on each ticket, and the cost. */
export function RunPanel({ run }: { run: Run | null }) {
  if (!run) {
    return <div className="empty">No run in this session yet.</div>;
  }
  return (
    <div className="runcard">
      <div className="rid">
        {run.run_id} · {run.status}
        {run.status === "running" && <> <span className="spin" /></>}
        {run.usage?.total_tokens ? ` · ${run.usage.total_tokens.toLocaleString()} tokens` : ""}
        {run.usage?.requests ? ` · ${run.usage.requests} requests` : ""}
      </div>

      {run.error && <div className="banner">{run.error}</div>}

      {run.status === "running" && run.resolutions.length === 0 && (
        <div className="banner info">
          Working tickets {run.ticket_ids.join(", ")}. Payments found along the way will wait
          for you.
        </div>
      )}

      {run.resolutions.map((r) => (
        <div key={r.ticket_id} style={{ borderTop: "1px solid var(--line)", paddingTop: 10 }}>
          <div>
            <b>#{r.ticket_id}</b>{" "}
            <span className={`outcome ${r.outcome}`}>{r.outcome.replace(/_/g, " ")}</span>
          </div>
          <div style={{ color: "var(--ink-2)", marginTop: 4 }}>{r.summary}</div>
          {r.delegated_to.length > 0 && (
            <div className="chips" style={{ marginTop: 7 }}>
              {r.delegated_to.map((a) => (
                <span className="chip" key={a}>
                  {titleCase(a)}
                </span>
              ))}
            </div>
          )}
          {r.human_approval_needed.length > 0 && (
            <div style={{ color: "var(--pink)", fontSize: 13, marginTop: 7 }}>
              Waiting on you: {r.human_approval_needed.join("; ")}
            </div>
          )}
          {r.customer_or_vendor_drafts.length > 0 && (
            <div style={{ color: "var(--muted)", fontSize: 12.5, marginTop: 5 }}>
              Drafted, not sent: {r.customer_or_vendor_drafts.join("; ")}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
