import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api/client";
import { defaultPreferenceFor } from "../defaults";
import { categoryLabel, formatScore, scoreColor, sortedCategories } from "../format";
import { useApp } from "../store";
import type { MetricDef, Preference, Preset, ScorePreviewResponse } from "../types";

interface Props {
  metrics: MetricDef[];
}

export function Preferences({ metrics }: Props) {
  const presets = useApp((s) => s.presets);
  const setPresets = useApp((s) => s.setPresets);
  const activePresetId = useApp((s) => s.activePresetId);
  const setActivePresetId = useApp((s) => s.setActivePresetId);
  const selected = useApp((s) => s.selected);

  const [working, setWorking] = useState<Preference[]>([]);
  const [dirty, setDirty] = useState(false);
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [newPresetName, setNewPresetName] = useState("");
  const [liveScores, setLiveScores] = useState<ScorePreviewResponse | null>(null);
  const [scoring, setScoring] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const active = useMemo(
    () => presets.find((p) => p.id === activePresetId) ?? null,
    [presets, activePresetId]
  );

  // Load working state when active preset changes
  useEffect(() => {
    if (!active) {
      setWorking([]);
      return;
    }
    // Merge: each catalog metric gets a row; missing prefs use defaults.
    const byKey = new Map(active.preferences.map((p) => [p.metric_key, p]));
    const merged: Preference[] = metrics.map((m) => {
      const existing = byKey.get(m.key);
      if (existing) {
        return {
          metric_key: existing.metric_key,
          weight: existing.weight,
          direction: existing.direction ?? m.direction,
          ideal: existing.ideal,
          cap: existing.cap,
          tolerance: existing.tolerance,
          enabled: existing.enabled,
        };
      }
      return defaultPreferenceFor(m);
    });
    setWorking(merged);
    setDirty(false);
  }, [active, metrics]);

  // Live scoring: re-score whenever working prefs or selected locations change
  useEffect(() => {
    if (selected.length === 0 || working.length === 0) {
      setLiveScores(null);
      return;
    }
    if (debounceRef.current) clearTimeout(debounceRef.current);
    setScoring(true);
    debounceRef.current = setTimeout(async () => {
      try {
        const res = await api.scorePreview(
          selected.map((l) => l.geoid),
          working
        );
        setLiveScores(res);
      } catch {
        // silently ignore preview errors — stale scores are fine
      } finally {
        setScoring(false);
      }
    }, 350);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [working, selected]);

  const updateRow = (metric_key: string, patch: Partial<Preference>) => {
    setWorking((rows) =>
      rows.map((r) => (r.metric_key === metric_key ? { ...r, ...patch } : r))
    );
    setDirty(true);
  };

  const save = async () => {
    if (!active) return;
    setBusy(true);
    try {
      const updated = await api.setPreferences(active.id, working);
      setPresets(presets.map((p) => (p.id === updated.id ? updated : p)));
      setDirty(false);
      setSavedAt(Date.now());
    } catch (e) {
      alert(`Save failed: ${e}`);
    } finally {
      setBusy(false);
    }
  };

  const createPreset = async () => {
    const name = newPresetName.trim();
    if (!name) return;
    setBusy(true);
    try {
      const created = await api.createPreset(name);
      // seed with default prefs for every metric so it's usable immediately
      const defaults = metrics.map((m) => defaultPreferenceFor(m));
      const withPrefs = await api.setPreferences(created.id, defaults);
      const list = await api.listPresets();
      setPresets(list);
      setActivePresetId(withPrefs.id);
      setNewPresetName("");
    } catch (e) {
      alert(`Create failed: ${e}`);
    } finally {
      setBusy(false);
    }
  };

  const deleteActive = async () => {
    if (!active) return;
    if (!confirm(`Delete preset "${active.name}"?`)) return;
    setBusy(true);
    try {
      await api.deletePreset(active.id);
      const list = await api.listPresets();
      setPresets(list);
    } catch (e) {
      alert(`Delete failed: ${e}`);
    } finally {
      setBusy(false);
    }
  };

  const cats = sortedCategories(metrics.map((m) => m.category));

  return (
    <div className="prefs">
      <div className="preset-list">
        {presets.map((p) => (
          <button
            key={p.id}
            className={`preset-btn ${p.id === activePresetId ? "active" : ""}`}
            onClick={() => setActivePresetId(p.id)}
          >
            {p.name}
          </button>
        ))}
      </div>

      <div className="new-preset">
        <input
          type="text"
          placeholder="New preset name (e.g., 'retirement')"
          value={newPresetName}
          onChange={(e) => setNewPresetName(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && createPreset()}
        />
        <button
          className="preset-btn"
          disabled={busy || !newPresetName.trim()}
          onClick={createPreset}
        >
          + New
        </button>
      </div>

      {active ? (
        <>
          <div className="preset-actions">
            <button className="primary" disabled={!dirty || busy} onClick={save}>
              {busy ? "Saving…" : dirty ? "Save changes" : "Saved"}
            </button>
            <button className="danger" onClick={deleteActive} disabled={busy}>
              Delete preset
            </button>
            <span className={`save-status ${dirty ? "dirty" : savedAt ? "saved" : ""}`}>
              {dirty
                ? "Unsaved changes"
                : savedAt
                ? `Saved ${new Date(savedAt).toLocaleTimeString()}`
                : ""}
            </span>
          </div>

          {selected.length > 0 && (
            <div className="live-rank">
              <div className="live-rank-header">
                Live rankings
                {scoring && <span className="spinner" style={{ marginLeft: 6 }} />}
              </div>
              {liveScores
                ? [...liveScores.locations]
                    .sort((a, b) => (b.overall_score ?? -Infinity) - (a.overall_score ?? -Infinity))
                    .map((loc, i) => (
                      <div key={loc.location.geoid} className="live-rank-row">
                        <span className="live-rank-pos">{i + 1}</span>
                        <span className="live-rank-name">{loc.location.display_name}</span>
                        <span
                          className="live-rank-score"
                          style={{ color: scoreColor(loc.overall_score) }}
                        >
                          {formatScore(loc.overall_score)}
                        </span>
                      </div>
                    ))
                : !scoring && (
                    <div style={{ color: "var(--text-dim)", fontSize: 12 }}>
                      Adjust preferences to see live rankings.
                    </div>
                  )}
            </div>
          )}

          {cats.map((cat) => (
            <div className="cat-section" key={cat}>
              <h4>{categoryLabel(cat)}</h4>
              {metrics
                .filter((m) => m.category === cat)
                .map((m) => {
                  const row = working.find((r) => r.metric_key === m.key);
                  if (!row) return null;
                  return (
                    <PreferenceRow
                      key={m.key}
                      metric={m}
                      pref={row}
                      onChange={(patch) => updateRow(m.key, patch)}
                    />
                  );
                })}
            </div>
          ))}
        </>
      ) : (
        <div style={{ color: "var(--text-dim)", padding: "12px 0" }}>
          Create a preset to start defining preferences.
        </div>
      )}
    </div>
  );
}

function PreferenceRow({
  metric,
  pref,
  onChange,
}: {
  metric: MetricDef;
  pref: Preference;
  onChange: (patch: Partial<Preference>) => void;
}) {
  const direction = pref.direction ?? metric.direction;
  return (
    <div className={`pref-row ${pref.enabled ? "" : "disabled"}`}>
      <div className="top">
        <input
          type="checkbox"
          checked={pref.enabled}
          onChange={(e) => onChange({ enabled: e.target.checked })}
          title="Include this metric in scoring"
        />
        <label>
          {metric.label}{" "}
          <span className="unit">
            ({metric.unit} • finest: {metric.finest_level})
          </span>
        </label>
      </div>
      <div className="desc">{metric.description}</div>
      <div className="weight">
        <span style={{ fontSize: 11, color: "var(--text-dim)" }}>Weight</span>
        <input
          type="range"
          min={0}
          max={10}
          step={1}
          value={pref.weight}
          onChange={(e) => onChange({ weight: Number(e.target.value) })}
        />
        <span className="num">{pref.weight}</span>
      </div>
      <div className="controls">
        <label>
          Direction
          <select
            value={direction}
            onChange={(e) => onChange({ direction: e.target.value as Preference["direction"] })}
          >
            <option value="lower_better">lower better</option>
            <option value="higher_better">higher better</option>
            <option value="target">target</option>
          </select>
        </label>
        <label>
          {direction === "target" ? "Target" : "Ideal"}
          <input
            type="number"
            value={pref.ideal ?? ""}
            onChange={(e) =>
              onChange({ ideal: e.target.value === "" ? null : Number(e.target.value) })
            }
          />
        </label>
        <label>
          {direction === "target" ? "Tolerance" : "Cap (0 credit)"}
          <input
            type="number"
            value={direction === "target" ? pref.tolerance ?? "" : pref.cap ?? ""}
            onChange={(e) =>
              direction === "target"
                ? onChange({
                    tolerance: e.target.value === "" ? null : Number(e.target.value),
                  })
                : onChange({ cap: e.target.value === "" ? null : Number(e.target.value) })
            }
          />
        </label>
      </div>
    </div>
  );
}
