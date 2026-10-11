import type { Cash } from "../api";
import { money } from "../format";

/**
 * The checking balance, split by when each obligation actually falls due.
 *
 * A single committed total mixes horizons and misleads. After rent is paid the
 * shop holds $1,000 and owes $840 now, with next month's rent not due for
 * another month — reporting that as "over-committed" makes a solvent shop look
 * insolvent. So the headline is what is spendable *today*, and what is coming
 * is shown separately, with its date.
 */
export function CashPanel({ cash }: { cash: Cash | null }) {
  if (!cash) {
    return (
      <section className="card">
        <header><h2>Checking</h2></header>
        <div className="body"><div className="empty">Waiting for the backend…</div></div>
      </section>
    );
  }

  const total = cash.total_balance;
  const dueNow = cash.due_now.total;
  const freeNow = cash.free_now;
  const pct = (n: number) => (total > 0 ? Math.max(0, Math.min(100, (n / total) * 100)) : 0);
  const tone = freeNow < 0 ? "negative" : freeNow < total * 0.2 ? "tight" : "";

  return (
    <section className="card">
      <header>
        <h2>Checking</h2>
        <span className="spacer" />
        <span className="pill">as of {cash.as_of_date}</span>
      </header>
      <div className="body cash">
        <div>
          <div className={`figure ${tone}`}>{money(freeNow)}</div>
          <div className="sub">
            free after what is due now, of {money(total)} on hand
            {tone === "tight" && " — thin"}
            {tone === "negative" && " — already short"}
          </div>
        </div>

        <div className="meter" title="Balance split by what is already due">
          <i className="rent" style={{ width: `${pct(dueNow)}%` }} />
          <i className="free" style={{ width: `${pct(Math.max(0, freeNow))}%` }} />
        </div>

        <div className="legend">
          <div>
            <span className="key" style={{ background: "var(--pink)" }} />
            Due now<span className="val">{money(dueNow)}</span>
          </div>
          <div>
            <span className="key" style={{ background: "var(--green)" }} />
            Free to spend<span className="val">{money(freeNow)}</span>
          </div>
        </div>

        {cash.due_now.items.length > 0 && (
          <div className="obligations">
            <h4>Due now</h4>
            {cash.due_now.items.map((o) => (
              <div className="ob" key={`${o.kind}-${o.ref_id}`}>
                <span className="ob-label">{o.label}</span>
                <span className="ob-date overdue">due {o.due_date}</span>
                <span className="ob-amt">{money(o.amount)}</span>
              </div>
            ))}
          </div>
        )}

        {cash.upcoming.items.length > 0 && (
          <div className="obligations">
            <h4>Coming up</h4>
            {cash.upcoming.items.map((o) => (
              <div className="ob" key={`${o.kind}-${o.ref_id}`}>
                <span className="ob-label">{o.label}</span>
                <span className="ob-date">due {o.due_date}</span>
                <span className="ob-amt">{money(o.amount)}</span>
              </div>
            ))}
            {cash.free_after_all_known < 0 && (
              <div className="shortfall">
                {money(Math.abs(cash.free_after_all_known))} short of covering what is coming —
                solvent today, not yet funded for {cash.upcoming.items[0].due_date}.
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
