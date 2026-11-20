import { useEffect, useState } from "react";
import { api, STATUS, formatDate, formatDateTime } from "../api.js";
import { Badge } from "./components.jsx";

export default function Track({ initialProtocol }) {
  const [protocol, setProtocol] = useState(initialProtocol || "");
  const [report, setReport] = useState(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const search = async (p = protocol) => {
    setError("");
    setMessage("");
    setReport(null);
    try {
      setReport(await api.report(p.trim().toUpperCase()));
    } catch (e) {
      setError(e.message);
    }
  };

  useEffect(() => {
    if (initialProtocol) search(initialProtocol);
  }, [initialProtocol]);

  const erase = async () => {
    if (!confirm("Delete the text and photo of this report? The case stays open at the agency, but without this data.")) return;
    await api.eraseData(report.protocol);
    setMessage("Text and photo deleted (LGPD, art. 18). Only the category, approximate location and dates were kept.");
    search(report.protocol);
  };

  const overdue = report && report.status !== "resolved" && new Date(report.deadline) < new Date();

  return (
    <section className="card">
      <h1>Track a protocol</h1>
      <form className="search" onSubmit={(e) => { e.preventDefault(); search(); }}>
        <label htmlFor="protocol">Protocol number</label>
        <input id="protocol" value={protocol} placeholder="CP-2026-000001" onChange={(e) => setProtocol(e.target.value)} />
        <button type="submit" disabled={!protocol.trim()}>Search</button>
      </form>
      {error && <p className="error" role="alert">{error}</p>}
      {message && <p className="notice" role="status">{message}</p>}

      {report && (
        <div aria-live="polite">
          <h2>{report.category_label} <Badge priority={report.priority} /></h2>
          <p className="current-state">Status: <strong>{STATUS[report.status]}</strong>{overdue && <span className="badge badge-critical">Deadline missed</span>}</p>
          <dl className="summary">
            <dt>Responsible agency</dt><dd>{report.agency}</dd>
            <dt>Opened</dt><dd>{formatDateTime(report.created_at)}</dd>
            <dt>Deadline</dt><dd>{formatDate(report.deadline)}</dd>
            {report.address && <><dt>Address</dt><dd>{report.address}</dd></>}
            <dt>Report (anonymized)</dt><dd>{report.anonymized_text}</dd>
            {report.source === "iot" && <><dt>Source</dt><dd>Automatic ramp sensor ({report.device})</dd></>}
          </dl>

          <h3>Timeline</h3>
          <ol className="timeline">
            {report.history.map((h, i) => (
              <li key={i}>
                <time dateTime={h.at}>{formatDateTime(h.at)}</time>
                <strong>{STATUS[h.status] || h.status}</strong>
                {h.note && <span>{h.note}</span>}
              </li>
            ))}
          </ol>

          {report.photo_analysis && (
            <figure>
              <img src={`/media/${report.photo_analysis}`} alt={`Photo analysis: ${report.damage_level} damage`} />
              <figcaption>Photo analysis: damage index {report.damage_index}/100 ({report.damage_level}).</figcaption>
            </figure>
          )}

          {!report.anonymized_text.startsWith("[removed") && (
            <button type="button" className="danger" onClick={erase}>Delete my text and photo</button>
          )}
        </div>
      )}
    </section>
  );
}
