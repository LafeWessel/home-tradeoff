import { useApp } from "../store";

export function Tray() {
  const selected = useApp((s) => s.selected);
  const remove = useApp((s) => s.removeLocation);
  const clear = useApp((s) => s.clearLocations);

  return (
    <div className="tray-strip">
      <span className="tray-label">
        {selected.length === 0 ? "No locations selected" : `Comparing (${selected.length})`}
      </span>
      {selected.length > 0 && (
        <>
          <div className="tray-chips">
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
          <button className="tray-clear" onClick={clear}>
            Clear
          </button>
        </>
      )}
    </div>
  );
}
