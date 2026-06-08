import type {
  CompareResponse,
  Location,
  MapScoreResponse,
  MetricDef,
  Preference,
  Preset,
  ScorePreviewResponse,
  ScoreResponse,
} from "../types";

const BASE = ""; // proxied by Vite to backend

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const resp = await fetch(BASE + path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`${method} ${path} -> ${resp.status}: ${text}`);
  }
  if (resp.status === 204) return undefined as unknown as T;
  return (await resp.json()) as T;
}

export const api = {
  searchLocations: (q: string, opts?: { level?: string; state?: string; limit?: number }) => {
    const params = new URLSearchParams({ q });
    if (opts?.level) params.set("level", opts.level);
    if (opts?.state) params.set("state", opts.state);
    if (opts?.limit) params.set("limit", String(opts.limit));
    return request<Location[]>("GET", `/api/locations/search?${params.toString()}`);
  },

  getLocation: (geoid: string) =>
    request<Location>("GET", `/api/locations/${encodeURIComponent(geoid)}`),

  listMetrics: () => request<MetricDef[]>("GET", "/api/metrics"),

  compare: (geoids: string[]) =>
    request<CompareResponse>("POST", "/api/compare", { geoids }),

  listPresets: () => request<Preset[]>("GET", "/api/presets"),

  createPreset: (name: string, description?: string) =>
    request<Preset>("POST", "/api/presets", { name, description: description ?? null }),

  getPreset: (id: number) => request<Preset>("GET", `/api/presets/${id}`),

  updatePreset: (id: number, body: { name?: string; description?: string }) =>
    request<Preset>("PATCH", `/api/presets/${id}`, body),

  deletePreset: (id: number) => request<void>("DELETE", `/api/presets/${id}`),

  setPreferences: (id: number, prefs: Preference[]) =>
    request<Preset>(
      "PUT",
      `/api/presets/${id}/preferences`,
      prefs.map(({ id: _omit, ...rest }) => rest)
    ),

  score: (presetId: number, geoids: string[]) =>
    request<ScoreResponse>("POST", "/api/score", { preset_id: presetId, geoids }),

  scorePreview: (geoids: string[], preferences: Preference[]) =>
    request<ScorePreviewResponse>("POST", "/api/score/preview", {
      geoids,
      preferences: preferences.map(({ id: _omit, ...rest }) => rest),
    }),

  scoreMap: (params: { presetId: number; level: "state" | "county"; metricKey?: string }) => {
    const p = new URLSearchParams({ preset_id: String(params.presetId), level: params.level });
    if (params.metricKey) p.set("metric_key", params.metricKey);
    return request<MapScoreResponse>("GET", `/api/score/map?${p.toString()}`);
  },
};
