import { useEffect, useState } from "react";
import { api } from "./api/client";
import { Compare } from "./components/Compare";
import { MapPane } from "./components/Map";
import { Preferences } from "./components/Preferences";
import { Score } from "./components/Score";
import { Search } from "./components/Search";
import { Tray } from "./components/Tray";
import { useApp } from "./store";
import type { MetricDef } from "./types";

export default function App() {
  const tab = useApp((s) => s.activeTab);
  const setTab = useApp((s) => s.setTab);
  const setPresets = useApp((s) => s.setPresets);
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
          <button className={tab === "compare" ? "active" : ""} onClick={() => setTab("compare")}>
            Compare
          </button>
          <button className={tab === "score" ? "active" : ""} onClick={() => setTab("score")}>
            Rank
          </button>
          <button className={tab === "prefs" ? "active" : ""} onClick={() => setTab("prefs")}>
            Preferences
          </button>
        </nav>
      </header>

      <MapPane />

      <aside className="sidebar">
        <Search />
        <Tray />
        {tab === "compare" && <Compare metrics={metrics} />}
        {tab === "score" && <Score metrics={metrics} />}
        {tab === "prefs" && <Preferences metrics={metrics} />}
      </aside>
    </div>
  );
}
