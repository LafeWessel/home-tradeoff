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

export default function App() {
  const openPanels = useApp((s) => s.openPanels);
  const togglePanel = useApp((s) => s.togglePanel);
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

  // Initialize (and reset after save) working preferences from the active preset.
  useEffect(() => {
    if (!activePresetId || metrics.length === 0 || presets.length === 0) return;
    const preset = presets.find((p) => p.id === activePresetId);
    if (!preset) return;
    const byKey = new Map(preset.preferences.map((p) => [p.metric_key, p]));
    setWorkingPreferences(
      metrics.map((m) => {
        const ex = byKey.get(m.key);
        if (ex) {
          return {
            metric_key: ex.metric_key,
            weight: ex.weight,
            direction: ex.direction ?? m.direction,
            ideal: ex.ideal,
            cap: ex.cap,
            tolerance: ex.tolerance,
            enabled: ex.enabled,
          };
        }
        return defaultPreferenceFor(m);
      })
    );
  }, [activePresetId, presets, metrics, setWorkingPreferences]);

  if (bootErr)
    return (
      <div style={{ padding: 24, color: "var(--bad)" }}>
        Backend unreachable. Is uvicorn running on :8765? <br />
        <code>{bootErr}</code>
      </div>
    );

  return (
    <div className="app">
      <header className="app-header">
        <h1>Home Tradeoff</h1>
        <span style={{ color: "var(--text-dim)", fontSize: 12 }}>
          Compare US locations on the data that matters
        </span>
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

      <MapPane />

      <aside className="sidebar">
        <Search />
        <Tray />
        <div className="panels">
          {openPanels.includes("compare") && (
            <>
              <div className="panel-title">Compare</div>
              <Compare metrics={metrics} />
            </>
          )}
          {openPanels.includes("score") && (
            <>
              <div className="panel-title">Rank</div>
              <Score metrics={metrics} />
            </>
          )}
          {openPanels.includes("prefs") && (
            <>
              <div className="panel-title">Preferences</div>
              <Preferences metrics={metrics} />
            </>
          )}
        </div>
      </aside>
    </div>
  );
}
