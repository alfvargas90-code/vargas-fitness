/* Timing Weather — v1.1 UI.
 * Renders state.json (written by engine.py, v1.1 camelCase contract) into the
 * 12-section locked page order:
 *   1 Hero Sun · 2 Current Phase · 3 Forecast Card · 4 Active Sky · 5 Top Drivers ·
 *   6 Forecast Trend · 7 Next Major Window · 8 Metrics Grid · 9 Recommended Actions ·
 *   10 Why This Forecast · 11 Narrative · 12 Timestamp.
 * Polls state.json every 60s; re-renders only when updatedAt changes. No fake data —
 * every value comes from the engine; missing/null renders as "—" or a hidden section
 * (PVR law: e.g. confidence null -> "Not Rated", nextWindow null -> hidden).
 */
"use strict";

const cap = s => (s ? s.charAt(0).toUpperCase() + s.slice(1) : "—");
const dash = v => (v === null || v === undefined || v === "" ? "—" : v);

const PLANET_GLYPH = {
  Sun: "☉", Moon: "☽", Mercury: "☿", Venus: "♀", Mars: "♂", Jupiter: "♃",
  Saturn: "♄", Uranus: "♅", Neptune: "♆", Pluto: "♇",
};

function fmtDate(iso) {
  if (!iso) return "—";
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString([], { month: "short", day: "numeric" });
}

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
  TRANSITION:     "Things are shifting — stay adaptable",
  PRESSURE:       "Under load — protect the essentials",
  NEUTRAL:        "Quiet skies — steady as she goes",
};

function renderHero(s) {
  const sun = document.getElementById("sun");
  sun.setAttribute("data-dominant", (s.dominantPlanet || "Jupiter").toLowerCase());
  document.getElementById("forecast-label").textContent = dash(s.forecast);
  document.getElementById("forecast-sub").textContent =
    FORECAST_SUB[s.forecast] || "Reading the chart…";
}

// ── Section 2 — Current Phase ──────────────────────────────────────────
function renderPhase(s) {
  document.getElementById("phase-name").textContent = dash(s.currentPhase);
  const span = (s.currentPhaseStart || s.currentPhaseEnd)
    ? `${fmtDate(s.currentPhaseStart)} – ${fmtDate(s.currentPhaseEnd)}`
    : "—";
  document.getElementById("phase-range").textContent = span;
}

// ── Section 3 — Forecast Card ──────────────────────────────────────────
const CONF_COLOR = { High: "text-positive", Medium: "text-warning", Low: "text-danger" };

function renderForecastCard(s) {
  const dur = s.durationDays == null ? "—"
    : `${s.durationDays} day${s.durationDays === 1 ? "" : "s"}`;
  // PVR: confidence null -> "Not Rated", never a fabricated grade.
  const conf = s.confidence == null
    ? `<span class="text-muted font-semibold">Not Rated</span>`
    : `<span class="${CONF_COLOR[s.confidence] || "text-ink"} font-semibold">${s.confidence}</span>`;
  const rows = [
    ["Forecast", `<span class="text-gold font-semibold">${dash(s.forecast)}</span>`],
    ["Dominant", `<span class="font-semibold">${dash(s.dominantPlanet)}</span>`],
    ["Supporting", dash(s.supportingPlanet)],
    ["Pressure source", dash(s.pressurePlanet)],
    ["Confidence", conf],
    ["Duration", dur],
  ];
  document.getElementById("forecast-rows").innerHTML = rows.map(([k, v]) => `
    <div class="flex items-center justify-between py-3">
      <span class="text-muted text-sm">${k}</span>
      <span class="text-ink text-sm text-right">${v}</span>
    </div>`).join("");
}

// ── Section 4 — Active Sky ─────────────────────────────────────────────
function renderActiveSky(s) {
  const rows = [
    ["Dominant", s.dominantPlanet],
    ["Supporting", s.supportingPlanet],
    ["Pressure", s.pressurePlanet],
    ["Volatility", s.volatilityPlanet],
  ];
  document.getElementById("sky-rows").innerHTML = rows.map(([role, planet]) => `
    <div class="flex items-center justify-between py-3">
      <span class="text-muted text-sm">${role}</span>
      <span class="text-right">
        <span class="text-ink text-sm font-medium">${dash(planet)}</span>
        <span class="text-muted text-base ml-2">${planet ? (PLANET_GLYPH[planet] || "") : ""}</span>
      </span>
    </div>`).join("");
}

// ── Section 5 — Top Drivers ────────────────────────────────────────────
function renderDrivers(s) {
  const sec = document.getElementById("sec-drivers");
  const drivers = s.drivers || [];
  if (!drivers.length) { sec.classList.add("hidden"); return; }
  sec.classList.remove("hidden");
  document.getElementById("drivers-list").innerHTML = drivers.map((d, i) => `
    <div class="flex items-center justify-between py-3">
      <span class="text-ink text-sm">
        <span class="text-muted tab-num mr-3">${i + 1}.</span>${dash(d.name)}
      </span>
      <span class="text-gold tab-num text-sm font-semibold">+${d.score}</span>
    </div>`).join("");
}

// ── Section 6 — Forecast Trend ─────────────────────────────────────────
const TREND_DIR = {
  Strengthening: { glyph: "↑", cls: "text-positive" },
  Stable:        { glyph: "→", cls: "text-muted" },
  Weakening:     { glyph: "↓", cls: "text-danger" },
};

