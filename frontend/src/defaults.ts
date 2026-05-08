/**
 * Sensible starting points for ideal / cap / tolerance per metric.
 * Tuned to make scoring "do something" out of the box; users will tweak.
 */
import type { MetricDef, Preference } from "./types";

type DefaultSpec = {
  ideal?: number;
  cap?: number;
  tolerance?: number;
};

const DEFAULTS: Record<string, DefaultSpec> = {
  // Taxes — lower better, ideal 0
  "tax.income.top_marginal": { ideal: 0, cap: 11 },
  "tax.sales.combined_avg": { ideal: 0, cap: 10 },
  "tax.property.effective_rate": { ideal: 0.5, cap: 2.5 },
  "tax.estate.has_estate_tax": { ideal: 0, cap: 1 },
  // Tax structure: 'target' on 0=none, tolerance 0.5 lets flat earn partial
  "tax.income.flat_or_progressive": { ideal: 0, tolerance: 1.5 },

  // Housing
  "housing.median_value": { ideal: 350_000, tolerance: 200_000 },
  "housing.median_rent": { ideal: 1_200, cap: 3_000 },
  "housing.owner_occupied_pct": { ideal: 70, cap: 40 },

  // Cost of living (RPP)
  "col.rpp": { ideal: 90, cap: 115 },

  // Climate
  "climate.jan_low_f": { ideal: 35, tolerance: 15 },
  "climate.jul_high_f": { ideal: 82, tolerance: 12 },
  "climate.annual_precip_in": { ideal: 35, tolerance: 25 },
  "hazard.fema_nri": { ideal: 15, cap: 60 },

  // Crime
  "crime.violent_per_100k": { ideal: 200, cap: 800 },
  "crime.property_per_100k": { ideal: 1500, cap: 4000 },

  // Employment
  "employment.unemployment_rate": { ideal: 3.0, cap: 8.0 },

  // Demographics
  "pop.total": { ideal: 100_000, tolerance: 200_000 },
  "pop.median_age": { ideal: 38, tolerance: 8 },
  "econ.median_household_income": { ideal: 90_000, cap: 50_000 },
  "edu.bachelors_or_higher_pct": { ideal: 40, cap: 20 },
};

export function defaultPreferenceFor(m: MetricDef): Preference {
  const d = DEFAULTS[m.key] ?? {};
  return {
    metric_key: m.key,
    weight: 5,
    direction: m.direction,
    ideal: d.ideal ?? null,
    cap: d.cap ?? null,
    tolerance: d.tolerance ?? null,
    enabled: true,
  };
}
