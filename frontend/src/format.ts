export const money = (n: number | null | undefined) =>
  n === null || n === undefined
    ? "—"
    : n.toLocaleString("en-US", { style: "currency", currency: "USD" });

export const time = (iso: string) => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
};

export const titleCase = (s: string) =>
  s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
