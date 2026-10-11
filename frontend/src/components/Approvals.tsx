import { useState } from "react";
import type { Approval } from "../api";
import { money, time } from "../format";

/**
 * The human gate.
 *
 * Nothing an agent does moves money; these are requests waiting on a person.
 * Approving requires typing a name, because the backend records it against the
 * payment and refuses agent names outright — the click has to belong to
 * somebody.
 */
export function Approvals({
  approvals,
  onDecide,
  busy,
}: {
  approvals: Approval[];
  onDecide: (id: number, decision: "approve" | "reject", by: string) => Promise<void>;
  busy: number | null;
}) {
  const [names, setNames] = useState<Record<number, string>>({});
  const pending = approvals.filter((a) => a.status === "pending");
  const decided = approvals.filter((a) => a.status !== "pending");

  return (
    <div style={{ display: "grid", gap: 12 }}>
      {pending.length === 0 && decided.length === 0 && (
        <div className="empty">
          No payments staged. Agents can request one — they can never approve it.
        </div>
      )}

      {pending.map((a) => {
        const by = names[a.id] ?? "";
        const working = busy === a.id;
        return (
          <div className="approval" key={a.id}>
            <div>
              <div className="amount">{money(a.amount)}</div>
              <div className="meta">
                {a.kind}
                {a.ref_id !== null && ` · ref ${a.ref_id}`} · from {a.account}
                {a.ticket_id !== null && ` · ticket ${a.ticket_id}`}
              </div>
            </div>
            <div className="reason">{a.reason}</div>
            <div className="meta">
              staged by {a.requested_by} at {time(a.requested_at)} — no money has moved
            </div>
            <div className="actions">
              <input
                type="text"
                placeholder="Your name — recorded against the payment"
                value={by}
                onChange={(e) => setNames({ ...names, [a.id]: e.target.value })}
                disabled={working}
              />
              <button
                className="btn primary small"
                disabled={by.trim().length < 2 || working}
                onClick={() => onDecide(a.id, "approve", by.trim())}
                title={by.trim().length < 2 ? "Type your name first" : "Authorize this payment"}
              >
                {working ? <span className="spin" /> : "Approve"}
              </button>
              <button
                className="btn danger small"
                disabled={by.trim().length < 2 || working}
                onClick={() => onDecide(a.id, "reject", by.trim())}
              >
                Reject
              </button>
            </div>
          </div>
        );
      })}

      {decided.map((a) => (
        <div className="approval decided" key={a.id}>
          <div className="meta">
            {money(a.amount)} · {a.kind} ·{" "}
            <b style={{ color: a.status === "rejected" ? "var(--red)" : "var(--green)" }}>
              {a.status}
            </b>
            {a.decided_by && ` by ${a.decided_by}`}
            {a.payment_id !== null && ` · payment ${a.payment_id}`}
          </div>
        </div>
      ))}
    </div>
  );
}
