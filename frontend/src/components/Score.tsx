import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import { useApp } from "../store";
import { categoryLabel, formatScore, formatValue, scoreColor, sortedCategories } from "../format";
import type { Location, MetricDef, ScoreResponse } from "../types";

type ScoredLoc = ScoreResponse["locations"][0];

export function Score({ metrics }: { metrics: MetricDef[] }) {
  const selected = useApp((s) => s.selected);
  const activePresetId = useApp((s) => s.activePresetId);
  const [data, setData] = useState<ScoreResponse | null>(null);
  const [pendingGeoids, setPendingGeoids] = useState<Set<string>>(new Set());
  const [err, setErr] = useState<string | null>(null);
  const fetchIdRef = useRef(0);
  const loadedGeoidSetRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    setErr(null);
    if (selected.length === 0 || activePresetId == null) {
      setData(null);
      setPendingGeoids(new Set());
      loadedGeoidSetRef.current = new Set();
      return;
    }
    const id = ++fetchIdRef.current;
    setPendingGeoids(
      new Set(selected.map((l) => l.geoid).filter((g) => !loadedGeoidSetRef.current.has(g)))
    );
    api
      .score(activePresetId, selected.map((s) => s.geoid))
      .then((res) => {
        if (id !== fetchIdRef.current) return;
        loadedGeoidSetRef.current = new Set(res.locations.map((l) => l.location.geoid));
        setData(res);
        setPendingGeoids(new Set());
      })
      .catch((e) => {
        if (id !== fetchIdRef.current) return;
        setErr(String(e));
        setPendingGeoids(new Set());
      });
  }, [selected, activePresetId]);

  if (selected.length === 0)
    return <div className="compare empty">Select locations to score.</div>;
  if (activePresetId == null)
    return <div className="compare empty">Create or activate a preset in the Preferences tab.</div>;
  if (err) return <div className="compare empty">Error: {err}</div>;

  // Loaded locations, sorted by score descending
  const dataByGeoid = new Map<string, ScoredLoc>(
    data?.locations.map((l) => [l.location.geoid, l]) ?? []
  );
  const ranked: ScoredLoc[] = [...dataByGeoid.values()].sort((a, b) => {
    const av = a.overall_score ?? -Infinity;
    const bv = b.overall_score ?? -Infinity;
    return bv - av;
  });
  const pendingLocs: Location[] = selected.filter((l) => pendingGeoids.has(l.geoid));

  const mdef: Record<string, MetricDef> = {};
  for (const m of metrics) mdef[m.key] = m;

  const usedKeys = new Set<string>();
  for (const r of ranked) for (const m of r.metrics) usedKeys.add(m.metric_key);
  const usedMetrics = metrics.filter((m) => usedKeys.has(m.key));
  const cats = sortedCategories(usedMetrics.map((m) => m.category));

  // Column order for breakdown: ranked loaded + pending at end
  const breakdownCols: Array<{ geoid: string; display_name: string; pending: boolean }> = [
    ...ranked.map((r) => ({ geoid: r.location.geoid, display_name: r.location.display_name, pending: false })),
    ...pendingLocs.map((l) => ({ geoid: l.geoid, display_name: l.display_name, pending: true })),
  ];

  return (
    <div className="compare">
      {data && (
        <div style={{ marginBottom: 12, color: "var(--text-dim)", fontSize: 12 }}>
          Preset: <strong style={{ color: "var(--text)" }}>{data.preset.name}</strong>
          {data.preset.description ? ` — ${data.preset.description}` : ""}
        </div>
      )}

      {/* Summary rank table */}
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
              <td><span className="spinner" /></td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* Per-metric breakdown — only shown once we have at least one loaded location */}
      {(ranked.length > 0 || pendingLocs.length > 0) && cats.length > 0 && (
        <div style={{ marginTop: 24 }}>
          <h3 style={{ fontSize: 12, textTransform: "uppercase", color: "var(--text-dim)" }}>
            Per-metric breakdown
          </h3>
          <table>
            <thead>
              <tr>
                <th style={{ width: "40%" }}>Metric (weight)</th>
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
}: {
  category: string;
  metrics: MetricDef[];
  ranked: ScoredLoc[];
  dataByGeoid: Map<string, ScoredLoc>;
  breakdownCols: Array<{ geoid: string; display_name: string; pending: boolean }>;
  mdef: Record<string, MetricDef>;
}) {
  const items = metrics.filter((m) => m.category === category);
  if (items.length === 0) return null;

  const firstLoaded = ranked[0];

  return (
    <>
      <tr className="cat-header">
        <td colSpan={breakdownCols.length + 1}>{categoryLabel(category)}</td>
      </tr>
      {items.map((m) => {
        const anyWeight =
          firstLoaded?.metrics.find((x) => x.metric_key === m.key)?.weight ?? 0;
        return (
          <tr key={m.key}>
            <td>
              <div className="metric-label">
                {m.label}{" "}
                <span style={{ color: "var(--text-dim)" }}>(w {anyWeight.toFixed(0)})</span>
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
              return (
                <td key={col.geoid}>
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
