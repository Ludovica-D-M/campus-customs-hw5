import type { ActivityStep } from "../api";
import { EVENT_LABEL, agentStyle } from "../agents";
import { time } from "../format";

/**
 * What the agents actually did, newest last, straight from the audit trail.
 *
 * Each line is attributed to a coloured avatar so the five agents read as
 * distinct voices. Delegations show the handoff, tool calls show the tool and
 * its arguments, and the two lines that matter most — a payment being staged
 * and a human deciding it — are tinted so they cannot be scrolled past.
 */
export function ActivityFeed({ steps }: { steps: ActivityStep[] }) {
  if (steps.length === 0) {
    return <div className="empty">No activity yet. Select a ticket and run the team.</div>;
  }
  return (
    <div className="feed">
      {steps.map((s) => {
        const who = agentStyle(s.agent);
        const verb = EVENT_LABEL[s.event] ?? s.event;
        const args = s.arguments ? Object.entries(s.arguments) : [];
        return (
          <div className={`step ev-${s.event}`} key={`${s.run_id}-${s.step}`}>
            <div className="avatar" style={{ background: who.colour }}>
              {who.initial}
            </div>
            <div style={{ minWidth: 0 }}>
              <div className="line1">
                <span className="name" style={{ color: who.colour }}>
                  {who.label}
                </span>
                <span className="verb">{verb}</span>
                {s.tool && <span className="tool">{s.tool}</span>}
                {s.ticket_id !== null && <span className="verb">· ticket {s.ticket_id}</span>}
                <span className="ts">{time(s.at)}</span>
              </div>

              {s.event === "delegation" && s.instruction && (
                <div className="text">“{s.instruction}”</div>
              )}
              {s.event !== "delegation" && s.detail && s.detail !== s.tool && (
                <div className="text">{s.detail}</div>
              )}
              {s.event === "tool_call" && args.length > 0 && (
                <div className="args">
                  {args.map(([k, v]) => `${k}: ${JSON.stringify(v)}`).join("  ·  ")}
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
