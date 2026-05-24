import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import { useApp } from "../store";
import { categoryLabel, formatScore, formatValue, scoreColor, sortedCategories } from "../format";
import type { Location, MetricDef, ScorePreviewResponse } from "../types";

type ScoredLoc = ScorePreviewResponse["locations"][0];

export function Score({ metrics }: { metrics: MetricDef[] }) {
  const selected = useApp((s) => s.selected);
  const workingPreferences = useApp((s) => s.workingPreferences);
  const activePresetId = useApp((s) => s.activePresetId);
  const presets = useApp((s) => s.presets);
  const clearLocations = useApp((s) => s.clearLocations);

  const [data, setData] = useState<ScorePreviewResponse | null>(null);
  const [scoring, setScoring] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const fetchIdRef = useRef(0);

  useEffect(() => {
    setErr(null);
    if (selected.length === 0 || workingPreferences.length === 0) {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      setData(null);
      setScoring(false);
      return;
    }
    setScoring(true);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    const id = ++fetchIdRef.current;
    debounceRef.current = setTimeout(async () => {
      try {
        const res = await api.scorePreview(
          selected.map((l) => l.geoid),
          workingPreferences
        );
        if (id !== fetchIdRef.current) return;
        setData(res);
      } catch (e) {
        if (id !== fetchIdRef.current) return;
        const msg = String(e);
        if (msg.includes("404")) clearLocations();
        setErr(msg);
      } finally {
        if (id === fetchIdRef.current) setScoring(false);
      }
    }, 350);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [selected, workingPreferences, clearLocations]);

  const activePreset = presets.find((p) => p.id === activePresetId);

  if (selected.length === 0)
    return <div className="compare empty">Select locations to score.</div>;
  if (workingPreferences.length === 0)
    return (
      <div className="compare empty">
        <span className="spinner" />
      </div>
    );
  if (err) return <div className="compare empty">Error: {err}</div>;

  const dataByGeoid = new Map<string, ScoredLoc>(
    data?.locations.map((l) => [l.location.geoid, l]) ?? []
  );
  const ranked: ScoredLoc[] = [...dataByGeoid.values()].sort((a, b) => {
    const av = a.overall_score ?? -Infinity;
    const bv = b.overall_score ?? -Infinity;
    return bv - av;
  });
  // Locations added since last completed fetch
  const pendingLocs: Location[] = selected.filter((l) => !dataByGeoid.has(l.geoid));

  const mdef: Record<string, MetricDef> = {};
  for (const m of metrics) mdef[m.key] = m;

  const usedKeys = new Set<string>();
  for (const r of ranked) for (const m of r.metrics) usedKeys.add(m.metric_key);
  const usedMetrics = metrics.filter((m) => usedKeys.has(m.key));
  const cats = sortedCategories(usedMetrics.map((m) => m.category));

  const breakdownCols: Array<{ geoid: string; display_name: string; pending: boolean }> = [
    ...ranked.map((r) => ({
      geoid: r.location.geoid,
      display_name: r.location.display_name,
      pending: false,
    })),
    ...pendingLocs.map((l) => ({ geoid: l.geoid, display_name: l.display_name, pending: true })),
  ];

  const totalWeight = ranked.length > 0
    ? ranked[0].metrics.reduce((s, m) => s + m.weight, 0)
    : 0;

  return (
    <div className="compare">
      <div style={{ marginBottom: 12, color: "var(--text-dim)", fontSize: 12, display: "flex", alignItems: "center", gap: 8 }}>
        {activePreset ? (
          <>Preset: <strong style={{ color: "var(--text)" }}>{activePreset.name}</strong></>
        ) : (
          "No preset selected"
        )}
        {scoring && <span className="spinner" />}
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
                <span className="score-aggregate" style={{ color: scoreColor(r.overall_score) }}>
                  {formatScore(r.overall_score)}
                </span>
              </td>
            </tr>
          ))}
          {pendingLocs.map((loc) => (
            <tr key={loc.geoid}>
              <td style={{ color: "var(--text-dim)" }}>—</td>
              <td>
                <div className="metric-label" style={{ color: "var(--text-dim)" }}>
                  {loc.display_name}
                </div>
              </td>
              <td>
                <span className="spinner" />
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {(ranked.length > 0 || pendingLocs.length > 0) && cats.length > 0 && (
        <div style={{ marginTop: 24 }}>
          <h3 style={{ fontSize: 12, textTransform: "uppercase", color: "var(--text-dim)" }}>
            Per-metric breakdown
          </h3>
          <table>
            <thead>
              <tr>
                <th style={{ width: "40%" }}>Metric</th>
                {breakdownCols.map((c) => (
                  <th key={c.geoid}>{c.display_name}</th>
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
                  dataByGeoid={dataByGeoid}
                  breakdownCols={breakdownCols}
                  mdef={mdef}
                  totalWeight={totalWeight}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function CategoryBreakdown({
  category,
  metrics,
  ranked,
  dataByGeoid,
  breakdownCols,
  mdef,
  totalWeight,
}: {
  category: string;
  metrics: MetricDef[];
  ranked: ScoredLoc[];
  dataByGeoid: Map<string, ScoredLoc>;
  breakdownCols: Array<{ geoid: string; display_name: string; pending: boolean }>;
  mdef: Record<string, MetricDef>;
  totalWeight: number;
}) {
  const [collapsed, setCollapsed] = useState(false);
  const items = metrics.filter((m) => m.category === category);
  if (items.length === 0) return null;

  const firstLoaded = ranked[0];

  const itemKeys = new Set(items.map((m) => m.key));

  // Weighted-average score per location for this category
  const catScores = new Map<string, number | null>();
  for (const col of breakdownCols) {
    if (col.pending) { catScores.set(col.geoid, null); continue; }
    const r = dataByGeoid.get(col.geoid);
    if (!r) { catScores.set(col.geoid, null); continue; }
    const catMetrics = r.metrics.filter((sm) => itemKeys.has(sm.metric_key) && sm.score != null);
    if (catMetrics.length === 0) { catScores.set(col.geoid, null); continue; }
    const catWeightTotal = catMetrics.reduce((s, sm) => s + sm.weight, 0);
    const weightedSum = catMetrics.reduce((s, sm) => s + sm.score! * sm.weight, 0);
    catScores.set(col.geoid, catWeightTotal > 0 ? weightedSum / catWeightTotal : null);
  }

  // Max possible pts this category contributes (sum of metric weights / totalWeight)
  const catMetricWeights = firstLoaded?.metrics.filter((m) => itemKeys.has(m.metric_key)) ?? [];
  const catMaxPts = totalWeight > 0
    ? catMetricWeights.reduce((s, m) => s + m.weight, 0) / totalWeight * 100
    : 0;

  // Earned pts per location for this category
  const catEarnedPts = new Map<string, number | null>();
  for (const col of breakdownCols) {
    if (col.pending || totalWeight === 0) { catEarnedPts.set(col.geoid, null); continue; }
    const r = dataByGeoid.get(col.geoid);
    if (!r) { catEarnedPts.set(col.geoid, null); continue; }
    const pts = r.metrics
      .filter((m) => itemKeys.has(m.metric_key) && m.score != null)
      .reduce((s, m) => s + m.score! * m.weight / totalWeight, 0);
    catEarnedPts.set(col.geoid, pts);
  }

  return (
    <>
      <tr className="cat-header" onClick={() => setCollapsed((c) => !c)}>
        <td>
          <span className="cat-chevron">{collapsed ? "▶" : "▼"}</span>
          {categoryLabel(category)}
          <span style={{ color: "var(--text-dim)", fontWeight: 400, fontSize: 11, marginLeft: 4 }}>
            ({catMaxPts.toFixed(1)} pts)
          </span>
        </td>
        {breakdownCols.map((col) => {
          const score = catScores.get(col.geoid);
          const earned = catEarnedPts.get(col.geoid);
          return (
            <td key={col.geoid} style={{ textAlign: "center" }}>
              {col.pending ? (
                <span className="spinner" />
              ) : score != null ? (
                <span style={{ color: scoreColor(score), fontVariantNumeric: "tabular-nums" }}>
                  {formatScore(score)}
                  <span style={{ color: "var(--text-dim)", fontWeight: 400, fontSize: 11, marginLeft: 4 }}>
                    ({earned != null ? earned.toFixed(1) : "—"})
                  </span>
                </span>
              ) : (
                <span style={{ color: "var(--text-dim)" }}>—</span>
              )}
            </td>
          );
        })}
      </tr>
      {!collapsed && items.map((m) => {
        const anyWeight =
          firstLoaded?.metrics.find((x) => x.metric_key === m.key)?.weight ?? 0;
        const metricMaxPts = totalWeight > 0 ? anyWeight / totalWeight * 100 : 0;
        return (
          <tr key={m.key}>
            <td>
              <div className="metric-label">
                {m.label}{" "}
                <span style={{ color: "var(--text-dim)" }}>({metricMaxPts.toFixed(1)} pts)</span>
              </div>
            </td>
            {breakdownCols.map((col) => {
              if (col.pending) {
                return (
                  <td key={col.geoid} className="missing">
                    <span className="spinner" />
                  </td>
                );
              }
              const r = dataByGeoid.get(col.geoid);
              const sm = r?.metrics.find((x) => x.metric_key === m.key);
              if (!sm || sm.score == null) {
                return (
                  <td key={col.geoid} className="missing">
                    —
                  </td>
                );
              }
              const earnedPts = totalWeight > 0 ? sm.score * sm.weight / totalWeight : null;
              return (
                <td key={col.geoid}>
                  <div className="score-cell" style={{ color: scoreColor(sm.score) }}>
                    {formatScore(sm.score)}
                    <span style={{ color: "var(--text-dim)", fontWeight: 400, fontSize: 11 }}>
                      ({earnedPts != null ? earnedPts.toFixed(1) : "—"})
                    </span>
                    <span
                      className="score-bar"
                      style={{
                        width: Math.max(8, sm.score * 0.6),
                        background: scoreColor(sm.score),
                        opacity: 0.5,
                      }}
                    />
                  </div>
                  <div className="metric-source">{formatValue(sm.raw_value, mdef[m.key])}</div>
                </td>
              );
            })}
          </tr>
        );
      })}
    </>
  );
}
