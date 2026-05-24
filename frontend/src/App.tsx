import { useEffect, useState } from "react";
import { api } from "./api/client";
import { defaultPreferenceFor } from "./defaults";
import { Compare } from "./components/Compare";
import { MapPane } from "./components/Map";
import { Preferences } from "./components/Preferences";
import { Score } from "./components/Score";
import { Search } from "./components/Search";
import { Tray } from "./components/Tray";
import { useApp } from "./store";
import type { MetricDef } from "./types";

const PANEL_LABELS = { compare: "Compare", score: "Rank", prefs: "Preferences" } as const;
const PANEL_WIDTH = 400;
const DATA_LABEL_WIDTH = 210;
const DATA_LOC_WIDTH = 130;

export default function App() {
  const openPanels = useApp((s) => s.openPanels);
  const togglePanel = useApp((s) => s.togglePanel);
  const selected = useApp((s) => s.selected);
  const setPresets = useApp((s) => s.setPresets);
  const presets = useApp((s) => s.presets);
  const activePresetId = useApp((s) => s.activePresetId);
  const setWorkingPreferences = useApp((s) => s.setWorkingPreferences);
  const [metrics, setMetrics] = useState<MetricDef[]>([]);
  const [bootErr, setBootErr] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.listMetrics(), api.listPresets()])
      .then(([m, p]) => {
        setMetrics(m);
        setPresets(p);
      })
      .catch((e) => setBootErr(String(e)));
  }, [setPresets]);

  // Initialize (and reset after save/preset-switch) working preferences.
  useEffect(() => {
    if (!activePresetId || metrics.length === 0 || presets.length === 0) return;
    const preset = presets.find((p) => p.id === activePresetId);
    if (!preset) return;
    const byKey = new Map(preset.preferences.map((p) => [p.metric_key, p]));
    setWorkingPreferences(
      metrics.map((m) => {
        const ex = byKey.get(m.key);
        if (ex)
          return {
            metric_key: ex.metric_key,
            weight: ex.weight,
            direction: ex.direction ?? m.direction,
            ideal: ex.ideal,
            cap: ex.cap,
            tolerance: ex.tolerance,
            enabled: ex.enabled,
          };
        return defaultPreferenceFor(m);
      })
    );
  }, [activePresetId, presets, metrics, setWorkingPreferences]);

  if (bootErr)
    return (
      <div style={{ padding: 24, color: "var(--bad)" }}>
        Backend unreachable. Is uvicorn running on :8765?
        <br />
        <code>{bootErr}</code>
      </div>
    );

  const dataWidth = Math.max(PANEL_WIDTH, DATA_LABEL_WIDTH + Math.max(1, selected.length) * DATA_LOC_WIDTH);
  const PANEL_ORDER = ["compare", "score", "prefs"] as const;
  const gridCols = `1fr${PANEL_ORDER
    .filter((p) => openPanels.includes(p))
    .map((p) => ` ${p === "compare" || p === "score" ? dataWidth : PANEL_WIDTH}px`)
    .join("")}`;

  return (
    <div className="app" style={{ gridTemplateColumns: gridCols }}>
      <header className="app-header">
        <h1>Home Tradeoff</h1>
        <Search />
        <nav className="nav">
          {(["compare", "score", "prefs"] as const).map((p) => (
            <button
              key={p}
              className={openPanels.includes(p) ? "active" : ""}
              onClick={() => togglePanel(p)}
            >
              {PANEL_LABELS[p]}
            </button>
          ))}
        </nav>
      </header>

      <Tray />

      <MapPane />

      {openPanels.includes("compare") && (
        <aside className="panel-col">
          <div className="panel-col-header">Compare</div>
          <div className="panel-col-body">
            <Compare metrics={metrics} />
          </div>
        </aside>
      )}
      {openPanels.includes("score") && (
        <aside className="panel-col">
          <div className="panel-col-header">Rank</div>
          <div className="panel-col-body">
            <Score metrics={metrics} />
          </div>
        </aside>
      )}
      {openPanels.includes("prefs") && (
        <aside className="panel-col">
          <div className="panel-col-header">Preferences</div>
          <div className="panel-col-body">
            <Preferences metrics={metrics} />
          </div>
        </aside>
      )}
    </div>
  );
}
