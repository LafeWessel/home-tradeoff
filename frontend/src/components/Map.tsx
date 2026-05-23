import { useEffect, useRef, useState } from "react";
import maplibregl, { Map as MlMap, Marker, Popup } from "maplibre-gl";
import { useApp } from "../store";
import { api } from "../api/client";
import type { Location } from "../types";

const STATE_GEO_URL = "/api/geo/states";
const COUNTY_GEO_URL = "/api/geo/counties";
const GEO_CACHE = "home-tradeoff-geo-v1";

async function fetchGeoJson(url: string): Promise<unknown> {
  if ("caches" in globalThis) {
    const cache = await caches.open(GEO_CACHE);
    const hit = await cache.match(url);
    if (hit) return hit.json();
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`${url} -> ${resp.status}`);
    await cache.put(url, resp.clone());
    return resp.json();
  }
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(`${url} -> ${resp.status}`);
  return resp.json();
}

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

interface PlaceMarkerEntry {
  marker: Marker;
  el: HTMLElement;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function bboxCenter(geometry: any): [number, number] {
  let minLng = Infinity, maxLng = -Infinity, minLat = Infinity, maxLat = -Infinity;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const rings: number[][][] = geometry.type === "Polygon" ? geometry.coordinates
    : geometry.type === "MultiPolygon" ? (geometry.coordinates as number[][][][]).flat(1)
    : [];
  for (const ring of rings) {
    for (const [lng, lat] of ring) {
      if (lng < minLng) minLng = lng;
      if (lng > maxLng) maxLng = lng;
      if (lat < minLat) minLat = lat;
      if (lat > maxLat) maxLat = lat;
    }
  }
  return [(minLng + maxLng) / 2, (minLat + maxLat) / 2];
}

const MAP_VIEW_KEY = "home-tradeoff-map-view";

function savedMapView(): { center: [number, number]; zoom: number } {
  try {
    const raw = localStorage.getItem(MAP_VIEW_KEY);
    if (raw) return JSON.parse(raw);
  } catch { /* ignore */ }
  return { center: [-96, 38], zoom: 3.5 };
}

export function MapPane() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MlMap | null>(null);
  const placeMarkersRef = useRef<Map<string, PlaceMarkerEntry>>(new Map());
  const locationCacheRef = useRef<Map<string, Location>>(new Map());
  const hoveredStateRef = useRef<string | null>(null);
  const hoveredCountyRef = useRef<string | null>(null);
  const hoverPopupRef = useRef<Popup | null>(null);
  const activeFeatureStatesRef = useRef<Set<string>>(new Set());
  const countiesLoadedRef = useRef(false);

  const [mapMode, setMapMode] = useState<"states" | "counties">("states");
  const [countiesLoading, setCountiesLoading] = useState(false);
  const mapModeRef = useRef<"states" | "counties">("states");
  useEffect(() => {
    mapModeRef.current = mapMode;
    const map = mapRef.current;
    if (!map) return;
    if (hoveredStateRef.current) {
      if (map.getSource("states-geo")) {
        map.setFeatureState({ source: "states-geo", id: hoveredStateRef.current }, { hover: false });
      }
      hoveredStateRef.current = null;
    }
    if (hoveredCountyRef.current) {
      if (map.getSource("counties-geo")) {
        map.setFeatureState({ source: "counties-geo", id: hoveredCountyRef.current }, { hover: false });
      }
      hoveredCountyRef.current = null;
    }
    map.getCanvas().style.cursor = "";
    hoverPopupRef.current?.remove();
    hoverPopupRef.current = null;
  }, [mapMode]);

  const selected = useApp((s) => s.selected);
  const deselected = useApp((s) => s.deselected);
  const addLocation = useApp((s) => s.addLocation);
  const addLocationRef = useRef(addLocation);
  useEffect(() => { addLocationRef.current = addLocation; }, [addLocation]);
  const removeLocation = useApp((s) => s.removeLocation);
  const removeLocationRef = useRef(removeLocation);
  useEffect(() => { removeLocationRef.current = removeLocation; }, [removeLocation]);
  const selectedRef = useRef(selected);
  const deselectedRef = useRef(deselected);
  useEffect(() => {
    selectedRef.current = selected;
    deselectedRef.current = deselected;
  }, [selected, deselected]);

