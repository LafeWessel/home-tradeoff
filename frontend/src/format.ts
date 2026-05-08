import type { MetricDef } from "./types";

export function formatValue(v: number | null | undefined, m: MetricDef): string {
  if (v == null || Number.isNaN(v)) return "—";
  switch (m.unit) {
    case "$":
      return v >= 1e6
        ? `$${(v / 1e6).toFixed(2)}M`
        : v >= 1e3
        ? `$${(v / 1e3).toFixed(0)}k`
        : `$${Math.round(v).toLocaleString()}`;
    case "$/mo":
      return `$${Math.round(v).toLocaleString()}/mo`;
    case "%":
      return `${v.toFixed(2)}%`;
    case "°F":
      return `${Math.round(v)}°F`;
    case "in":
      return `${v.toFixed(1)} in`;
    case "people":
      return v >= 1e6
        ? `${(v / 1e6).toFixed(2)}M`
        : v >= 1e3
        ? `${(v / 1e3).toFixed(0)}k`
        : `${Math.round(v).toLocaleString()}`;
    case "years":
      return `${v.toFixed(1)} yr`;
    case "per 100k":
      return `${Math.round(v).toLocaleString()}`;
    case "bool":
      return v >= 0.5 ? "Yes" : "No";
    case "text": {
      // Special: tax structure encoded as 0/1/2
      if (m.key === "tax.income.flat_or_progressive") {
        return ({ 0: "None", 1: "Flat", 2: "Progressive" } as Record<number, string>)[
          Math.round(v)
        ] ?? "—";
      }
      return String(v);
    }
    default:
      return v.toFixed(2);
  }
}

export function formatScore(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return "—";
  return v.toFixed(0);
}

export function scoreColor(v: number | null | undefined): string {
  if (v == null) return "var(--text-dim)";
  if (v >= 75) return "var(--good)";
  if (v >= 50) return "var(--accent)";
  if (v >= 25) return "var(--warn)";
  return "var(--bad)";
}

const CATEGORY_LABELS: Record<string, string> = {
  taxes: "Taxes",
  housing: "Housing",
  cost_of_living: "Cost of living",
  climate: "Climate & hazards",
  crime: "Crime",
  employment: "Employment",
  demographics: "Demographics",
};

export function categoryLabel(c: string): string {
  return CATEGORY_LABELS[c] ?? c;
}

const CATEGORY_ORDER = [
  "taxes",
  "housing",
  "cost_of_living",
  "climate",
  "crime",
  "employment",
  "demographics",
];

export function sortedCategories(cats: string[]): string[] {
  return [...new Set(cats)].sort(
    (a, b) => CATEGORY_ORDER.indexOf(a) - CATEGORY_ORDER.indexOf(b)
  );
}
