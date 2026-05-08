import { create } from "zustand";
import type { Location, Preset } from "./types";

export type Tab = "compare" | "score" | "prefs";

interface AppState {
  selected: Location[];
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

export const useApp = create<AppState>((set, get) => ({
  selected: [],
  activeTab: "compare",
  presets: [],
  activePresetId: null,

  addLocation: (l) => {
    const cur = get().selected;
    if (cur.find((x) => x.geoid === l.geoid)) return;
    if (cur.length >= 12) return; // hard cap
    set({ selected: [...cur, l] });
  },
  removeLocation: (geoid) =>
    set({ selected: get().selected.filter((x) => x.geoid !== geoid) }),
  clearLocations: () => set({ selected: [] }),
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
}));
