import { useEffect, useState } from "react";
import { api } from "../api/client";
import { useApp } from "../store";
import { categoryLabel, formatScore, formatValue, scoreColor, sortedCategories } from "../format";
import type { MetricDef, ScoreResponse } from "../types";

export function Score({ metrics }: { metrics: MetricDef[] }) {
  const selected = useApp((s) => s.selected);
  const activePresetId = useApp((s) => s.activePresetId);
  const [data, setData] = useState<ScoreResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    setData(null);
    setErr(null);
    if (selected.length === 0 || activePresetId == null) return;
    setLoading(true);
    api
      .score(activePresetId, selected.map((s) => s.geoid))
      .then(setData)
      .catch((e) => setErr(String(e)))
      .finally(() => setLoading(false));
  }, [selected, activePresetId]);

  if (selected.length === 0)
    return <div className="compare empty">Select locations to score.</div>;
  if (activePresetId == null)
    return <div className="compare empty">Create or activate a preset in the Preferences tab.</div>;
  if (loading) return <div className="compare empty">Scoring…</div>;
  if (err) return <div className="compare empty">Error: {err}</div>;
  if (!data) return null;

  // Sort by score descending; nulls last.
  const ranked = [...data.locations].sort((a, b) => {
    const av = a.overall_score ?? -Infinity;
    const bv = b.overall_score ?? -Infinity;
    return bv - av;
  });

  // Build a metric->def lookup
  const mdef: Record<string, MetricDef> = {};
  for (const m of metrics) mdef[m.key] = m;

  const usedKeys = new Set<string>();
  for (const r of ranked) for (const m of r.metrics) usedKeys.add(m.metric_key);
  const usedMetrics = metrics.filter((m) => usedKeys.has(m.key));
  const cats = sortedCategories(usedMetrics.map((m) => m.category));

  return (
    <div className="compare">
      <div style={{ marginBottom: 12, color: "var(--text-dim)", fontSize: 12 }}>
        Preset: <strong style={{ color: "var(--text)" }}>{data.preset.name}</strong>
        {data.preset.description ? ` — ${data.preset.description}` : ""}
      </div>
      <table>
        <thead>
          <tr>
            <th>Rank</th>
            <th>Location</th>
            <th>Score</th>
          </tr>
        </thead>
        <tbody>
          {ranked.map((r, i) => (
            <tr key={r.location.geoid}>
              <td style={{ fontVariantNumeric: "tabular-nums", fontWeight: 600 }}>{i + 1}</td>
              <td>
                <div className="metric-label">{r.location.display_name}</div>
                {r.missing_metric_keys.length > 0 && (
                  <div className="metric-source">
                    {r.missing_metric_keys.length} metric(s) missing
                  </div>
                )}
              </td>
              <td>
                <span
                  className="score-aggregate"
                  style={{ color: scoreColor(r.overall_score) }}
                >
                  {formatScore(r.overall_score)}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <div style={{ marginTop: 24 }}>
        <h3 style={{ fontSize: 12, textTransform: "uppercase", color: "var(--text-dim)" }}>
          Per-metric breakdown
        </h3>
        <table>
          <thead>
            <tr>
              <th style={{ width: "40%" }}>Metric (weight)</th>
              {ranked.map((r) => (
                <th key={r.location.geoid}>{r.location.display_name}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {cats.map((cat) => (
              <CategoryBreakdown
                key={cat}
                category={cat}
                metrics={usedMetrics}
                ranked={ranked}
                mdef={mdef}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function CategoryBreakdown({
  category,
  metrics,
  ranked,
  mdef,
}: {
  category: string;
  metrics: MetricDef[];
  ranked: ScoreResponse["locations"];
  mdef: Record<string, MetricDef>;
}) {
  const items = metrics.filter((m) => m.category === category);
  if (items.length === 0) return null;
  return (
    <>
      <tr className="cat-header">
        <td colSpan={ranked.length + 1}>{categoryLabel(category)}</td>
      </tr>
      {items.map((m) => {
        const anyWeight = ranked[0]?.metrics.find((x) => x.metric_key === m.key)?.weight ?? 0;
        return (
          <tr key={m.key}>
            <td>
              <div className="metric-label">
                {m.label} <span style={{ color: "var(--text-dim)" }}>(w {anyWeight.toFixed(0)})</span>
              </div>
            </td>
            {ranked.map((r) => {
              const sm = r.metrics.find((x) => x.metric_key === m.key);
              if (!sm || sm.score == null) {
                return (
                  <td key={r.location.geoid} className="missing">
                    —
                  </td>
                );
              }
              return (
                <td key={r.location.geoid}>
                  <div className="score-cell" style={{ color: scoreColor(sm.score) }}>
                    {formatScore(sm.score)}
                    <span
                      className="score-bar"
                      style={{
                        width: Math.max(8, sm.score * 0.6),
                        background: scoreColor(sm.score),
                        opacity: 0.5,
                      }}
                    />
                  </div>
                  <div className="metric-source">
                    {formatValue(sm.raw_value, mdef[m.key])}
                  </div>
                </td>
              );
            })}
          </tr>
        );
      })}
    </>
  );
}
