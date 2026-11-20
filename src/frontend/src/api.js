// Client for the ClearPath REST API (FastAPI).
async function handle(response) {
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof body.detail === "string" ? body.detail : "Something went wrong. Please try again.";
    throw new Error(detail);
  }
  return body;
}

export const api = {
  classify: (text) =>
    fetch("/api/classify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    }).then(handle),

  submitReport: ({ text, lat, lon, photo, consent }) => {
    const data = new FormData();
    data.append("text", text);
    data.append("consent", consent ? "true" : "false");
    if (lat != null && lon != null) {
      data.append("lat", String(lat));
      data.append("lon", String(lon));
    }
    if (photo) data.append("photo", photo);
    return fetch("/api/reports", { method: "POST", body: data }).then(handle);
  },

  report: (protocol) => fetch(`/api/reports/${encodeURIComponent(protocol)}`).then(handle),
  reports: () => fetch("/api/reports").then(handle),
  eraseData: (protocol) =>
    fetch(`/api/reports/${encodeURIComponent(protocol)}/data`, { method: "DELETE" }).then(handle),
  indicators: () => fetch("/api/indicators").then(handle),
  devices: () => fetch("/api/iot/devices").then(handle),
};

// FIXED category order = fixed color order (the color follows the category, never its position).
export const CATEGORIES = [
  { id: "damaged_sidewalk", label: "Damaged sidewalk", color: "var(--series-1)" },
  { id: "sidewalk_obstruction", label: "Sidewalk obstruction", color: "var(--series-2)" },
  { id: "ramp_access", label: "Ramp / building access", color: "var(--series-3)" },
  { id: "tactile_paving", label: "Tactile paving", color: "var(--series-4)" },
  { id: "crossing_signal", label: "Crossing and pedestrian signal", color: "var(--series-5)" },
  { id: "accessible_transit", label: "Accessible public transit", color: "var(--series-6)" },
];

export const PRIORITIES = {
  critical: { label: "Critical", icon: "‼" },
  high: { label: "High", icon: "!" },
  medium: { label: "Medium", icon: "•" },
  low: { label: "Low", icon: "○" },
};

export const STATUS = {
  received: "Received",
  human_triage: "Under review by a public servant",
  forwarded: "Forwarded to the agency",
  in_progress: "In progress",
  resolved: "Resolved",
  escalated: "Escalated to the Ombudsman (deadline missed)",
};

export const formatDate = (iso) => (iso ? new Date(iso).toLocaleDateString("en-US") : "-");
export const formatDateTime = (iso) =>
  iso ? new Date(iso).toLocaleString("en-US", { dateStyle: "short", timeStyle: "short" }) : "-";
