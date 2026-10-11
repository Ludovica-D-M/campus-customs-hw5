import type { Ticket } from "../api";
import { titleCase } from "../format";

/**
 * The three tickets, selectable for a run.
 *
 * Status is carried twice on purpose: a coloured left edge for scanning the
 * column, and a worded badge for reading one. `resolved` is the only green
 * thing on the board, and a ticket only earns it when the Boss judges the work
 * complete — a cleared payment alone sends the ticket back to `open`.
 */
export function TicketBoard({
  tickets,
  selected,
  onToggle,
}: {
  tickets: Ticket[];
  selected: Set<number>;
  onToggle: (id: number) => void;
}) {
  if (tickets.length === 0) {
    return <div className="empty">No tickets on the board.</div>;
  }
  return (
    <div className="tickets">
      {tickets.map((t) => {
        const lastNote = (t.notes ?? "").trim().split("\n").filter(Boolean).slice(-1)[0] ?? "";
        return (
          <label
            key={t.id}
            className={`ticket s-${t.status} ${selected.has(t.id) ? "sel" : ""}`}
          >
            <div className="head">
              <input
                type="checkbox"
                checked={selected.has(t.id)}
                onChange={() => onToggle(t.id)}
                aria-label={`Select ticket ${t.id}`}
              />
              <div style={{ minWidth: 0, flex: 1 }}>
                <div className="title">
                  #{t.id} · {t.subject}
                </div>
                <div className="who">
                  {titleCase(t.type)} · {t.requester}
                </div>
              </div>
              <span className={`badge ${t.status}`}>{t.status.replace(/_/g, " ")}</span>
            </div>

            <div className="chips">
              {t.sku && <span className="chip">{t.sku}</span>}
              {t.size && <span className="chip">size {t.size}</span>}
              {t.qty !== null && <span className="chip">qty {t.qty}</span>}
              {t.lease_id !== null && <span className="chip">lease {t.lease_id}</span>}
              {t.invoice_id !== null && <span className="chip">invoice {t.invoice_id}</span>}
            </div>

            {lastNote && <div className="note">{lastNote}</div>}
          </label>
        );
      })}
    </div>
  );
}