function renderTrend(s) {
  const sec = document.getElementById("sec-trend");
  const pts = s.forecastTrend || [];
  if (pts.length < 2) { sec.classList.add("hidden"); return; }
  sec.classList.remove("hidden");
  document.getElementById("trend-rows").innerHTML = pts.map(p => `
    <div class="flex items-center justify-between py-2">
      <span class="text-muted text-sm tab-num">${fmtDate(p.date)}</span>
      <span class="text-ink text-sm">${dash(p.label)}</span>
    </div>`).join("");
  const dir = TREND_DIR[s.trendDirection];
  const el = document.getElementById("trend-direction");
  el.innerHTML = s.trendDirection
    ? `<span class="${dir ? dir.cls : "text-ink"} font-semibold">${dir ? dir.glyph : ""} ${s.trendDirection}</span>`
    : `<span class="text-muted">—</span>`;
}

// ── Section 7 — Next Major Window ──────────────────────────────────────
function renderNextWindow(s) {
  const sec = document.getElementById("sec-next");
  const w = s.nextWindow;
  if (!w) { sec.classList.add("hidden"); return; }
  sec.classList.remove("hidden");
  document.getElementById("next-title").textContent = dash(w.title);
  const bits = [];
  if (w.date) bits.push(fmtDate(w.date));
  if (w.daysRemaining != null) bits.push(`${w.daysRemaining} days out`);
  document.getElementById("next-date").textContent = bits.join(" · ") || "—";
  // strength: null -> hide per PVR
  const strEl = document.getElementById("next-strength");
  if (w.strength == null) {
    strEl.classList.add("hidden");
  } else {
    strEl.classList.remove("hidden");
    strEl.innerHTML = `<span class="tab-num text-gold font-semibold">${w.strength.toFixed(1)}</span><span class="text-muted">/10</span>`;
  }
  const cat = document.getElementById("next-category");
  if (w.category) { cat.classList.remove("hidden"); cat.textContent = w.category; }
  else { cat.classList.add("hidden"); }
}

// ── Section 8 — Weather Metrics ────────────────────────────────────────
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
  document.getElementById("metrics-grid").innerHTML = METRICS.map(m => {
    const v = s[m.key];
    const shown = v == null ? "—" : `${v}<span class="text-lg text-muted">%</span>`;
    return `
      <div class="rounded-2xl border border-line bg-card p-4">
        <div class="tab-num text-3xl font-bold ${metricColor(v, m.good)}">${shown}</div>
        <div class="text-ink text-sm font-medium mt-1">${m.label}</div>
        <div class="text-muted text-[12px] leading-snug mt-1.5">${m.desc}</div>
      </div>`;
  }).join("");
}

// ── Section 9 — Recommended Actions ────────────────────────────────────
function renderActions(s) {
  const sec = document.getElementById("sec-actions");
  const recs = s.recommendations || [];
  const avoid = s.avoidances || [];
  if (!recs.length && !avoid.length) { sec.classList.add("hidden"); return; }
  sec.classList.remove("hidden");
  document.getElementById("do-list").innerHTML = recs.map(r => `
    <li class="flex items-start gap-2.5 py-1.5">
      <span class="text-positive mt-0.5">✓</span>
      <span class="text-ink text-sm">${r}</span>
    </li>`).join("") || `<li class="text-muted text-sm py-1.5">—</li>`;
  document.getElementById("avoid-list").innerHTML = avoid.map(a => `
    <li class="flex items-start gap-2.5 py-1.5">
      <span class="text-danger mt-0.5">✗</span>
      <span class="text-ink text-sm">${a}</span>
    </li>`).join("") || `<li class="text-muted text-sm py-1.5">—</li>`;
}

// ── Section 10 — Why This Forecast (collapsible) ───────────────────────
function renderWhy(s) {
  const sec = document.getElementById("sec-why");
  const ev = (s.evidence || []).slice().sort((a, b) => Math.abs(b.score) - Math.abs(a.score));
  if (!ev.length) { sec.classList.add("hidden"); return; }
  sec.classList.remove("hidden");
  document.getElementById("why-summary").innerHTML =
    `<span class="text-gold font-semibold">${dash(s.forecast)}</span>` +
    (s.opportunity != null ? `<span class="text-muted"> · Opportunity ${s.opportunity}/100</span>` : "");
  document.getElementById("why-rows").innerHTML = ev.map(f => {
    const pos = f.score >= 0;
    const cls = pos ? "text-positive" : "text-danger";
    const sign = pos ? "+" : "−";
    return `
      <div class="flex items-center justify-between py-2">
        <span class="text-ink text-sm">${dash(f.factor)}</span>
        <span class="${cls} tab-num text-sm font-semibold">${sign}${Math.abs(f.score)}</span>
      </div>`;
  }).join("");
}

// ── Section 11 — Narrative ─────────────────────────────────────────────
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

// ── Section 12 — Timestamp ─────────────────────────────────────────────
function renderStamp(s) {
  const el = document.getElementById("stamp");
  if (!s.updatedAt) { el.textContent = "—"; return; }
  const t = new Date(s.updatedAt);
  el.textContent = `Updated ${t.toLocaleString([], { month: "short", day: "numeric",
    hour: "numeric", minute: "2-digit" })}`;
}

function renderAll(s) {
  renderHero(s);
  renderPhase(s);
  renderForecastCard(s);
  renderActiveSky(s);
  renderDrivers(s);
  renderTrend(s);
  renderNextWindow(s);
  renderMetrics(s);
  renderActions(s);
  renderWhy(s);
  renderNarrative(s);
  renderStamp(s);
}

// ── Polling ────────────────────────────────────────────────────────────
let _lastSig = null;
async function poll() {
  try {
    const s = await fetchState();
    const sig = s.updatedAt || null;
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
