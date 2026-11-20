import { useEffect, useRef, useState } from "react";
import { MapContainer, TileLayer, CircleMarker, useMapEvents } from "react-leaflet";
import { api, formatDate } from "../api.js";
import { Badge } from "./components.jsx";

const SAO_PAULO = [-23.5505, -46.6333];
const RECOGNITION = typeof window !== "undefined" && (window.SpeechRecognition || window.webkitSpeechRecognition);

function MapPicker({ position, onPick }) {
  useMapEvents({ click: (e) => onPick([e.latlng.lat, e.latlng.lng]) });
  return position ? <CircleMarker center={position} radius={10} pathOptions={{ color: "#ffffff", weight: 2, fillColor: "#2a78d6", fillOpacity: 1 }} /> : null;
}

export default function Report({ goTo }) {
  const [text, setText] = useState("");
  const [preview, setPreview] = useState(null);
  const [position, setPosition] = useState(null);
  const [photo, setPhoto] = useState(null);
  const [consent, setConsent] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  const [listening, setListening] = useState(false);
  const [locationNote, setLocationNote] = useState("");
  const recognizer = useRef(null);

  useEffect(() => {
    if (text.trim().length < 15) return setPreview(null);
    const t = setTimeout(() => api.classify(text).then(setPreview).catch(() => setPreview(null)), 600);
    return () => clearTimeout(t);
  }, [text]);

  const dictate = () => {
    if (!RECOGNITION) return;
    if (listening) return recognizer.current?.stop();
    const r = new RECOGNITION();
    r.lang = "en-US";
    r.interimResults = false;
    r.onresult = (e) => setText((t) => `${t} ${e.results[0][0].transcript}`.trim());
    r.onend = () => setListening(false);
    r.onerror = () => setListening(false);
    recognizer.current = r;
    setListening(true);
    r.start();
  };

  const useMyLocation = () => {
    if (!navigator.geolocation) return setLocationNote("Your browser does not share its location. Tap the map instead.");
    setLocationNote("Getting your location...");
    navigator.geolocation.getCurrentPosition(
      (p) => { setPosition([p.coords.latitude, p.coords.longitude]); setLocationNote("Location marked on the map."); },
      () => setLocationNote("Could not get your location. Tap the map to mark the spot."),
      { enableHighAccuracy: true, timeout: 10000 }
    );
  };

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setSending(true);
    try {
      const r = await api.submitReport({ text, lat: position?.[0], lon: position?.[1], photo, consent });
      setResult(r);
    } catch (err) {
      setError(err.message);
    } finally {
      setSending(false);
    }
  };

  if (result) {
    return (
      <section className="card" aria-live="polite">
        <h1>Report received. Thank you!</h1>
        <p className="protocol">Your protocol: <strong>{result.protocol}</strong></p>
        {result.duplicate && <p className="notice">You had already sent this exact text. Showing the existing protocol.</p>}
        <dl className="summary">
          <dt>Category</dt><dd>{result.category_label}</dd>
          <dt>Priority</dt><dd><Badge priority={result.priority} /></dd>
          <dt>Forwarded to</dt><dd>{result.status === "human_triage" ? "Review by a public servant (unclear text)" : result.agency}</dd>
          <dt>Response deadline</dt><dd>{formatDate(result.deadline)}</dd>
          {result.urgency_reasons && <><dt>Why this priority</dt><dd>{result.urgency_reasons}</dd></>}
          {result.group_root && <><dt>Same barrier</dt><dd>Other people have already reported this spot (occurrence {result.group_root}). Your report raised its priority.</dd></>}
        </dl>
        {result.personal_data_removed && Object.keys(result.personal_data_removed).length > 0 && (
          <p className="notice">To protect you, we removed from the text: {Object.keys(result.personal_data_removed).join(", ")}.</p>
        )}
        {result.photo_analysis && (
          <figure>
            <img src={`/media/${result.photo_analysis}`} alt={`Photo analysis: ${result.damage_level} damage, index ${result.damage_index} out of 100. Cracks in red, potholes in orange.`} />
            <figcaption>Automatic photo analysis: cracks in red, potholes in orange.</figcaption>
          </figure>
        )}
        <div className="actions">
          <button type="button" onClick={() => goTo("track", result.protocol)}>Track this protocol</button>
          <button type="button" className="secondary" onClick={() => { setResult(null); setText(""); setPhoto(null); setPosition(null); setConsent(false); }}>
            Report another barrier
          </button>
        </div>
      </section>
    );
  }

  return (
    <form className="card" onSubmit={submit} noValidate>
      <h1>Report an accessibility barrier</h1>
      <p className="help">Broken sidewalk, car blocking a ramp, missing tactile paving, silent pedestrian signal, broken elevator... Tell us in your own words. No sign-up needed.</p>

      <label htmlFor="text">What is happening? <span className="required">(required)</span></label>
      <div className="text-row">
        <textarea id="text" rows={5} value={text} onChange={(e) => setText(e.target.value)} maxLength={2000}
                  aria-describedby="text-hint" required />
        {RECOGNITION && (
          <button type="button" className="secondary" onClick={dictate} aria-pressed={listening}>
            {listening ? "Stop listening" : "🎤 Speak instead of typing"}
          </button>
        )}
      </div>
      <p id="text-hint" className="hint">Mention the place (street, number, landmark) and who is affected. Do not write your CPF or phone number: we don't need them.</p>

      {preview && (
        <div className="preview" aria-live="polite">
          <span>We understood: <strong>{preview.label}</strong> ({Math.round(preview.confidence * 100)}% confidence)</span>
          <span>Estimated priority: <Badge priority={preview.estimated_priority} /></span>
          {preview.address && <span>Address found: <strong>{preview.address}</strong></span>}
          {Object.keys(preview.personal_data_removed).length > 0 && (
            <span className="notice">We found personal data ({Object.keys(preview.personal_data_removed).join(", ")}). It will be removed before saving.</span>
          )}
        </div>
      )}

      <fieldset>
        <legend>Where is it?</legend>
        <button type="button" className="secondary" onClick={useMyLocation}>📍 Use my location</button>
        <span className="hint"> or tap the map.</span>
        <p className="hint" aria-live="polite">{locationNote}</p>
        <div className="map-small">
          <MapContainer center={position || SAO_PAULO} zoom={13} scrollWheelZoom={false}>
            <TileLayer attribution='&copy; OpenStreetMap' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
            <MapPicker position={position} onPick={setPosition} />
          </MapContainer>
        </div>
        {position && <p className="hint">Marked location: {position[0].toFixed(4)}, {position[1].toFixed(4)} (stored with ~11 m precision).</p>}
      </fieldset>

      <label htmlFor="photo">Photo (optional)</label>
      <input id="photo" type="file" accept="image/jpeg,image/png" onChange={(e) => setPhoto(e.target.files[0] || null)} />
      <p className="hint">Photograph only the barrier, without faces or license plates. We remove the location and phone data stored in the photo.</p>

      <label className="consent">
        <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
        <span>I have read the notice: the report will only be used to send the fix to the public agency. Personal data written by mistake is removed, and I can ask for the text and photo to be deleted using the protocol (LGPD).</span>
      </label>

      {error && <p className="error" role="alert">{error}</p>}
      <button type="submit" disabled={sending || text.trim().length < 10 || !consent}>
        {sending ? "Sending..." : "Submit report"}
      </button>
    </form>
  );
}
