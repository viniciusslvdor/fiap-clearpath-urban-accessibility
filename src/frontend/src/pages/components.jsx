import { useEffect, useState } from "react";
import { PRIORITIES } from "../api.js";

// Priority is never shown by color alone: icon + text + color.
export function Badge({ priority }) {
  const p = PRIORITIES[priority];
  if (!p) return null;
  return (
    <span className={`badge badge-${priority}`}>
      <span aria-hidden="true">{p.icon}</span> {p.label}
    </span>
  );
}

// Reads the real value of CSS variables (Recharts/Leaflet SVG needs the resolved color),
// and reads them again when the system theme or high contrast changes.
export function useColors(names) {
  const read = () => {
    const style = getComputedStyle(document.documentElement);
    return Object.fromEntries(names.map((n) => [n, style.getPropertyValue(n).trim()]));
  };
  const [colors, setColors] = useState(read);
  useEffect(() => {
    const update = () => setColors(read());
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    mq.addEventListener("change", update);
    const obs = new MutationObserver(update);
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["data-contrast", "data-theme"] });
    return () => { mq.removeEventListener("change", update); obs.disconnect(); };
  }, []);
  return colors;
}
