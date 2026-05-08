import { useEffect, useRef } from "react";
import maplibregl, { Map as MlMap, Marker, Popup } from "maplibre-gl";
import { useApp } from "../store";
import { api } from "../api/client";
import type { Location } from "../types";

// Public OSM raster tiles via OpenStreetMap. Basemap data is intentionally
// not cached locally per project requirements.
const STYLE: maplibregl.StyleSpecification = {
  version: 8,
  sources: {
    osm: {
      type: "raster",
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      attribution: "© OpenStreetMap contributors",
      maxzoom: 19,
    },
  },
  layers: [{ id: "osm-tiles", type: "raster", source: "osm" }],
};

interface MarkerEntry {
  marker: Marker;
  geoid: string;
}

export function MapPane() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MlMap | null>(null);
  const stateMarkersRef = useRef<MarkerEntry[]>([]);
  const selectedMarkersRef = useRef<Map<string, Marker>>(new Map());
  const selected = useApp((s) => s.selected);
  const addLocation = useApp((s) => s.addLocation);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: STYLE,
      center: [-96, 38],
      zoom: 3.5,
      attributionControl: { compact: true },
    });
    mapRef.current = map;

    map.on("load", async () => {
      // Plant a marker per state. Empty-q search returns all rows of that level.
      const stateList = await api
        .searchLocations("", { level: "state", limit: 100 })
        .catch(() => [] as Location[]);

      for (const s of stateList) {
        if (s.lat == null || s.lon == null) continue;
        const el = document.createElement("div");
        el.className = "state-marker";
        el.style.cssText =
          "width:18px;height:18px;border-radius:50%;background:#58a6ff;border:2px solid #0e1116;cursor:pointer;box-shadow:0 0 4px #0e1116;";
        el.title = s.name;
        const marker = new maplibregl.Marker({ element: el }).setLngLat([s.lon, s.lat]).addTo(map);
        const popup = new Popup({ offset: 14, closeButton: false }).setText(s.display_name);
        el.addEventListener("mouseenter", () => {
          marker.setPopup(popup);
          popup.addTo(map);
        });
        el.addEventListener("mouseleave", () => popup.remove());
        el.addEventListener("click", () => addLocation(s));
        stateMarkersRef.current.push({ marker, geoid: s.geoid });
      }
    });
  }, [addLocation]);

  // Sync selected markers (for non-state selections)
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const wantedGeoids = new Set(selected.map((l) => l.geoid));

    // Remove markers for locations no longer selected
    for (const [geoid, m] of selectedMarkersRef.current.entries()) {
      if (!wantedGeoids.has(geoid)) {
        m.remove();
        selectedMarkersRef.current.delete(geoid);
      }
    }

    // Highlight selected state markers (recolor) and add markers for non-state selections
    for (const entry of stateMarkersRef.current) {
      const el = entry.marker.getElement() as HTMLElement;
      el.style.background = wantedGeoids.has(entry.geoid) ? "#3fb950" : "#58a6ff";
    }

    for (const loc of selected) {
      if (loc.level === "state") continue; // already represented
      if (selectedMarkersRef.current.has(loc.geoid)) continue;
      if (loc.lat == null || loc.lon == null) continue;
      const el = document.createElement("div");
      el.style.cssText = `
        width:14px;height:14px;border-radius:50%;
        background:${loc.level === "place" ? "#3fb950" : "#d29922"};
        border:2px solid #0e1116;cursor:pointer;box-shadow:0 0 4px #0e1116;
      `;
      el.title = loc.display_name;
      const m = new maplibregl.Marker({ element: el }).setLngLat([loc.lon, loc.lat]).addTo(map);
      selectedMarkersRef.current.set(loc.geoid, m);
    }

    // Fly-to fit when selection changes
    if (selected.length > 0) {
      const pts = selected.filter((l) => l.lat != null && l.lon != null);
      if (pts.length === 1) {
        map.flyTo({ center: [pts[0].lon!, pts[0].lat!], zoom: pts[0].level === "state" ? 5 : 8 });
      } else if (pts.length > 1) {
        const lons = pts.map((p) => p.lon!);
        const lats = pts.map((p) => p.lat!);
        map.fitBounds(
          [
            [Math.min(...lons) - 1, Math.min(...lats) - 1],
            [Math.max(...lons) + 1, Math.max(...lats) + 1],
          ],
          { padding: 60, duration: 800 }
        );
      }
    }
  }, [selected]);

  return (
    <div className="map-pane">
      <div ref={containerRef} id="map" />
      <div className="map-overlay">
        Click a state to add it. Search for counties / cities in the sidebar.
        Mix levels freely — comparing a city vs. a state works.
      </div>
    </div>
  );
}
