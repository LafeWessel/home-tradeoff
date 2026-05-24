import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import { useApp } from "../store";
import { categoryLabel, formatValue, sortedCategories } from "../format";
import type { CompareResponse, Location, MetricDef, MetricValue } from "../types";

type LocData = CompareResponse["locations"][0];

export function Compare({ metrics }: { metrics: MetricDef[] }) {
  const selected = useApp((s) => s.selected);
  const clearLocations = useApp((s) => s.clearLocations);
  const [data, setData] = useState<CompareResponse | null>(null);
  const [pendingGeoids, setPendingGeoids] = useState<Set<string>>(new Set());
  const [err, setErr] = useState<string | null>(null);
  const fetchIdRef = useRef(0);
  const loadedGeoidSetRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    setErr(null);
    if (selected.length === 0) {
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
      .compare(selected.map((s) => s.geoid))
      .then((res) => {
        if (id !== fetchIdRef.current) return;
        loadedGeoidSetRef.current = new Set(res.locations.map((l) => l.location.geoid));
        setData(res);
        setPendingGeoids(new Set());
      })
      .catch((e) => {
        if (id !== fetchIdRef.current) return;
        // Stale persisted locations — their geoids no longer exist in the DB.
        if (String(e).includes("404")) clearLocations();
        setErr(String(e));
        setPendingGeoids(new Set());
      });
  }, [selected, clearLocations]);

  if (selected.length === 0)
    return <div className="compare empty">Select two or more locations to compare.</div>;
  if (err) return <div className="compare empty">Error: {err}</div>;

  const dataByGeoid = new Map<string, LocData>(
    data?.locations.map((l) => [l.location.geoid, l]) ?? []
  );
  const metricList = data?.metrics.length ? data.metrics : metrics;
  const cats = sortedCategories(metricList.map((m) => m.category));

  return (
    <div className="compare">
      <table>
        <thead>
          <tr>
            <th className="metric-col-header" style={{ width: "30%" }}>Metric</th>
            {selected.map((l) => (
              <th key={l.geoid} className={`loc-col-header level-${l.level}`}>
                {l.display_name}
                <div className={`level-pill ${l.level}`}>{l.level}</div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {cats.map((cat) => (
            <CategoryRows
              key={cat}
              category={cat}
              metrics={metricList}
              selected={selected}
              dataByGeoid={dataByGeoid}
              pendingGeoids={pendingGeoids}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CategoryRows({
  category,
  metrics,
  selected,
  dataByGeoid,
  pendingGeoids,
}: {
  category: string;
  metrics: MetricDef[];
  selected: Location[];
  dataByGeoid: Map<string, LocData>;
  pendingGeoids: Set<string>;
}) {
  const [open, setOpen] = useState(true);
  const catMetrics = metrics.filter((m) => m.category === category);
  return (
    <>
      <tr className="cat-header" onClick={() => setOpen((o) => !o)}>
        <td colSpan={selected.length + 1}>
          <span className="cat-chevron">{open ? "▾" : "▸"}</span>
          {categoryLabel(category)}
          <span className="cat-count">{catMetrics.length}</span>
        </td>
      </tr>
      {open && catMetrics.map((m) => (
        <MetricRow
          key={m.key}
          metric={m}
          selected={selected}
          dataByGeoid={dataByGeoid}
          pendingGeoids={pendingGeoids}
        />
      ))}
    </>
  );
}

function MetricRow({
  metric,
  selected,
  dataByGeoid,
  pendingGeoids,
}: {
  metric: MetricDef;
  selected: Location[];
  dataByGeoid: Map<string, LocData>;
  pendingGeoids: Set<string>;
}) {
  const numericValues: { geoid: string; v: number }[] = [];
  for (const loc of selected) {
    if (pendingGeoids.has(loc.geoid)) continue;
    const v = dataByGeoid.get(loc.geoid)?.metrics[metric.key]?.value;
    if (v != null && !Number.isNaN(v)) numericValues.push({ geoid: loc.geoid, v });
  }
  let bestGid: string | null = null;
  let worstGid: string | null = null;
  if (numericValues.length >= 2 && metric.unit !== "bool" && metric.unit !== "text") {
    const sorted = [...numericValues].sort((a, b) => a.v - b.v);
    if (sorted[0].v !== sorted[sorted.length - 1].v) {
      if (metric.direction === "lower_better") {
        bestGid = sorted[0].geoid;
        worstGid = sorted[sorted.length - 1].geoid;
      } else if (metric.direction === "higher_better") {
        bestGid = sorted[sorted.length - 1].geoid;
        worstGid = sorted[0].geoid;
      }
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
      {selected.map((loc) => {
        if (pendingGeoids.has(loc.geoid)) {
          return (
            <td key={loc.geoid} className="missing">
              <span className="spinner" />
            </td>
          );
        }
        const mv: MetricValue | undefined = dataByGeoid.get(loc.geoid)?.metrics[metric.key];
        const isBest = bestGid === loc.geoid;
        const isWorst = worstGid === loc.geoid;
        const cls = isBest ? "best" : isWorst ? "worst" : "";
        if (mv?.value == null) {
          return (
            <td key={loc.geoid} className="missing">
              —
            </td>
          );
        }
        return (
          <td key={loc.geoid} className={cls}>
            {formatValue(mv.value, metric)}
            {mv.level_resolved && mv.level_resolved !== loc.level && (
              <span
                className={`resolved-tag${mv.level_resolved === "state" ? " resolved-tag--state" : ""}`}
                title={
                  mv.level_resolved === "state"
                    ? "No county data — showing statewide average"
                    : "Showing county average (no city-level data)"
                }
              >
                ~{mv.level_resolved}
              </span>
            )}
            {mv.source_year && (
              <div className="metric-source">
                {mv.source} '{String(mv.source_year).slice(-2)}
              </div>
            )}
          </td>
        );
      })}
    </tr>
  );
}
