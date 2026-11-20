import { useEffect, useState } from "react";
import Report from "./pages/Report.jsx";
import Track from "./pages/Track.jsx";
import MapPage from "./pages/MapPage.jsx";
import Dashboard from "./pages/Dashboard.jsx";

const PAGES = [
  { id: "report", label: "Report a barrier", component: Report },
  { id: "track", label: "Track a protocol", component: Track },
  { id: "map", label: "Map", component: MapPage },
  { id: "dashboard", label: "Impact dashboard", component: Dashboard },
];

function readPreference(key, fallback) {
  try {
    return localStorage.getItem(key) ?? fallback;
  } catch {
    return fallback;
  }
}

function savePreference(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* private browsing: continue without saving */
  }
}

export default function App() {
  const readHash = () => {
    const [id, extra = ""] = location.hash.slice(1).split("/");
    return PAGES.some((p) => p.id === id) ? { id, extra: decodeURIComponent(extra) } : { id: "report", extra: "" };
  };
  const [page, setPage] = useState(() => readHash().id);
  const [fontSize, setFontSize] = useState(() => Number(readPreference("cp-font", "100")));
  const [highContrast, setHighContrast] = useState(() => readPreference("cp-contrast", "no") === "yes");
  const [initialProtocol, setInitialProtocol] = useState(() => readHash().extra);

  useEffect(() => {
    const listen = () => {
      const h = readHash();
      setPage(h.id);
      if (h.extra) setInitialProtocol(h.extra);
    };
    window.addEventListener("hashchange", listen);
    return () => window.removeEventListener("hashchange", listen);
  }, []);

  useEffect(() => {
    document.documentElement.style.fontSize = `${fontSize}%`;
    savePreference("cp-font", String(fontSize));
  }, [fontSize]);

  useEffect(() => {
    document.documentElement.dataset.contrast = highContrast ? "high" : "normal";
    savePreference("cp-contrast", highContrast ? "yes" : "no");
  }, [highContrast]);

  const goTo = (id, protocol = "") => {
    setInitialProtocol(protocol);
    location.hash = protocol ? `${id}/${protocol}` : id;
    setPage(id);
    document.getElementById("content")?.focus();
  };

  const Current = PAGES.find((p) => p.id === page).component;

  return (
    <>
      <a className="skip" href="#content">Skip to content</a>
      <header className="top">
        <div className="brand">
          <span className="logo" aria-hidden="true">♿</span>
          <div>
            <strong>ClearPath</strong>
            <span className="subtitle">Accessibility barriers, reported and resolved</span>
          </div>
        </div>
        <div className="tools" role="group" aria-label="Accessibility settings">
          <button type="button" onClick={() => setFontSize((f) => Math.max(90, f - 10))} aria-label="Decrease text size">A−</button>
          <button type="button" onClick={() => setFontSize((f) => Math.min(150, f + 10))} aria-label="Increase text size">A+</button>
          <button type="button" aria-pressed={highContrast} onClick={() => setHighContrast((c) => !c)}>
            High contrast
          </button>
        </div>
      </header>

      <nav className="tabs" aria-label="Sections">
        {PAGES.map((p) => (
          <a key={p.id} href={`#${p.id}`} aria-current={page === p.id ? "page" : undefined}
             onClick={(e) => { e.preventDefault(); goTo(p.id); }}>
            {p.label}
          </a>
        ))}
      </nav>

      <main id="content" tabIndex={-1}>
        <Current goTo={goTo} initialProtocol={initialProtocol} />
      </main>

      <footer className="footer">
        Academic prototype, FIAP Global Solution 2026.2 (CitizenTech). Letters are simulated and do not reach real agencies.
        SDGs 10 and 11.
      </footer>
    </>
  );
}
