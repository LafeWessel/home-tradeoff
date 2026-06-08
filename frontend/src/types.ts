export type GeoLevel = "state" | "county" | "place";

export interface Location {
  id: number;
  geoid: string;
  level: GeoLevel;
  name: string;
  display_name: string;
  state_abbr: string | null;
  state_fips: string | null;
  parent_geoid: string | null;
  population: number | null;
  lat: number | null;
  lon: number | null;
}

export interface MetricDef {
  key: string;
  label: string;
  category: string;
  unit: string;
  direction: "lower_better" | "higher_better" | "target";
  description: string;
  source_label: string;
  finest_level: GeoLevel;
}

export interface MetricValue {
  value: number | null;
  source: string | null;
  source_year: number | null;
  fetched_at: string | null;
  level_resolved: GeoLevel | null;
  resolved_geoid: string | null;
}

export interface LocationMetrics {
  location: Location;
  metrics: Record<string, MetricValue>;
}

export interface CompareResponse {
  metrics: MetricDef[];
  locations: LocationMetrics[];
}

export interface Preference {
  id?: number;
  metric_key: string;
  weight: number;
  direction: "lower_better" | "higher_better" | "target" | null;
  ideal: number | null;
  cap: number | null;
  tolerance: number | null;
  enabled: boolean;
}

export interface Preset {
  id: number;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
  preferences: (Preference & { id: number })[];
}

export interface ScoredMetric {
  metric_key: string;
  raw_value: number | null;
  score: number | null;
  weight: number;
  direction: string;
  ideal: number | null;
  cap: number | null;
  tolerance: number | null;
  level_resolved: GeoLevel | null;
}

export interface ScoredLocation {
  location: Location;
  overall_score: number | null;
  metrics: ScoredMetric[];
  missing_metric_keys: string[];
}

export interface ScoreResponse {
  preset: Preset;
  locations: ScoredLocation[];
}

export interface ScorePreviewResponse {
  locations: ScoredLocation[];
}

export interface MapScoreEntry {
  score: number | null;
  raw_value: number | null;
  lat: number | null;
  lon: number | null;
}

export interface MapScoreResponse {
  scores: Record<string, MapScoreEntry>;
}
