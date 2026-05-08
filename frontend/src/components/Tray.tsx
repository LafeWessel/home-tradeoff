import { useApp } from "../store";

export function Tray() {
  const selected = useApp((s) => s.selected);
  const remove = useApp((s) => s.removeLocation);
  const clear = useApp((s) => s.clearLocations);

  return (
    <div className="tray">
      <h3>
        Comparing ({selected.length}){" "}
        {selected.length > 0 && (
          <button
            onClick={clear}
            style={{
              float: "right",
              background: "transparent",
              border: "none",
              color: "var(--text-dim)",
              cursor: "pointer",
              fontSize: 11,
              textTransform: "uppercase",
              letterSpacing: 0.6,
            }}
          >
            Clear
          </button>
        )}
      </h3>
      {selected.length === 0 ? (
        <div className="empty">No locations selected. Click a state on the map or search above.</div>
      ) : (
        <div className="chips">
          {selected.map((s) => (
            <span key={s.geoid} className="chip">
              <span className={`level-pill ${s.level}`}>{s.level[0].toUpperCase()}</span>
              {s.display_name}
              <button onClick={() => remove(s.geoid)} title="Remove">
                ×
              </button>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
