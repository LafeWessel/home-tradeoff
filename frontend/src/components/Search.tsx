import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import { useApp } from "../store";
import type { Location } from "../types";

export function Search() {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<Location[]>([]);
  const [open, setOpen] = useState(false);
  const debounceRef = useRef<number | null>(null);
  const addLocation = useApp((s) => s.addLocation);

  useEffect(() => {
    if (debounceRef.current) window.clearTimeout(debounceRef.current);
    if (q.trim().length < 1) {
      setResults([]);
      return;
    }
    debounceRef.current = window.setTimeout(async () => {
      try {
        const r = await api.searchLocations(q.trim(), { limit: 15 });
        setResults(r);
      } catch (e) {
        console.error(e);
      }
    }, 150);
    return () => {
      if (debounceRef.current) window.clearTimeout(debounceRef.current);
    };
  }, [q]);

  const pick = (l: Location) => {
    addLocation(l);
    setQ("");
    setResults([]);
    setOpen(false);
  };

  return (
    <div className="search-box">
      <input
        type="text"
        placeholder="Search states, counties, cities…"
        value={q}
        onChange={(e) => {
          setQ(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
      />
      {open && results.length > 0 && (
        <div className="search-results">
          {results.map((r) => (
            <div key={r.geoid} className="row" onMouseDown={() => pick(r)}>
              <span className={`level-pill ${r.level}`}>{r.level}</span>
              <span>{r.display_name}</span>
              {r.population != null && (
                <span style={{ marginLeft: "auto", color: "var(--text-dim)", fontSize: 11 }}>
                  {r.population.toLocaleString()}
                </span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
