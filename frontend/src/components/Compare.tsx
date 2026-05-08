import { useEffect, useState } from "react";
import { api } from "../api/client";
import { useApp } from "../store";
import { categoryLabel, formatValue, sortedCategories } from "../format";
import type { CompareResponse, MetricDef } from "../types";

export function Compare() {
  const selected = useApp((s) => s.selected);
  const [data, setData] = useState<CompareResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    setData(null);
    setErr(null);
    if (selected.length === 0) return;
    setLoading(true);
    api
      .compare(selected.map((s) => s.geoid))
      .then(setData)
      .catch((e) => setErr(String(e)))
      .finally(() => setLoading(false));
  }, [selected]);

  if (selected.length === 0)
    return <div className="compare empty">Select two or more locations to compare.</div>;
  if (loading) return <div className="compare empty">Loading…</div>;
  if (err) return <div className="compare empty">Error: {err}</div>;
  if (!data) return null;

  const cats = sortedCategories(data.metrics.map((m) => m.category));

  return (
    <div className="compare">
      <table>
        <thead>
          <tr>
            <th style={{ width: "30%" }}>Metric</th>
            {data.locations.map((l) => (
              <th key={l.location.geoid}>{l.location.display_name}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {cats.map((cat) => (
            <CategoryRows key={cat} category={cat} data={data} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CategoryRows({ category, data }: { category: string; data: CompareResponse }) {
  const metrics = data.metrics.filter((m) => m.category === category);
  return (
    <>
      <tr className="cat-header">
        <td colSpan={data.locations.length + 1}>{categoryLabel(category)}</td>
      </tr>
      {metrics.map((m) => (
        <MetricRow key={m.key} metric={m} data={data} />
      ))}
    </>
  );
}

function MetricRow({ metric, data }: { metric: MetricDef; data: CompareResponse }) {
  // Compute best/worst across this row using direction.
  const numericValues: { geoid: string; v: number }[] = [];
  for (const l of data.locations) {
    const v = l.metrics[metric.key]?.value;
    if (v != null && !Number.isNaN(v)) numericValues.push({ geoid: l.location.geoid, v });
  }
  let bestGid: string | null = null;
  let worstGid: string | null = null;
  if (numericValues.length >= 2 && metric.unit !== "bool" && metric.unit !== "text") {
    const sorted = [...numericValues].sort((a, b) => a.v - b.v);
    if (metric.direction === "lower_better") {
      bestGid = sorted[0].geoid;
      worstGid = sorted[sorted.length - 1].geoid;
    } else if (metric.direction === "higher_better") {
      bestGid = sorted[sorted.length - 1].geoid;
      worstGid = sorted[0].geoid;
    }
  }

  return (
    <tr>
      <td>
        <div className="metric-label">
          {metric.label}{" "}
          <span style={{ color: "var(--text-dim)", fontWeight: 400 }}>({metric.unit})</span>
        </div>
        <div className="metric-source">{metric.source_label}</div>
      </td>
      {data.locations.map((l) => {
        const mv = l.metrics[metric.key];
        const isBest = bestGid === l.location.geoid;
        const isWorst = worstGid === l.location.geoid;
        const cls = isBest ? "best" : isWorst ? "worst" : "";
        if (mv?.value == null) {
          return (
            <td key={l.location.geoid} className="missing">
              —
            </td>
          );
        }
        return (
          <td key={l.location.geoid} className={cls}>
            {formatValue(mv.value, metric)}
            {mv.level_resolved && mv.level_resolved !== l.location.level && (
              <span className="resolved-tag" title="Inherited from coarser level">
                {mv.level_resolved}
              </span>
            )}
            {mv.source_year && (
              <div className="metric-source">
                {mv.source} ’{String(mv.source_year).slice(-2)}
              </div>
            )}
          </td>
        );
      })}
    </tr>
  );
}
