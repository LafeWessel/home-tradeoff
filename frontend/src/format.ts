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
    case "$/yr":
      return `$${Math.round(v).toLocaleString()}/yr`;
    case "%":
      return `${v.toFixed(2)}%`;
    case "ppts":
      return `${v >= 0 ? "+" : ""}${v.toFixed(1)}`;
    case "¢/kWh":
      return `${v.toFixed(1)}¢`;
    case "µg/m³":
      return `${v.toFixed(1)} µg/m³`;
    case "mi":
      return v >= 100 ? `${Math.round(v)} mi` : `${v.toFixed(1)} mi`;
    case "0–100":
    case "0–3":
      return v.toFixed(0);
    case "days":
      return `${Math.round(v)} d`;
    case "mph":
      return `${v.toFixed(1)} mph`;
    case "index (US=100)":
      return v.toFixed(1);
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
  utilities: "Utilities & connectivity",
  climate: "Climate & hazards",
  crime: "Crime",
  employment: "Employment",
  health: "Health",
  environment: "Environment",
  demographics: "Demographics & education",
  infrastructure: "Infrastructure",
  politics: "Politics",
  law: "Law",
  outdoor: "Outdoor recreation",
};

export function categoryLabel(c: string): string {
  return CATEGORY_LABELS[c] ?? c;
}

const CATEGORY_ORDER = [
  "taxes",
  "housing",
  "cost_of_living",
  "utilities",
  "climate",
  "crime",
  "employment",
  "health",
  "environment",
  "demographics",
  "infrastructure",
  "politics",
  "law",
  "outdoor",
];

export function sortedCategories(cats: string[]): string[] {
  return [...new Set(cats)].sort((a, b) => {
    const ai = CATEGORY_ORDER.indexOf(a);
    const bi = CATEGORY_ORDER.indexOf(b);
    return (ai === -1 ? Infinity : ai) - (bi === -1 ? Infinity : bi);
  });
}
