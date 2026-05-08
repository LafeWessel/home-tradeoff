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

  // Insurance / additional taxes / housing trend
  "housing.insurance_avg_premium": { ideal: 1200, cap: 5000 },
  "tax.retirement.burden_score": { ideal: 0, cap: 3 },
  "tax.capital_gains.top_rate": { ideal: 0, cap: 11 },
  "tax.property.median_annual_bill": { ideal: 2000, cap: 9000 },
  "housing.appreciation_10yr_cagr": { ideal: 6, tolerance: 4 },

  // Hazard sub-scores + air quality + summer heat
  "hazard.hurricane": { ideal: 0, cap: 60 },
  "hazard.wildfire": { ideal: 0, cap: 60 },
  "hazard.tornado": { ideal: 0, cap: 60 },
  "hazard.flood": { ideal: 0, cap: 50 },
  "env.pm25_annual": { ideal: 5, cap: 12 },
  "climate.summer_heat_index_f": { ideal: 85, tolerance: 12 },

  // Utilities & infrastructure
  "utility.electricity_rate": { ideal: 12, cap: 30 },
  "infra.broadband_100_20_pct": { ideal: 95, cap: 75 },
  "infra.airport_hub_distance_mi": { ideal: 30, cap: 250 },

  // Education / health / quality of life
  "edu.k12_proficiency_pct": { ideal: 38, cap: 22 },
  "health.primary_care_per_100k": { ideal: 95, cap: 60 },
  "health.life_expectancy_years": { ideal: 79, cap: 73 },
  "pop.growth_5yr_pct": { ideal: 3, tolerance: 5 },
  "employment.job_growth_5yr_pct": { ideal: 5, cap: -1 },
  "politics.partisan_lean_2024": { ideal: 0, tolerance: 25 },

  // Race / ethnicity (ACS B03002). Defaults loosely track US national shares;
  // tolerances are intentionally wide so the metric doesn't dominate scoring
  // unless the user dials it in.
  "demo.race.white_pct": { ideal: 60, tolerance: 40 },
  "demo.race.black_pct": { ideal: 13, tolerance: 25 },
  "demo.race.hispanic_pct": { ideal: 19, tolerance: 25 },
  "demo.race.asian_pct": { ideal: 6, tolerance: 15 },
  "demo.race.native_american_pct": { ideal: 1, tolerance: 5 },
  "demo.race.other_pct": { ideal: 10, tolerance: 15 },
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
