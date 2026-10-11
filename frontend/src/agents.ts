/**
 * The five agents, plus the two non-agent actors that appear in the trail.
 *
 * Each agent gets its own hue and initial so a glance at the activity feed
 * reads as five distinct voices rather than one undifferentiated log. The
 * palette stays inside the shop's pink family — these are variations in hue and
 * lightness, not five unrelated colours competing with each other.
 */

export interface AgentStyle {
  key: string;
  label: string;
  initial: string;
  colour: string;
  role: string;
}

export const AGENTS: Record<string, AgentStyle> = {
  boss: {
    key: "boss",
    label: "Boss",
    initial: "B",
    colour: "#ff3d87",
    role: "Owns the ticket. Delegates, decides, records the outcome.",
  },
  inventory: {
    key: "inventory",
    label: "Inventory",
    initial: "I",
    colour: "#ff8ab8",
    role: "Stock on hand, shortfalls, vendor lead times.",
  },
  accounting: {
    key: "accounting",
    label: "Accounting",
    initial: "A",
    colour: "#c86bff",
    role: "Cash, obligations, margin. Stages payments — cannot approve them.",
  },
  facilities: {
    key: "facilities",
    label: "Facilities",
    initial: "F",
    colour: "#ff6f5e",
    role: "The lease, rent amounts and dates.",
  },
  customer_service: {
    key: "customer_service",
    label: "Customer Service",
    initial: "C",
    colour: "#ffb44d",
    role: "Drafts the reply. Nothing is ever sent.",
  },
  "human operator": {
    key: "human operator",
    label: "You",
    initial: "★",
    colour: "#4ade80",
    role: "The only actor that can approve a payment.",
  },
  runner: {
    key: "runner",
    label: "System",
    initial: "·",
    colour: "#6b6b7b",
    role: "Starts and ends the run.",
  },
};

export const TEAM = [
  "boss",
  "inventory",
  "accounting",
  "facilities",
  "customer_service",
] as const;

export function agentStyle(name: string): AgentStyle {
  return (
    AGENTS[name] ?? {
      key: name,
      label: name,
      initial: name.slice(0, 1).toUpperCase(),
      colour: "#6b6b7b",
      role: "",
    }
  );
}

/** Human-readable label for an audit event. */
export const EVENT_LABEL: Record<string, string> = {
  run_started: "run started",
  agent_started: "picked up the ticket",
  agent_finished: "reported back",
  delegation: "handed off",
  tool_call: "called",
  tool_result: "got back",
  approval_requested: "staged a payment",
  human_decision: "decided",
  limit_reached: "was stopped by a limit",
  error: "hit an error",
  run_finished: "run finished",
};
