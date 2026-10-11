/**
 * The only module that talks to the backend.
 *
 * Every value the dashboard shows comes from one of these calls. Nothing is
 * mocked, defaulted or computed from a guess — if the API has not returned it,
 * the UI shows the absence rather than inventing a number.
 */

const BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

export type TicketStatus = "open" | "awaiting_approval" | "blocked" | "resolved";

export interface Ticket {
  id: number;
  type: string;
  requester: string;
  subject: string;
  sku: string | null;
  size: string | null;
  qty: number | null;
  lease_id: number | null;
  invoice_id: number | null;
  status: TicketStatus;
  notes: string | null;
  created_at: string;
}

export interface TicketsResponse {
  as_of_date: string;
  tickets: Ticket[];
  counts_by_status: Record<string, number>;
}

export interface Obligation {
  kind: string;
  ref_id: number;
  amount: number;
  due_date: string;
  label: string;
}

export interface Cash {
  as_of_date: string;
  accounts: { name: string; balance: number; date: string }[];
  total_balance: number;
  /** Obligations on or before the shop date — these compete with today's cash. */
  due_now: { total: number; items: Obligation[] };
  /** Obligations after the shop date. Real, but not yet claiming today's money. */
  upcoming: { total: number; items: Obligation[] };
  free_now: number;
  free_after_all_known: number;
  committed: { unpaid_invoices: number; next_rent: number; total: number };
  uncommitted: number;
}

export interface Approval {
  id: number;
  kind: string;
  ref_id: number | null;
  amount: number;
  account: string;
  reason: string;
  requested_by: string;
  ticket_id: number | null;
  status: "pending" | "approved" | "rejected" | "paid";
  requested_at: string;
  decided_by: string | null;
  decided_at: string | null;
  payment_id: number | null;
}

export interface ActivityStep {
  run_id: string;
  step: number;
  at: string;
  agent: string;
  event: string;
  ticket_id: number | null;
  detail: string;
  tool: string | null;
  arguments: Record<string, unknown> | null;
  instruction: string | null;
  chain: string[] | null;
  usage: Record<string, number>;
}

export interface Resolution {
  ticket_id: number;
  outcome: string;
  summary: string;
  reasoning: string;
  delegated_to: string[];
  actions_taken: string[];
  human_approval_needed: string[];
  customer_or_vendor_drafts: string[];
}

export interface Run {
  run_id: string;
  status: "running" | "finished" | "failed";
  ticket_ids: number[];
  started_at: string;
  finished_at: string | null;
  resolutions: Resolution[];
  usage: Record<string, number>;
  error: string | null;
}

export class ApiError extends Error {}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...init,
    });
  } catch {
    throw new ApiError(`Cannot reach the operations API at ${BASE}.`);
  }
  if (!res.ok) {
    // FastAPI puts the reason in `detail`; surface it rather than a bare code,
    // because these are the refusals the shop's rules produce.
    const body = await res.json().catch(() => null);
    throw new ApiError(body?.detail ?? `${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  base: BASE,
  health: () => req<{ ok: boolean; model: string; working_db: string }>("/api/health"),
  tickets: () => req<TicketsResponse>("/api/tickets"),
  cash: () => req<Cash>("/api/cash"),
  approvals: () => req<{ approvals: Approval[]; note: string }>("/api/approvals"),
  /**
   * Activity, optionally narrowed to one ticket and one run.
   *
   * The dashboard always passes both when something is in focus: mixing two
   * tickets, or two runs of the same ticket, would make the contribution
   * counts meaningless.
   */
  activity: (opts: { limit?: number; runId?: string; ticketId?: number } = {}) => {
    const q = new URLSearchParams({ limit: String(opts.limit ?? 300) });
    if (opts.runId) q.set("run_id", opts.runId);
    if (opts.ticketId !== undefined) q.set("ticket_id", String(opts.ticketId));
    return req<{ runs: number; steps: ActivityStep[] }>(`/api/activity?${q}`);
  },
  runs: () => req<{ runs: Run[] }>("/api/runs"),
  run: (id: string) => req<Run>(`/api/runs/${id}`),
  startRun: (ticket_ids: number[]) =>
    req<{ run_id: string }>("/api/runs", {
      method: "POST",
      body: JSON.stringify({ ticket_ids }),
    }),
  decide: (id: number, decision: "approve" | "reject", authorized_by: string) =>
    req<{ approval_id: number; decision: string; paid: boolean }>(
      `/api/approvals/${id}/decision`,
      { method: "POST", body: JSON.stringify({ decision, authorized_by }) },
    ),
  reset: () => req<{ ok: boolean }>("/api/reset", { method: "POST" }),
};
