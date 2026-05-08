import { useEffect, useRef } from "react";
import maplibregl, { Map as MlMap, Marker, Popup } from "maplibre-gl";
import { useApp } from "../store";
import { api } from "../api/client";
import type { Location } from "../types";

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

interface StateMarkerEntry {
  marker: Marker;
  geoid: string;
}

interface NonStateMarkerEntry {
  marker: Marker;
  el: HTMLElement;
}

const MAP_VIEW_KEY = "home-tradeoff-map-view";

function savedMapView(): { center: [number, number]; zoom: number } {
  try {
    const raw = localStorage.getItem(MAP_VIEW_KEY);
    if (raw) return JSON.parse(raw);
  } catch { /* ignore */ }
  return { center: [-96, 38], zoom: 3.5 };
}

function nonStateColor(loc: Location) {
  return loc.level === "place" ? "#3fb950" : "#d29922";
}

export function MapPane() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MlMap | null>(null);
  const stateMarkersRef = useRef<StateMarkerEntry[]>([]);
  const nonStateMarkersRef = useRef<Map<string, NonStateMarkerEntry>>(new Map());
  const selected = useApp((s) => s.selected);
  const deselected = useApp((s) => s.deselected);
  const addLocation = useApp((s) => s.addLocation);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const { center, zoom } = savedMapView();
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: STYLE,
      center,
      zoom,
      attributionControl: { compact: true },
    });
    mapRef.current = map;

    map.on("moveend", () => {
      const c = map.getCenter();
      localStorage.setItem(
        MAP_VIEW_KEY,
        JSON.stringify({ center: [c.lng, c.lat], zoom: map.getZoom() })
      );
    });

    map.on("load", async () => {
      const stateList = await api
        .searchLocations("", { level: "state", limit: 100 })
        .catch(() => [] as Location[]);

      for (const s of stateList) {
        if (s.lat == null || s.lon == null) continue;
        const el = document.createElement("div");
        el.className = "state-marker";
        el.style.cssText =
          "width:18px;height:18px;border-radius:50%;background:#58a6ff;border:2px solid #0e1116;cursor:pointer;box-shadow:0 0 4px #0e1116;transition:opacity 0.15s;";
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

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const selectedSet = new Set(selected.map((l) => l.geoid));
    const deselectedSet = new Set(deselected.map((l) => l.geoid));

    // Update state marker colors: green=selected, dimmed=deselected, blue=unvisited
    for (const entry of stateMarkersRef.current) {
      const el = entry.marker.getElement() as HTMLElement;
      if (selectedSet.has(entry.geoid)) {
        el.style.background = "#3fb950";
        el.style.opacity = "1";
      } else if (deselectedSet.has(entry.geoid)) {
        el.style.background = "#58a6ff";
        el.style.opacity = "0.35";
      } else {
        el.style.background = "#58a6ff";
        el.style.opacity = "1";
      }
    }

    // Remove non-state markers that are no longer in either list
    for (const [geoid, { marker }] of nonStateMarkersRef.current.entries()) {
      if (!selectedSet.has(geoid) && !deselectedSet.has(geoid)) {
        marker.remove();
        nonStateMarkersRef.current.delete(geoid);
      }
    }

    // Add or update markers for all non-state locations (selected + deselected)
    for (const loc of [...selected, ...deselected]) {
      if (loc.level === "state") continue;
      if (loc.lat == null || loc.lon == null) continue;
      const isSelected = selectedSet.has(loc.geoid);
      const color = isSelected ? nonStateColor(loc) : "#6e7681";
      const opacity = isSelected ? "1" : "0.45";

      const existing = nonStateMarkersRef.current.get(loc.geoid);
      if (existing) {
        existing.el.style.background = color;
        existing.el.style.opacity = opacity;
      } else {
        const el = document.createElement("div");
        el.style.cssText = `
          width:14px;height:14px;border-radius:50%;
          background:${color};border:2px solid #0e1116;
          cursor:pointer;box-shadow:0 0 4px #0e1116;
          opacity:${opacity};transition:opacity 0.15s;
        `;
        el.title = loc.display_name;
        const marker = new maplibregl.Marker({ element: el })
          .setLngLat([loc.lon, loc.lat])
          .addTo(map);
        nonStateMarkersRef.current.set(loc.geoid, { marker, el });
      }
    }

    // Fly to fit only the active selected locations
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
  }, [selected, deselected]);

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
