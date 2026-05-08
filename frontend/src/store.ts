import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { Location, Preset } from "./types";

export type Tab = "compare" | "score" | "prefs";

interface AppState {
  selected: Location[];
  deselected: Location[];
  activeTab: Tab;
  presets: Preset[];
  activePresetId: number | null;

  addLocation: (l: Location) => void;
  removeLocation: (geoid: string) => void;
  clearLocations: () => void;
  setTab: (t: Tab) => void;
  setPresets: (p: Preset[]) => void;
  setActivePresetId: (id: number | null) => void;
}

export const useApp = create<AppState>()(
  persist(
    (set, get) => ({
      selected: [],
      deselected: [],
      activeTab: "compare",
      presets: [],
      activePresetId: null,

      addLocation: (l) => {
        const { selected, deselected } = get();
        if (selected.find((x) => x.geoid === l.geoid)) return;
        if (selected.length >= 12) return;
        set({ selected: [...selected, l], deselected: deselected.filter((x) => x.geoid !== l.geoid) });
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
      setTab: (t) => set({ activeTab: t }),
      setPresets: (p) =>
        set((s) => ({
          presets: p,
          activePresetId:
            s.activePresetId && p.some((x) => x.id === s.activePresetId)
              ? s.activePresetId
              : p[0]?.id ?? null,
        })),
      setActivePresetId: (id) => set({ activePresetId: id }),
    }),
    {
      name: "home-tradeoff",
      partialize: (s) => ({
        selected: s.selected,
        deselected: s.deselected,
        activeTab: s.activeTab,
        activePresetId: s.activePresetId,
      }),
    }
  )
);