  // Map init
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
      try {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const stateGeo: any = await fetchGeoJson(STATE_GEO_URL);
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        stateGeo.features.forEach((f: any) => { f.properties._geoid = f.properties.STATE; });

        map.addSource("states-geo", { type: "geojson", data: stateGeo, promoteId: "_geoid" });

        map.addLayer({
          id: "states-fill",
          type: "fill",
          source: "states-geo",
          paint: {
            "fill-color": [
              "case",
              ["boolean", ["feature-state", "selected"], false], "rgba(63,185,80,0.3)",
              ["boolean", ["feature-state", "deselected"], false], "rgba(88,166,255,0.12)",
              "rgba(0,0,0,0)",
            ],
          },
        });

        map.addLayer({
          id: "states-line",
          type: "line",
          source: "states-geo",
          paint: {
            "line-color": [
              "case",
              ["boolean", ["feature-state", "selected"], false], "#3fb950",
              ["boolean", ["feature-state", "hover"], false], "#58a6ff",
              "rgba(88,166,255,0.5)",
            ],
            "line-width": [
              "case",
              ["boolean", ["feature-state", "hover"], false], 2, 1,
            ],
          },
        });

        map.on("mousemove", "states-fill", (e) => {
          if (mapModeRef.current !== "states") return;
          const feat = e.features?.[0];
          if (!feat) return;
          const id = String(feat.id);
          if (hoveredStateRef.current === id) return;
          if (hoveredStateRef.current) {
            map.setFeatureState({ source: "states-geo", id: hoveredStateRef.current }, { hover: false });
          }
          hoveredStateRef.current = id;
          map.setFeatureState({ source: "states-geo", id }, { hover: true });
          map.getCanvas().style.cursor = "pointer";
          hoverPopupRef.current?.remove();
          const loc = locationCacheRef.current.get(id);
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          const name = loc?.display_name ?? (feat.properties as any)?.NAME ?? id;
          const center: [number, number] = (loc?.lon != null && loc?.lat != null)
            ? [loc.lon, loc.lat]
            : bboxCenter(feat.geometry);
          hoverPopupRef.current = new Popup({ closeButton: false, closeOnClick: false, offset: 8 })
            .setLngLat(center)
            .setText(name)
            .addTo(map);
        });

        map.on("mouseleave", "states-fill", () => {
          if (hoveredStateRef.current) {
            map.setFeatureState({ source: "states-geo", id: hoveredStateRef.current }, { hover: false });
            hoveredStateRef.current = null;
          }
          hoverPopupRef.current?.remove();
          hoverPopupRef.current = null;
          if (mapModeRef.current === "states") map.getCanvas().style.cursor = "";
        });

        map.on("click", "states-fill", async (e) => {
          if (mapModeRef.current !== "states") return;
          const feat = e.features?.[0];
          if (!feat) return;
          const geoid = String(feat.id);
          let loc = locationCacheRef.current.get(geoid);
          if (!loc) {
            loc = await api.getLocation(geoid).catch(() => undefined);
            if (loc) locationCacheRef.current.set(geoid, loc);
          }
          if (loc) addLocationRef.current(loc);
        });

        map.on("contextmenu", "states-fill", (e) => {
          e.originalEvent.preventDefault();
          const feat = e.features?.[0];
          if (!feat) return;
          removeLocationRef.current(String(feat.id));
        });

        // Apply any already-selected states (e.g. from persisted store)
        const sel = selectedRef.current;
        const desel = deselectedRef.current;
        const selSet = new Set(sel.map((l) => l.geoid));
        for (const loc of [...sel, ...desel]) {
          if (loc.level !== "state") continue;
          map.setFeatureState(
            { source: "states-geo", id: loc.geoid },
            { selected: selSet.has(loc.geoid), deselected: !selSet.has(loc.geoid) }
          );
          activeFeatureStatesRef.current.add(loc.geoid);
          locationCacheRef.current.set(loc.geoid, loc);
        }
      } catch (err) {
        console.error("Failed to load state boundaries:", err);
      }

