import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, STATUS, formatDateTime } from "../api.js";
import { Badge, useColors } from "./components.jsx";

const pct = (v) => (v == null ? "-" : `${Math.round(v * 100)}%`);

function Kpi({ title, value, detail }) {
  return (
    <div className="kpi">
      <span className="kpi-title">{title}</span>
      <span className="kpi-value">{value}</span>
      {detail && <span className="kpi-detail">{detail}</span>}
    </div>
  );
}

function ChartTooltip({ active, payload, label, unit }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="chart-tooltip">
      <strong>{label}</strong>
      <span>{payload[0].value} {unit}</span>
    </div>
  );
}

export default function Dashboard() {
  const [d, setD] = useState(null);
  const [devices, setDevices] = useState([]);
  const [error, setError] = useState("");
  const c = useColors(["--series-1", "--grid", "--axis", "--ink-muted", "--surface"]);

  const load = () => {
    api.indicators().then(setD).catch((e) => setError(e.message));
    api.devices().then(setDevices).catch(() => {});
  };
  useEffect(() => {
    load();
    const t = setInterval(load, 15000); // sensors refresh on their own
    return () => clearInterval(t);
  }, []);

  if (error) return <section className="card"><p className="error" role="alert">{error}</p></section>;
  if (!d) return <section className="card"><p>Loading indicators...</p></section>;

  const categories = Object.entries(d.by_category).map(([name, n]) => ({ name, n }));
  const series = d.last_30_days.map((s) => ({ day: s.day.slice(5, 7) + "/" + s.day.slice(8, 10), reports: s.reports }));
  const maxPriority = Math.max(1, ...Object.values(d.by_priority));
  const axis = { stroke: c["--axis"], tick: { fill: c["--ink-muted"], fontSize: 12 } };

  return (
    <section className="card wide">
      <h1>Impact dashboard</h1>
      <p className="demo-banner" role="note">
        <strong>Demo data.</strong> The reports went through the real system (NLP, vision, automation), but the dates
        and the agencies' responses were simulated by <code>scripts/seed_demo.py</code>. The numbers illustrate the
        indicators and do <em>not</em> measure real impact.
      </p>

      <div className="kpis">
        <Kpi title="Reports received" value={d.total_reports} detail={`${d.open} open · ${d.iot_reports} from sensors`} />
        <Kpi title="Forwarded with no human intervention" value={pct(d.auto_forwarded / Math.max(1, d.total_reports))}
             detail={`${d.human_triage} awaiting human triage`} />
        <Kpi title="Resolved within the deadline" value={pct(d.on_time_resolution_rate)} detail={`${d.resolved} resolved`} />
        <Kpi title="Average time to resolve" value={d.avg_days_to_resolve == null ? "-" : `${d.avg_days_to_resolve} days`} />
        <Kpi title="Escalated to the Ombudsman" value={d.escalated} detail="deadline missed, automatic follow-up" />
        <Kpi title="Reports with personal data removed" value={d.reports_with_personal_data_removed} detail="CPF, phone, e-mail, name, plate" />
      </div>

      <div className="charts">
        <figure className="chart">
          <figcaption>Reports per day (last 30 days)</figcaption>
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={series} margin={{ top: 8, right: 12, left: -18, bottom: 0 }}>
              <CartesianGrid stroke={c["--grid"]} vertical={false} />
              <XAxis dataKey="day" {...axis} interval={4} />
              <YAxis allowDecimals={false} {...axis} />
              <Tooltip content={<ChartTooltip unit="reports" />} cursor={{ stroke: c["--ink-muted"], strokeDasharray: "3 3" }} />
              <Line isAnimationActive={false} type="monotone" dataKey="reports" stroke={c["--series-1"]} strokeWidth={2} dot={false}
                    activeDot={{ r: 5, stroke: c["--surface"], strokeWidth: 2 }} />
            </LineChart>
          </ResponsiveContainer>
        </figure>

        <figure className="chart">
          <figcaption>Reports by category</figcaption>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={categories} layout="vertical" margin={{ top: 4, right: 24, left: 8, bottom: 0 }}>
              <CartesianGrid stroke={c["--grid"]} horizontal={false} />
              <XAxis type="number" allowDecimals={false} {...axis} />
              <YAxis type="category" dataKey="name" width={160} {...axis} />
              <Tooltip content={<ChartTooltip unit="reports" />} cursor={{ fill: c["--grid"], opacity: 0.5 }} />
              <Bar isAnimationActive={false} dataKey="n" fill={c["--series-1"]} radius={[0, 4, 4, 0]} barSize={16} label={{ position: "right", fill: c["--ink-muted"], fontSize: 12 }} />
            </BarChart>
          </ResponsiveContainer>
        </figure>
      </div>

      <div className="charts">
        <div>
          <h2>Priority</h2>
          <ul className="priority-bars">
            {Object.entries(d.by_priority).map(([p, n]) => (
              <li key={p}>
                <Badge priority={p} />
                <span className="track"><span className={`fill bg-${p}`} style={{ width: `${(n / maxPriority) * 100}%` }} /></span>
                <span className="value">{n}</span>
              </li>
            ))}
          </ul>
          <h2>Status</h2>
          <table>
            <tbody>
              {Object.entries(d.by_status).map(([s, n]) => <tr key={s}><td>{STATUS[s] || s}</td><td className="num">{n}</td></tr>)}
            </tbody>
          </table>
        </div>
        <div>
          <h2>Most reported barriers</h2>
          {d.most_reported_barriers.length === 0 ? <p className="hint">No barrier with more than one report.</p> : (
            <table>
              <thead><tr><th>Occurrence</th><th>Category</th><th className="num">Reports</th><th>Priority</th></tr></thead>
              <tbody>
                {d.most_reported_barriers.map((b) => (
                  <tr key={b.protocol}><td>{b.protocol}</td><td>{b.category}{b.address ? ` · ${b.address}` : ""}</td><td className="num">{b.reports}</td><td><Badge priority={b.priority} /></td></tr>
                ))}
              </tbody>
            </table>
          )}

          <h2>Ramp sensors (ESP32)</h2>
          <ul className="sensors">
            {devices.map((s) => (
              <li key={s.id} className={s.last_state === "blocked" ? "sensor blocked" : "sensor"}>
                <strong>{s.location || s.id}</strong>
                <span>{s.last_state === "blocked" ? "⛔ Ramp blocked" : "✅ Ramp clear"} · {s.distance_cm ?? "-"} cm</span>
                <span className="hint">Last seen: {formatDateTime(s.last_seen)}</span>
              </li>
            ))}
            {devices.length === 0 && <li className="hint">No sensor connected.</li>}
          </ul>
        </div>
      </div>

      <details>
        <summary>Show chart data as tables</summary>
        <table>
          <thead><tr><th>Category</th><th className="num">Reports</th></tr></thead>
          <tbody>{categories.map((x) => <tr key={x.name}><td>{x.name}</td><td className="num">{x.n}</td></tr>)}</tbody>
        </table>
        <table>
          <thead><tr><th>Day</th><th className="num">Reports</th></tr></thead>
          <tbody>{series.map((x) => <tr key={x.day}><td>{x.day}</td><td className="num">{x.reports}</td></tr>)}</tbody>
        </table>
      </details>
    </section>
  );
}
