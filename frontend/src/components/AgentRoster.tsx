import { useMemo } from "react";
import type { ActivityStep } from "../api";
import { TEAM, agentStyle } from "../agents";

/**
 * What each of the five agents contributed, derived from the audit trail.
 *
 * Nothing here is declared up front — the counts are computed from the steps
 * the backend returned, so an agent that was not needed on a ticket shows as
 * idle rather than as a card pretending it did something. That matters: the
 * plans deliberately leave agents out, and the roster should show that.
 */
export function AgentRoster({ steps }: { steps: ActivityStep[] }) {
  const stats = useMemo(() => {
    const base: Record<
      string,
      { tools: number; handoffs: number; reports: number; last: string }
    > = {};
    for (const key of TEAM) base[key] = { tools: 0, handoffs: 0, reports: 0, last: "" };

    for (const s of steps) {
      const row = base[s.agent];
      if (!row) continue;
      if (s.event === "tool_call") row.tools += 1;
      if (s.event === "delegation") row.handoffs += 1;
      if (s.event === "agent_finished") {
        row.reports += 1;
        row.last = s.detail;
      }
    }
    return base;
  }, [steps]);

  return (
    <div className="roster">
      {TEAM.map((key) => {
        const who = agentStyle(key);
        const s = stats[key];
        const idle = s.tools === 0 && s.handoffs === 0 && s.reports === 0;
        return (
          <div className={`agentcard ${idle ? "idle" : ""}`} key={key}>
            <div className="avatar" style={{ background: who.colour }}>
              {who.initial}
            </div>
            <div style={{ minWidth: 0 }}>
              <div className="name" style={{ color: idle ? undefined : who.colour }}>
                {who.label}
              </div>
              <div className="role">{who.role}</div>
              {idle ? (
                <div className="stats">
                  <span className="stat">not needed yet</span>
                </div>
              ) : (
                <>
                  <div className="stats">
                    <span className="stat">
                      <b>{s.tools}</b> tool calls
                    </span>
                    <span className="stat">
                      <b>{s.handoffs}</b> handoffs
                    </span>
                    <span className="stat">
                      <b>{s.reports}</b> reports
                    </span>
                  </div>
                  {s.last && <div className="last">{s.last}</div>}
                </>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