      const stateList = await api
        .searchLocations("", { level: "state", limit: 100 })
        .catch(() => [] as Location[]);
      for (const s of stateList) locationCacheRef.current.set(s.geoid, s);
    });
  }, []);

  // Lazy-load counties on first switch to county mode
  useEffect(() => {
    const map = mapRef.current;
    if (!map || mapMode !== "counties" || countiesLoadedRef.current) return;

    const loadCounties = () => {
      countiesLoadedRef.current = true;
      setCountiesLoading(true);

      fetchGeoJson(COUNTY_GEO_URL)
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        .then((countyGeo: any) => {
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          countyGeo.features.forEach((f: any) => {
            f.properties._geoid = f.properties.STATE + f.properties.COUNTY;
          });

          map.addSource("counties-geo", { type: "geojson", data: countyGeo, promoteId: "_geoid" });

          map.addLayer({
            id: "counties-fill",
            type: "fill",
            source: "counties-geo",
            minzoom: 4,
            paint: {
              "fill-color": [
                "case",
                ["boolean", ["feature-state", "selected"], false], "rgba(210,153,34,0.35)",
                ["boolean", ["feature-state", "deselected"], false], "rgba(210,153,34,0.12)",
                "rgba(0,0,0,0)",
              ],
            },
          });

          map.addLayer({
            id: "counties-line",
            type: "line",
            source: "counties-geo",
            minzoom: 4,
            paint: {
              "line-color": [
                "case",
                ["boolean", ["feature-state", "selected"], false], "#d29922",
                ["boolean", ["feature-state", "hover"], false], "#d29922",
                "rgba(210,153,34,0.4)",
              ],
              "line-width": [
                "case",
                ["boolean", ["feature-state", "hover"], false], 2, 0.5,
              ],
            },
          });

          map.on("mousemove", "counties-fill", (e) => {
            if (mapModeRef.current !== "counties") return;
            const feat = e.features?.[0];
            if (!feat) return;
            const id = String(feat.id);
            if (hoveredCountyRef.current === id) return;
            if (hoveredCountyRef.current) {
              map.setFeatureState({ source: "counties-geo", id: hoveredCountyRef.current }, { hover: false });
            }
            hoveredCountyRef.current = id;
            map.setFeatureState({ source: "counties-geo", id }, { hover: true });
            map.getCanvas().style.cursor = "pointer";
            hoverPopupRef.current?.remove();
            const loc = locationCacheRef.current.get(id);
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            const props = feat.properties as any;
            const name = loc?.display_name ?? (props?.NAME && props?.LSAD ? `${props.NAME} ${props.LSAD}` : props?.NAME ?? id);
            const center: [number, number] = (loc?.lon != null && loc?.lat != null)
              ? [loc.lon, loc.lat]
              : bboxCenter(feat.geometry);
            hoverPopupRef.current = new Popup({ closeButton: false, closeOnClick: false, offset: 8 })
              .setLngLat(center)
              .setText(name)
              .addTo(map);
          });

          map.on("mouseleave", "counties-fill", () => {
            if (hoveredCountyRef.current) {
              map.setFeatureState({ source: "counties-geo", id: hoveredCountyRef.current }, { hover: false });
              hoveredCountyRef.current = null;
            }
            hoverPopupRef.current?.remove();
            hoverPopupRef.current = null;
            if (mapModeRef.current === "counties") map.getCanvas().style.cursor = "";
          });

          map.on("click", "counties-fill", async (e) => {
            if (mapModeRef.current !== "counties") return;
            const feat = e.features?.[0];
            if (!feat) return;
            const geoid = String(feat.id);
            let loc = locationCacheRef.current.get(geoid);
            if (!loc) {
              loc = await api.getLocation(geoid).catch(() => undefined);
              if (loc) locationCacheRef.current.set(geoid, loc);
            }
            if (loc) addLocationRef.current(loc);
          });

          map.on("contextmenu", "counties-fill", (e) => {
            e.originalEvent.preventDefault();
            const feat = e.features?.[0];
            if (!feat) return;
            removeLocationRef.current(String(feat.id));
          });

          // Apply already-selected/deselected counties
          const sel = selectedRef.current;
          const desel = deselectedRef.current;
          const selSet = new Set(sel.map((l) => l.geoid));
          for (const loc of [...sel, ...desel]) {
            if (loc.level !== "county") continue;
            map.setFeatureState(
              { source: "counties-geo", id: loc.geoid },
              { selected: selSet.has(loc.geoid), deselected: !selSet.has(loc.geoid) }
            );
            activeFeatureStatesRef.current.add(loc.geoid);
            locationCacheRef.current.set(loc.geoid, loc);
          }
        })
        .catch((err) => {
          console.error("Failed to load county boundaries:", err);
          countiesLoadedRef.current = false;
        })
        .finally(() => setCountiesLoading(false));
    };

    if (map.isStyleLoaded()) {
      loadCounties();
    } else {
      map.once("load", loadCounties);
    }
  }, [mapMode]);

  // Sync selected/deselected → feature states + place markers
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const selectedSet = new Set(selected.map((l) => l.geoid));
    const deselectedSet = new Set(deselected.map((l) => l.geoid));

    // Clear old feature states
    for (const geoid of activeFeatureStatesRef.current) {
      const loc = locationCacheRef.current.get(geoid);
      if (!loc) continue;
      const source = loc.level === "state" ? "states-geo" : "counties-geo";
      if (map.getSource(source)) {
        map.setFeatureState({ source, id: geoid }, { selected: false, deselected: false });
      }
    }
    activeFeatureStatesRef.current = new Set();

    // Set new feature states
    for (const loc of [...selected, ...deselected]) {
      if (loc.level === "place") continue;
      const source = loc.level === "state" ? "states-geo" : "counties-geo";
      if (!map.getSource(source)) continue;
      map.setFeatureState(
        { source, id: loc.geoid },
        { selected: selectedSet.has(loc.geoid), deselected: deselectedSet.has(loc.geoid) }
      );
      activeFeatureStatesRef.current.add(loc.geoid);
      locationCacheRef.current.set(loc.geoid, loc);
    }

    // Manage place dot markers
    for (const [geoid, { marker }] of placeMarkersRef.current.entries()) {
      if (!selectedSet.has(geoid) && !deselectedSet.has(geoid)) {
        marker.remove();
        placeMarkersRef.current.delete(geoid);
      }
    }

    for (const loc of [...selected, ...deselected]) {
      if (loc.level !== "place") continue;
      if (loc.lat == null || loc.lon == null) continue;
      const isSelected = selectedSet.has(loc.geoid);
      const color = isSelected ? "#3fb950" : "#6e7681";
      const opacity = isSelected ? "1" : "0.45";
      const existing = placeMarkersRef.current.get(loc.geoid);
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
        el.addEventListener("contextmenu", (ev) => {
          ev.preventDefault();
          removeLocationRef.current(loc.geoid);
        });
        const marker = new maplibregl.Marker({ element: el })
          .setLngLat([loc.lon, loc.lat])
          .addTo(map);
        placeMarkersRef.current.set(loc.geoid, { marker, el });
      }
    }

  }, [selected, deselected]);

  return (
    <div className="map-pane">
      <div ref={containerRef} id="map" />
      <div className="map-mode-toggle">
        <button
          className={mapMode === "states" ? "active" : ""}
          onClick={() => setMapMode("states")}
        >
          States
        </button>
        <button
          className={mapMode === "counties" ? "active" : ""}
          onClick={() => setMapMode("counties")}
          disabled={countiesLoading}
        >
          {countiesLoading ? "Loading…" : "Counties"}
        </button>
      </div>
      <div className="map-overlay">
        {mapMode === "states"
          ? "Click a state to add it."
          : "Click a county to add it — zoom in to see borders."}{" "}
        Search for cities in the sidebar.
      </div>
    </div>
  );
}
