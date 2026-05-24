import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { Location, Preference, Preset } from "./types";

export type Panel = "compare" | "score" | "prefs";

interface AppState {
  selected: Location[];
  deselected: Location[];
  openPanels: Panel[];
  presets: Preset[];
  activePresetId: number | null;
  workingPreferences: Preference[];

  addLocation: (l: Location) => void;
  removeLocation: (geoid: string) => void;
  clearLocations: () => void;
  togglePanel: (p: Panel) => void;
  setPresets: (p: Preset[]) => void;
  setActivePresetId: (id: number | null) => void;
  setWorkingPreferences: (prefs: Preference[]) => void;
  updateWorkingPreference: (metric_key: string, patch: Partial<Preference>) => void;
}

export const useApp = create<AppState>()(
  persist(
    (set, get) => ({
      selected: [],
      deselected: [],
      openPanels: ["compare"],
      presets: [],
      activePresetId: null,
      workingPreferences: [],

      addLocation: (l) => {
        const { selected, deselected } = get();
        if (selected.find((x) => x.geoid === l.geoid)) return;
        if (selected.length >= 12) return;
        set({
          selected: [...selected, l],
          deselected: deselected.filter((x) => x.geoid !== l.geoid),
        });
      },
      removeLocation: (geoid) => {
        const { selected, deselected } = get();
        const loc = selected.find((x) => x.geoid === geoid);
        set({
          selected: selected.filter((x) => x.geoid !== geoid),
          deselected: loc ? [...deselected, loc] : deselected,
        });
      },
      clearLocations: () => set({ selected: [], deselected: [] }),
      togglePanel: (p) =>
        set((s) => ({
          openPanels: s.openPanels.includes(p)
            ? s.openPanels.filter((x) => x !== p)
            : [...s.openPanels, p],
        })),
      setPresets: (p) =>
        set((s) => ({
          presets: p,
          activePresetId:
            s.activePresetId && p.some((x) => x.id === s.activePresetId)
              ? s.activePresetId
              : p[0]?.id ?? null,
        })),
      setActivePresetId: (id) => set({ activePresetId: id }),
      setWorkingPreferences: (prefs) => set({ workingPreferences: prefs }),
      updateWorkingPreference: (metric_key, patch) =>
        set((s) => ({
          workingPreferences: s.workingPreferences.map((r) =>
            r.metric_key === metric_key ? { ...r, ...patch } : r
          ),
        })),
    }),
    {
      name: "home-tradeoff",
      partialize: (s) => ({
        selected: s.selected,
        deselected: s.deselected,
        openPanels: s.openPanels,
        activePresetId: s.activePresetId,
      }),
    }
  )
);
