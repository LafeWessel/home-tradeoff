import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { defaultPreferenceFor } from "../defaults";
import { categoryLabel, sortedCategories } from "../format";
import { useApp } from "../store";
import type { MetricDef, Preference } from "../types";

interface Props {
  metrics: MetricDef[];
}

export function Preferences({ metrics }: Props) {
  const presets = useApp((s) => s.presets);
  const setPresets = useApp((s) => s.setPresets);
  const activePresetId = useApp((s) => s.activePresetId);
  const setActivePresetId = useApp((s) => s.setActivePresetId);
  const workingPreferences = useApp((s) => s.workingPreferences);
  const updateWorkingPreference = useApp((s) => s.updateWorkingPreference);

  const [dirty, setDirty] = useState(false);
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [newPresetName, setNewPresetName] = useState("");
  const [renaming, setRenaming] = useState(false);
  const [renameName, setRenameName] = useState("");

  const active = useMemo(
    () => presets.find((p) => p.id === activePresetId) ?? null,
    [presets, activePresetId]
  );

  useEffect(() => {
    setDirty(false);
    setSavedAt(null);
    setRenaming(false);
  }, [activePresetId]);

  const updateRow = (metric_key: string, patch: Partial<Preference>) => {
    updateWorkingPreference(metric_key, patch);
    setDirty(true);
  };

  const save = async () => {
    if (!active) return;
    setBusy(true);
    try {
      const updated = await api.setPreferences(active.id, workingPreferences);
      // Use functional updater to avoid stale closure over presets
      setPresets(useApp.getState().presets.map((p) => (p.id === updated.id ? updated : p)));
      setDirty(false);
      setSavedAt(Date.now());
    } catch (e) {
      alert(`Save failed: ${e}`);
    } finally {
      setBusy(false);
    }
  };

  const renameActive = async () => {
    if (!active) return;
    const name = renameName.trim();
    if (!name || name === active.name) { setRenaming(false); return; }
    setBusy(true);
    try {
      const updated = await api.updatePreset(active.id, { name });
      setPresets(useApp.getState().presets.map((p) => (p.id === updated.id ? updated : p)));
      setRenaming(false);
    } catch (e) {
      alert(`Rename failed: ${e}`);
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
              {busy ? "Saving…" : dirty ? "Save changes" : savedAt ? "Saved" : "No changes"}
            </button>
            {renaming ? (
              <>
                <input
                  className="rename-input"
                  type="text"
                  value={renameName}
                  onChange={(e) => setRenameName(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") renameActive();
                    if (e.key === "Escape") setRenaming(false);
                  }}
                  autoFocus
                />
                <button onClick={renameActive} disabled={busy || !renameName.trim()}>
                  Confirm
                </button>
                <button onClick={() => setRenaming(false)} disabled={busy}>
                  Cancel
                </button>
              </>
            ) : (
              <button
                onClick={() => { setRenameName(active.name); setRenaming(true); }}
                disabled={busy}
              >
                Rename
              </button>
            )}
            <button className="danger" onClick={deleteActive} disabled={busy}>
              Delete
            </button>
            <span className={`save-status ${dirty ? "dirty" : savedAt ? "saved" : ""}`}>
              {dirty
                ? "Unsaved changes"
                : savedAt
                ? `Saved ${new Date(savedAt).toLocaleTimeString()}`
                : ""}
            </span>
          </div>

          {workingPreferences.length === 0 ? (
            <div style={{ padding: "16px 0" }}>
              <span className="spinner" />
            </div>
          ) : (
            cats.map((cat) => (
              <div className="cat-section" key={cat}>
                <h4>{categoryLabel(cat)}</h4>
                {metrics
                  .filter((m) => m.category === cat)
                  .map((m) => {
                    const row = workingPreferences.find((r) => r.metric_key === m.key);
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
            ))
          )}
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
