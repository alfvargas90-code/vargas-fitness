/* Timing Weather — Phase 1 UI.
 * Renders state.json (written by engine.py) into four sections:
 *   1 Hero Sun · 3 Forecast Card · 4 Weather Metrics · 9 Narrative.
 * Polls state.json every 60s; re-renders only when generated_at changes
 * (same signature pattern as the fitness dashboard's Currents card). No fake
 * data — missing/null values render as "—".
 */
"use strict";

const cap = s => (s ? s.charAt(0).toUpperCase() + s.slice(1) : "—");
const dash = v => (v === null || v === undefined || v === "" ? "—" : v);

async function fetchState() {
  const r = await fetch("state.json", { cache: "no-store" });
  if (!r.ok) throw new Error(r.status);
  return r.json();
}

// ── Section 1 — Hero Sun ───────────────────────────────────────────────
const FORECAST_SUB = {
  EXPANSION:      "Doors opening — build the pipeline",
  CONSOLIDATION:  "Make it concrete — formalize and commit",
  TRANSFORMATION: "Deep restructuring underway",
  DISRUPTION:     "Expect the unexpected — stay adaptable",
  ATTRACTION:     "Relationships and resources in focus",
};

function renderHero(s) {
  const sun = document.getElementById("sun");
  sun.setAttribute("data-dominant", s.dominant_planet || "jupiter");
  document.getElementById("forecast-label").textContent = dash(s.forecast_label);
  document.getElementById("forecast-sub").textContent =
    FORECAST_SUB[s.forecast_label] || "Reading the chart…";
}

// ── Section 3 — Forecast Card ──────────────────────────────────────────
const CONF_COLOR = { High: "text-positive", Medium: "text-warning", Low: "text-danger" };

function renderForecastCard(s) {
  const dur = s.duration_days == null ? "—"
    : `${s.duration_days} day${s.duration_days === 1 ? "" : "s"}`;
  const confClass = CONF_COLOR[s.confidence] || "text-ink";
  const rows = [
    ["Forecast", `<span class="text-gold font-semibold">${dash(s.forecast_label)}</span>`],
    ["Dominant", `<span class="font-semibold">${cap(s.dominant_planet)}</span>`],
    ["Supporting", cap(s.supporting_planet)],
    ["Pressure source", cap(s.pressure_source)],
    ["Confidence", `<span class="${confClass} font-semibold">${dash(s.confidence)}</span>`],
    ["Duration", dur],
  ];
  document.getElementById("forecast-rows").innerHTML = rows.map(([k, v]) => `
    <div class="flex items-center justify-between py-3">
      <span class="text-muted text-sm">${k}</span>
      <span class="text-ink text-sm text-right">${v}</span>
    </div>`).join("");
}

// ── Section 4 — Weather Metrics ────────────────────────────────────────
// Opportunity/Momentum are "good high" (green at 75+); Pressure/Volatility
// are "bad high" (red at 75+). Mid ranges stay neutral white.
const METRICS = [
  { key: "opportunity", label: "Opportunity", good: true,
    desc: "How much the period favors gains and open doors." },
  { key: "pressure", label: "Pressure", good: false,
    desc: "Weight of responsibility, constraint, and demands." },
  { key: "volatility", label: "Volatility", good: false,
    desc: "Likelihood of sudden change or disruption." },
  { key: "momentum", label: "Momentum", good: true,
    desc: "How fast things are building toward a shift." },
];

function metricColor(v, good) {
  if (v == null) return "text-muted";
  if (v >= 75) return good ? "text-positive" : "text-danger";
  if (v <= 25) return good ? "text-muted" : "text-positive";
  return "text-ink";
}

function renderMetrics(s) {
  const wm = s.weather_metrics || {};
  document.getElementById("metrics-grid").innerHTML = METRICS.map(m => {
    const v = wm[m.key];
    const shown = v == null ? "—" : `${v}<span class="text-lg text-muted">%</span>`;
    return `
      <div class="rounded-2xl border border-line bg-card p-4">
        <div class="tab-num text-3xl font-bold ${metricColor(v, m.good)}">${shown}</div>
        <div class="text-ink text-sm font-medium mt-1">${m.label}</div>
        <div class="text-muted text-[12px] leading-snug mt-1.5">${m.desc}</div>
      </div>`;
  }).join("");
}

// ── Section 9 — Narrative ──────────────────────────────────────────────
function renderNarrative(s) {
  const el = document.getElementById("narrative");
  if (s.narrative) {
    el.textContent = s.narrative;
    el.classList.remove("text-muted");
    el.classList.add("text-ink/90");
  } else {
    el.textContent = "Narrative computation pending.";
    el.classList.remove("text-ink/90");
    el.classList.add("text-muted");
  }
}

function renderStamp(s) {
  const el = document.getElementById("stamp");
  if (!s.generated_at) { el.textContent = "—"; return; }
  const t = new Date(s.generated_at);
  el.textContent = `Updated ${t.toLocaleString([], { month: "short", day: "numeric",
    hour: "numeric", minute: "2-digit" })}`;
}

function renderAll(s) {
  renderHero(s);
  renderForecastCard(s);
  renderMetrics(s);
  renderNarrative(s);
  renderStamp(s);
}

// ── Polling ────────────────────────────────────────────────────────────
let _lastSig = null;
async function poll() {
  try {
    const s = await fetchState();
    const sig = s.generated_at || null;
    if (sig && sig !== _lastSig) { _lastSig = sig; renderAll(s); }
  } catch (e) {
    if (_lastSig === null) {
      document.getElementById("forecast-sub").textContent =
        "Waiting for the engine's first read…";
    }
  }
}

poll();
setInterval(poll, 60000);
