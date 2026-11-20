import React from "react";
import { createRoot } from "react-dom/client";
import "leaflet/dist/leaflet.css";
import "./styles.css";
import App from "./App.jsx";

// ?theme=light or ?theme=dark forces the theme (useful for screenshots); otherwise it follows the system.
const theme = new URLSearchParams(location.search).get("theme");
if (theme) document.documentElement.dataset.theme = theme === "dark" ? "dark" : "light";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
