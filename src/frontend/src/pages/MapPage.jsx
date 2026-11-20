import { useEffect, useMemo, useState } from "react";
import { MapContainer, TileLayer, CircleMarker, Popup } from "react-leaflet";
import { api, CATEGORIES, STATUS, formatDate } from "../api.js";
import { Badge, useColors } from "./components.jsx";

export default function MapPage({ goTo }) {
  const [reports, setReports] = useState([]);
  const [filter, setFilter] = useState("all");
  const [openOnly, setOpenOnly] = useState(true);
  const [error, setError] = useState("");
  const colors = useColors(CATEGORIES.map((_, i) => `--series-${i + 1}`).concat("--surface"));

  useEffect(() => {
    api.reports().then(setReports).catch((e) => setError(e.message));
  }, []);

  const visible = useMemo(
    () => reports.filter((r) => r.lat != null && (filter === "all" || r.category === filter) && (!openOnly || r.status !== "resolved")),
    [reports, filter, openOnly]
  );
  const colorOf = (cat) => colors[`--series-${CATEGORIES.findIndex((c) => c.id === cat) + 1}`];

  return (
    <section className="card wide">
      <h1>Barrier map</h1>
      <div className="filters" role="group" aria-label="Map filters">
        <label htmlFor="filter-cat">Category</label>
        <select id="filter-cat" value={filter} onChange={(e) => setFilter(e.target.value)}>
          <option value="all">All</option>
          {CATEGORIES.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
        </select>
        <label className="check">
          <input type="checkbox" checked={openOnly} onChange={(e) => setOpenOnly(e.target.checked)} /> Unresolved only
        </label>
        <span className="hint">{visible.length} on the map</span>
      </div>
      {error && <p className="error" role="alert">{error}</p>}

      <ul className="legend" aria-label="Color legend">
        {CATEGORIES.map((c) => (
          <li key={c.id}><span className="swatch" style={{ background: c.color }} aria-hidden="true" />{c.label}</li>
        ))}
      </ul>

      <div className="map-large">
        <MapContainer center={[-23.56, -46.65]} zoom={12}>
          <TileLayer attribution='&copy; OpenStreetMap' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
          {visible.map((r) => (
            <CircleMarker key={r.protocol} center={[r.lat, r.lon]} radius={r.priority === "critical" ? 10 : 7}
                          pathOptions={{ color: colors["--surface"], weight: 2, fillColor: colorOf(r.category), fillOpacity: 0.95 }}>
              <Popup>
                <strong>{r.category_label}</strong> <Badge priority={r.priority} /><br />
                {STATUS[r.status]} · deadline {formatDate(r.deadline)}<br />
                {r.address && <>{r.address}<br /></>}
                <button type="button" className="link" onClick={() => goTo("track", r.protocol)}>{r.protocol}</button>
              </Popup>
            </CircleMarker>
          ))}
        </MapContainer>
      </div>

      <details>
        <summary>Show as a table ({visible.length})</summary>
        <div className="table-scroll">
          <table>
            <thead><tr><th>Protocol</th><th>Category</th><th>Priority</th><th>Status</th><th>Address</th></tr></thead>
            <tbody>
              {visible.map((r) => (
                <tr key={r.protocol}>
                  <td><button type="button" className="link" onClick={() => goTo("track", r.protocol)}>{r.protocol}</button></td>
                  <td>{r.category_label}</td><td><Badge priority={r.priority} /></td><td>{STATUS[r.status]}</td><td>{r.address || "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </section>
  );
}
