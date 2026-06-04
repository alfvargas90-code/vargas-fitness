// ---------- Storage ----------
const KEY_WEIGHT  = "fd.weight.v2";   // v2: added 2026-05-20 lean reading
const KEY_GOALS   = "fd.goals.v1";
const KEY_SCALE   = "fd.scale.v2";    // v2: added 2026-05-20 lean reading

function load(key, seed) {
  try {
    const raw = localStorage.getItem(key);
    if (raw) { try { return JSON.parse(raw); } catch {} }
    localStorage.setItem(key, JSON.stringify(seed));
  } catch (e) { /* storage blocked (e.g. Safari on file://) — render from seed in memory */ }
  return seed;
}
function save(key, val) { try { localStorage.setItem(key, JSON.stringify(val)); } catch (e) {} }

let weight = load(KEY_WEIGHT, SEED_WEIGHT);
let goals  = load(KEY_GOALS,  SEED_GOALS);
let scale  = load(KEY_SCALE,  SEED_SCALE);

// ---------- Helpers ----------
const fmt = (n, d = 1) => (n == null || isNaN(n) ? "—" : Number(n).toFixed(d));
const byDate = (a, b) => a.date.localeCompare(b.date);
const latestScale = () => [...scale].sort(byDate).at(-1);

// ---------- Today's load bands (SINGLE SOURCE OF TRUTH) ----------
// Interprets today's accumulated Polar active-calories into one load band. The
// Recovery tile's Reserve bar and the Activity card's load chip share the same
// 800-cal Heavy threshold — change it here and every section follows, so they can
// never contradict. The Python side (polar/lunar_stress.py LOAD_BANDS,
// polar/summary.py) mirrors these exact bands for the LSI + AI prompts.
const LOAD_BANDS = [
  { name: "—",        min: 0,   max: 49,       dot: "#64748b" }, // slate-500 (faint — no real activity yet)
  { name: "Light",    min: 50,  max: 399,      dot: "#94A3B8" }, // slate-400 — minimal
  { name: "Moderate", min: 400, max: 799,      dot: "#06B6D4" }, // cyan — engaged
  { name: "Heavy",    min: 800, max: Infinity, dot: "#F59E0B" }, // amber — heavy load (warning)
];
function loadBandFor(activeCal) {
  const c = (activeCal == null || isNaN(activeCal)) ? 0 : Number(activeCal);
  return LOAD_BANDS.find(b => c >= b.min && c <= b.max) || LOAD_BANDS[0];
}
// "● Light" style chip: colored dot + band name. Used by Recovery + Activity.
function loadBandChipHTML(band) {
  return `<span class="inline-block w-2.5 h-2.5 rounded-full align-middle" style="background:${band.dot}"></span>`
       + `<span class="align-middle"> ${band.name}</span>`;
}

// ---------- Data freshness ----------
// Whole-day delta between a YYYY-MM-DD string and today (local time).
function daysSinceDate(dateStr) {
  if (!dateStr) return null;
  const [y, m, d] = dateStr.split("-").map(Number);
  const then = new Date(y, m - 1, d);
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  return Math.round((today - then) / 86400000);
}
// Visible freshness badge. 0d → "Today" (normal), 1–2d → "X days ago" (normal),
// 3+d → amber "⚠️ X days stale — <nudge>". `nudge` is the per-source action.
function freshnessHTML(dateStr, nudge) {
  const n = daysSinceDate(dateStr);
  if (n == null) return `<span class="text-muted">—</span>`;
  if (n <= 0) return `<span class="text-slate-300">Today · ${dateStr}</span>`;
  if (n <= 2) return `<span class="text-slate-300">${n} day${n === 1 ? "" : "s"} ago · ${dateStr}</span>`;
  return `<span class="text-warn font-medium">⚠️ ${n} days stale — ${nudge}</span>`;
}

function bfPercentileBand(age, bf) {
  const row = BF_PERCENTILES_MEN.find(r => {
    if (r.age === ">60") return age > 60;
    const [lo, hi] = r.age.split("-").map(Number);
    return age >= lo && age <= hi;
  });
  if (!row) return "—";
  if (bf < row.p20) return "Top 20% (lean)";
  if (bf < row.p40) return "20–40th percentile";
  if (bf < row.p60) return "40–60th percentile";
  if (bf < row.p80) return "60–80th percentile";
  return "Above 80th percentile";
}

// ---------- Render ----------
function renderHeader() {
  const sub = document.getElementById("header-sub");
  if (!sub) return;
  const now = new Date();
  const date = now.toLocaleDateString("en-US", {
    weekday: "long", year: "numeric", month: "long", day: "numeric",
  });
  const time = now.toLocaleTimeString("en-US", {
    hour: "numeric", minute: "2-digit",
  });
  sub.textContent = `${date} · ${time}`;
}

function ageOn(dateStr) {
  // DOB from DEXA: 1990-08-30
  const dob = new Date("1990-08-30");
  const d = new Date(dateStr);
  let a = d.getFullYear() - dob.getFullYear();
  const m = d.getMonth() - dob.getMonth();
  if (m < 0 || (m === 0 && d.getDate() < dob.getDate())) a--;
  return a;
}

// ---------- Charts ----------
const charts = {};
const baseChartOpts = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: { legend: { labels: { color: "#cbd5e1" } } },
  scales: {
    x: { ticks: { color: "#9ca3af" }, grid: { color: "#374151" } },
    y: { ticks: { color: "#9ca3af" }, grid: { color: "#374151" } },
  },
};

// ---------- Training / Recovery / Activity / Nutrition ----------
function renderProfileStrip() {
  const p = typeof SEED_PROFILE !== "undefined" ? SEED_PROFILE : null;
  const el = document.getElementById("profile-strip");
  if (!el) return;
  el.textContent = "";
}

// ---------- Polar live data (Training & Recovery) ----------
// Reads polar/manifest.json + per-day JSON written by polar/sync.py.
// fetch() works when the dashboard is served over http(s); on file:// it
// fails gracefully to the empty-state.
async function fetchJSON(path) {
  const r = await fetch(path, { cache: "no-store" });
  if (!r.ok) throw new Error(r.status);
  return r.json();
}

const secsToHM = s => (s == null ? "—" : `${Math.floor(s / 3600)}h ${Math.round((s % 3600) / 60)}m`);
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const labelMD = d => { const [, m, day] = d.split("-"); return `${MONTHS[+m - 1]} ${+day}`; };

// Build [oldest…today] list of YYYY-MM-DD for the last `daysBack` calendar days (local time).
function lastN(daysBack = 14) {
  const out = [], t = new Date();
  for (let i = daysBack - 1; i >= 0; i--) {
    const d = new Date(t.getFullYear(), t.getMonth(), t.getDate() - i);
    out.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`);
  }
  return out;
}

async function renderPolar() {
  const empty = document.getElementById("polar-empty");
  const content = document.getElementById("polar-content");
  if (!empty || !content) return;
  const showEmpty = () => { empty.classList.remove("hidden"); content.classList.add("hidden"); };
  try {
    const manifest = await fetchJSON("polar/manifest.json");
    const cats = manifest.categories || {};
    const recDates = (cats.recharge || []).slice().sort(), sleepDates = (cats.sleep || []).slice().sort();
    if (!recDates.length && !sleepDates.length) return showEmpty();

    const recArr   = await Promise.all(recDates.map(d => fetchJSON(`polar/recharge/${d}.json`).catch(() => null)));
    const sleepArr = await Promise.all(sleepDates.map(d => fetchJSON(`polar/sleep/${d}.json`).catch(() => null)));
    const recMap = {}, sleepMap = {};
    recDates.forEach((d, i) => { if (recArr[i]) recMap[d] = recArr[i]; });
    sleepDates.forEach((d, i) => { if (sleepArr[i]) sleepMap[d] = sleepArr[i]; });

    // Nightly Recharge: walk backwards and keep only nights that actually have a
    // recharge value (band worn), within the last 90 days — then take the 10 most
    // recent. No empty placeholder rows for nights the band wasn't worn.
    const cutoff90 = lastN(90)[0];
    const rechargeDays = recDates.filter(d => d >= cutoff90 && recMap[d]?.ans_charge_status != null);
    const window10 = rechargeDays.slice(-10);
    renderRechargeStack(window10, recMap);
    renderRechargeTrend(window10, recMap, rechargeDays.length);
    renderPolarSleep(sleepMap[sleepDates.at(-1)]);   // Block B — most recent date with sleep data
    renderHRV(recDates, recMap);

    const polarLatest = [recDates.at(-1), sleepDates.at(-1)].filter(Boolean).sort().at(-1) || null;
    document.getElementById("polar-sub").innerHTML = freshnessHTML(polarLatest, "wear the watch");
    empty.classList.add("hidden");
    content.classList.remove("hidden");
  } catch (e) {
    showEmpty(); // file:// or no sync yet
  }
}

// ---------- Glance rings (Whoop-style — Sleep / Recovery / Strain) ----------
// Three SVG rings at the top: last night's sleep score, the overnight recovery
// score (lifted from the old Recovery tile), and today's strain (the inverse of
// the old Reserve bar — % of the 800-cal Heavy threshold spent). Each ring taps
// through to the detail card that owns its context.

// Strain fills against the same 800-cal Heavy threshold the LOAD_BANDS use, so
// the Strain ring and the Activity load chip can never contradict.
const RESERVE_DEPLETION_CAL = 800;

// Concept 02 semantic ring colors. Sleep + Recovery live in the CYAN recovery
// family (bright cyan = restored, dropping toward amber/coral as readiness
// falls); Strain lives in the CORAL/AMBER strain family (calm slate → amber
// building → coral heavy → red max). Purple is reserved for intelligence/
// context and never appears on these physiological rings. The soft glow is
// applied uniformly in orbitGroup().
function sleepColor(v) {              // Sleep — recovery family (cyan)
  return v >= 90 ? "#22D3EE"   // bright cyan — excellent sleep
       : v >= 50 ? "#06B6D4"   // cyan — good
       : v >= 30 ? "#0891B2"   // dim cyan — low
       :           "#155E75";  // deep cyan — chronic-low
}
function energyColor(v) {             // Recovery — cyan when restored, warns as it falls
  return v >= 90 ? "#10B981"   // green — peak recovery (performance-ready)
       : v >= 50 ? "#06B6D4"   // cyan — good recovery
       : v >= 30 ? "#F59E0B"   // amber — low (caution)
       :           "#FF6B6B";  // coral — poor (recovery risk)
}
function strainColor(pct) {           // Strain — strain family, hotter with load
  return pct < 15 ? "#64748B"   // slate — nothing meaningful yet (calm)
       : pct < 50 ? "#F59E0B"   // amber — light/moderate load building
       : pct < 80 ? "#FF8A8A"   // light coral — real load
       : pct < 95 ? "#FF6B6B"   // coral — heavy
       :            "#EF4444";  // red — max / red zone
}

// Overnight recovery score — combines recharge + sleep + HRV vs an adaptive HRV
// baseline. Lifted verbatim from the deleted renderRecoveryTile so the Recovery
// ring stays data-honest. Each part falls back if its metric is missing.
function computeRecoveryScore(rec, sleep, hrvBaseline) {
  const rechargePart = rec?.ans_charge_status != null ? (rec.ans_charge_status / 6) * 50 : 25;
  const sleepPart    = sleep?.sleep_score != null ? (sleep.sleep_score / 100) * 30 : 15;
  const hrvPart      = (rec?.heart_rate_variability_avg != null && hrvBaseline)
    ? Math.min(rec.heart_rate_variability_avg / hrvBaseline, 1) * 20 : 10;
  return Math.round(Math.min(rechargePart + sleepPart + hrvPart, 100));
}

// ── Design C: planetary orbit ──────────────────────────────────────────────
// ONE composite SVG: a phase-accurate moon at the center, three orbital rings
// around it (Recovery inner → Sleep mid → Strain outer), all at a uniform 35°
// tilt so they read as a single tilted disk. Each orbit is a HYBRID fill: a
// faint full ellipse (the orbit) + a brighter, color-semantic arc swept
// clockwise from the ellipse top to the data point. Percent values live in
// floating corner labels (in index.html), not on the rings.

// LPI v1 flat semantic colors (spec color table) — one fixed hue per metric,
// replacing the Concept 02 severity gradients on the orbital rings + corners.
const LPI = {
  recovery: "#00C8FF",  // Recovery
  sleep:    "#9B5CFF",  // Sleep
  strain:   "#FF5E62",  // Strain
  activity: "#FF8A3D",  // Activity
  nutrition:"#39D98A",  // Nutrition
  context:  "#8A5CFF",  // Context (Lunar)
};

const ORBIT = {
  cx: 150, cy: 150,          // viewBox center (viewBox is 0 0 300 300)
  tilt: 35, flatten: 0.55,   // 35° disk; ry = rx * 0.55
  moonR: 30,                 // inner orbit clears the moon by ~14px at its narrowest
  // LPI v1 ring assignment (SWAP from Concept 02): Sleep is now innermost,
  // Recovery middle, Strain outer + highest visual weight.
  rings: {                   // inside → out
    sleep:    { rx: 80 },
    recovery: { rx: 104 },
    strain:   { rx: 128 },
  },
  base: "#241B3A",           // faint orbit track (muted violet — metadata)
  arcW: 5, baseW: 2,         // thinner active stroke than Concept 02 (was 6)
};

// Ramanujan ellipse-perimeter approximation — used as the dash period so the
// color arc length maps linearly to percent.
function ellipsePerimeter(rx, ry) {
  const h = ((rx - ry) ** 2) / ((rx + ry) ** 2);
  return Math.PI * (rx + ry) * (1 + (3 * h) / (10 + Math.sqrt(4 - 3 * h)));
}

// Full-ellipse path starting at the top (0,-ry) and sweeping CLOCKWISE, so a
// dash of length (pct/100 · perimeter) from the start renders the 12-o'clock→
// percentage arc. Drawn inside the rotated group, so "top" is the disk's top.
function orbitPath(rx, ry) {
  return `M 0 ${-ry} A ${rx} ${ry} 0 0 1 0 ${ry} A ${rx} ${ry} 0 0 1 0 ${-ry}`;
}

// One hybrid orbit: faint full ellipse + bright semantic arc, both tilted 35°.
function orbitGroup(rx, pct, color) {
  const ry = +(rx * ORBIT.flatten).toFixed(2);
  const perim = ellipsePerimeter(rx, ry);
  const arc = (Math.max(0, Math.min(100, pct || 0)) / 100) * perim;
  // Soft glow on the bright arc only (Concept 03 DEPTH pillar) — additive light
  // on OLED black. Skipped for the faint default (base gray, ~0-length arc).
  const glow = color !== ORBIT.base ? ` filter="drop-shadow(0 0 6px ${color})"` : "";
  return `<g transform="rotate(${ORBIT.tilt})">
    <ellipse cx="0" cy="0" rx="${rx}" ry="${ry}" fill="none" stroke="${ORBIT.base}" stroke-width="${ORBIT.baseW}"/>
    <path d="${orbitPath(rx, ry)}" fill="none" stroke="${color}" stroke-width="${ORBIT.arcW}"
          stroke-linecap="round" stroke-dasharray="${arc.toFixed(2)} ${perim.toFixed(2)}"${glow}/>
  </g>`;
}

// Phase name → {illum 0-1, waning}. lunar_stress.json carries no
// phase_illumination_pct, so we map from the phase name (documented fallback).
function phaseToIllum(phase) {
  const p = (phase || "").toLowerCase();
  if (p.includes("new")) return { illum: 0.02, waning: false };
  if (p.includes("full")) return { illum: 1, waning: false };
  if (p.includes("first quarter")) return { illum: 0.5, waning: false };
  if (p.includes("last quarter") || p.includes("third quarter")) return { illum: 0.5, waning: true };
  if (p.includes("waning") && p.includes("gibbous")) return { illum: 0.67, waning: true };
  if (p.includes("waning") && p.includes("crescent")) return { illum: 0.28, waning: true };
  if (p.includes("waxing") && p.includes("gibbous")) return { illum: 0.72, waning: false };
  if (p.includes("waxing") && p.includes("crescent")) return { illum: 0.28, waning: false };
  return { illum: 0.5, waning: true };
}

// Realistic phase-accurate moon. Same near-side face every render (the Moon is
// tidally locked, so maria + craters sit at FIXED positions — north up); only the
// phase shadow advances. Coordinates below are fractions of the moon radius.
//   - maria  : large dark basalt seas (soft, blurred)
//   - dark   : small pit craters for surface texture
//   - bright : ray craters (Tycho, Copernicus, Kepler) — bright dot + faint halo
const MOON_MARIA = [               // x, y, rx, ry (fractions of r), opacity
  { x: -0.34, y: -0.40, rx: 0.34, ry: 0.27, o: 0.34 }, // Mare Imbrium (upper-left)
  { x:  0.06, y: -0.44, rx: 0.19, ry: 0.17, o: 0.32 }, // Mare Serenitatis (upper-center)
  { x:  0.40, y: -0.16, rx: 0.22, ry: 0.21, o: 0.34 }, // Mare Tranquillitatis (right of center)
  { x:  0.64, y: -0.30, rx: 0.11, ry: 0.09, o: 0.32 }, // Mare Crisium (near right limb)
  { x:  0.44, y:  0.26, rx: 0.15, ry: 0.18, o: 0.28 }, // Nectaris / Fecunditatis
  { x: -0.22, y:  0.42, rx: 0.23, ry: 0.16, o: 0.28 }, // Mare Nubium (lower-left)
  { x: -0.56, y:  0.06, rx: 0.20, ry: 0.40, o: 0.20 }, // Oceanus Procellarum (diffuse west)
  { x: -0.46, y:  0.48, rx: 0.10, ry: 0.10, o: 0.24 }, // Mare Humorum
];
const MOON_CRATERS_DARK = [        // x, y, r (fractions of r)
  { x:  0.20, y:  0.30, r: 0.030 }, { x:  0.10, y: -0.10, r: 0.024 },
  { x: -0.30, y: -0.18, r: 0.030 }, { x:  0.30, y:  0.52, r: 0.024 },
  { x:  0.52, y:  0.06, r: 0.022 }, { x: -0.12, y:  0.30, r: 0.028 },
  { x:  0.26, y: -0.34, r: 0.022 },
];
const MOON_CRATERS_BRIGHT = [      // ray craters — x, y, r (fractions of r)
  { x: -0.05, y:  0.55, r: 0.050 }, // Tycho (lower-center, slightly south)
  { x: -0.18, y:  0.02, r: 0.044 }, // Copernicus
  { x: -0.40, y:  0.06, r: 0.034 }, // Kepler
];

function moonSVG(r, illum, waning) {
  const rxT = +(r * Math.abs(1 - 2 * illum)).toFixed(2); // terminator semi-axis
  const limbSweep = waning ? 1 : 0;                       // outer semicircle on the shadow side
  const termSweep = waning ? (illum >= 0.5 ? 0 : 1) : (illum >= 0.5 ? 1 : 0);
  const shadow = `M 0 ${-r} A ${r} ${r} 0 0 ${limbSweep} 0 ${r} A ${rxT} ${r} 0 0 ${termSweep} 0 ${-r} Z`;
  const dim = illum > 0.99; // full moon → no shadow path
  const f = (n) => +(n * r).toFixed(2);

  const maria = MOON_MARIA.map((m) =>
    `<ellipse cx="${f(m.x)}" cy="${f(m.y)}" rx="${f(m.rx)}" ry="${f(m.ry)}" fill="#6c6c75" opacity="${m.o}"/>`
  ).join("");
  const darkC = MOON_CRATERS_DARK.map((c) =>
    `<circle cx="${f(c.x)}" cy="${f(c.y)}" r="${f(c.r)}" fill="#5b5b63" opacity="0.5"/>`
  ).join("");
  const brightC = MOON_CRATERS_BRIGHT.map((c) =>
    `<circle cx="${f(c.x)}" cy="${f(c.y)}" r="${f(c.r * 1.9)}" fill="#f1f1f3" opacity="0.16"/>` +
    `<circle cx="${f(c.x)}" cy="${f(c.y)}" r="${f(c.r)}" fill="#eaeaed" opacity="0.55"/>`
  ).join("");

  // Light from upper-left (gradient center offset) + limb darkening toward the
  // edge → a spherical, photographic body rather than a flat disk.
  return `<defs>
      <radialGradient id="moonBody" cx="40%" cy="36%" r="68%">
        <stop offset="0%"  stop-color="#ededf0"/>
        <stop offset="48%" stop-color="#d4d4d8"/>
        <stop offset="78%" stop-color="#b1b1b8"/>
        <stop offset="100%" stop-color="#83838b"/>
      </radialGradient>
      <clipPath id="moonClip"><circle cx="0" cy="0" r="${r}"/></clipPath>
      <filter id="moonTex" x="-30%" y="-30%" width="160%" height="160%">
        <feGaussianBlur stdDev="${f(0.022)}"/></filter>
      <filter id="moonTerm" x="-40%" y="-40%" width="180%" height="180%">
        <feGaussianBlur stdDev="${f(0.05)}"/></filter>
    </defs>
    <g clip-path="url(#moonClip)">
      <circle cx="0" cy="0" r="${r}" fill="url(#moonBody)"/>
      <g filter="url(#moonTex)">${maria}${darkC}</g>
      ${brightC}
      ${dim ? "" : `<path d="${shadow}" fill="#141419" opacity="0.92" filter="url(#moonTerm)"/>`}
    </g>
    <circle cx="0" cy="0" r="${r}" fill="none" stroke="#3c3c44" stroke-width="1"/>`;
}

// Assemble the composite SVG and inject; null pct → empty orbit (faint only).
function renderOrbit({ recovery, sleep, strain, moon }) {
  const host = document.getElementById("rings-orbit-svg");
  if (!host) return;
  const { cx, cy, moonR } = ORBIT;
  const m = moon || { illum: 0.5, waning: true };
  host.innerHTML = `<svg viewBox="0 0 300 300" width="100%" height="100%" class="block"
       preserveAspectRatio="xMidYMid meet" aria-label="Orbit rings around moon">
    <g transform="translate(${cx} ${cy})">
      ${orbitGroup(ORBIT.rings.strain.rx,   strain?.pct,   strain?.color   || ORBIT.base)}
      ${orbitGroup(ORBIT.rings.sleep.rx,    sleep?.pct,    sleep?.color    || ORBIT.base)}
      ${orbitGroup(ORBIT.rings.recovery.rx, recovery?.pct, recovery?.color || ORBIT.base)}
      ${moonSVG(moonR, m.illum, m.waning)}
    </g>
  </svg>`;
}

// ── LPI v1 metric-corner label bands ───────────────────────────────────────
// Qualitative word under each big number. Derived from the same score the ring
// arc renders, so the corner word and the arc length never disagree.
function recoveryLabel(score) {
  return score >= 85 ? "Peak" : score >= 70 ? "Excellent" : score >= 50 ? "Good"
       : score >= 30 ? "Fair" : "Low";
}
function sleepLabel(score) {
  return score >= 85 ? "Excellent" : score >= 70 ? "Good" : score >= 55 ? "Fair"
       : score >= 40 ? "Low" : "Poor";
}
function strainLabel(pct) {
  return pct >= 95 ? "Very High" : pct >= 80 ? "High" : pct >= 50 ? "Moderate"
       : pct >= 15 ? "Light" : "Minimal";
}

// Set one hero metric corner: big number + qualitative label + small detail.
// `color` tints number+label; null metric → em-dash + muted, glow cleared.
function setMetricCorner(key, val, label, detail, color) {
  const numEl = document.getElementById(`m-${key}-val`);
  const lblEl = document.getElementById(`m-${key}-label`);
  const detEl = document.getElementById(`m-${key}-detail`);
  if (numEl) {
    numEl.textContent = val ?? "—";
    numEl.style.color = color || ORBIT.base;
    numEl.style.textShadow = (val != null && color) ? `0 0 10px ${color}` : "none";
  }
  if (lblEl) { lblEl.textContent = label || ""; lblEl.style.color = color || "#9CA3AF"; }
  if (detEl) detEl.textContent = detail || "";
}

// Phase readout under the moon: "Waning Gibbous · Moon in Capricorn" + the
// next-sign-change line (uses lunar_stress.json's own ENTERS/LEAVES verb — the
// `display` string is authoritative, so the verb is whatever the data says).
function renderMoonReadout(lunar) {
  const main = document.getElementById("moon-readout-main");
  const sub  = document.getElementById("moon-readout-sub");
  if (!main) return;
  const L = lunar?.lunar;
  if (!L || !L.sign) { main.textContent = "—"; if (sub) sub.textContent = ""; return; }
  const parts = [];
  if (L.phase) parts.push(L.phase);
  parts.push(`Moon in ${L.sign}`);
  main.textContent = parts.join(" · ");
  if (sub) {
    const bits = [];
    if (L.next_sign_change && L.next_sign_change.display) bits.push(L.next_sign_change.display);
    if (L.void_of_course && L.void_of_course.active)
      bits.push(`Void of Course until ${L.void_of_course.until_display || "next ingress"}`);
    sub.textContent = bits.join("  ·  ");
  }
}

async function renderRings() {
  const host = document.getElementById("rings-orbit-svg");
  if (!host) return;

  // Defaults — faint orbits + a half-lit moon so something renders on file:// / no sync.
  let recovery = null, sleep = null, strain = null;
  let moon = { illum: 0.5, waning: true };
  // Corner detail values (kept around so the corners + Today's Read agree).
  let recoveryScore = null, sleepScore = null, sleepDur = null, strainPct = null,
      strainCal = null, hrvDeltaPct = null;

  try {
    const lunar = await fetchJSON("polar/lunar_stress.json").catch(() => null);
    if (lunar?.lunar) {
      const { illum, waning } = phaseToIllum(lunar.lunar.phase);
      moon = { illum, waning };
    }
    renderMoonReadout(lunar);

    const cats = (await fetchJSON("polar/manifest.json")).categories || {};
    const recDates   = (cats.recharge || []).slice().sort();
    const sleepDates = (cats.sleep || []).slice().sort();
    const actDates   = (cats.daily_activity || []).slice().sort();

    // --- SLEEP — most recent sleep_score, only if fresh (≤1 day old) ---
    const sleepDate = sleepDates.at(-1) || null;
    const sleepFresh = sleepDate && (daysSinceDate(sleepDate) ?? 99) <= 1;
    const sleepData = sleepDate ? await fetchJSON(`polar/sleep/${sleepDate}.json`).catch(() => null) : null;
    if (sleepFresh && sleepData?.sleep_score != null) {
      sleepScore = Math.round(sleepData.sleep_score);
      const durSecs = (sleepData.light_sleep || 0) + (sleepData.deep_sleep || 0) + (sleepData.rem_sleep || 0);
      sleepDur = durSecs ? secsToHM(durSecs) : null;
      sleep = { pct: sleepScore, color: LPI.sleep };
    }

    // --- RECOVERY — lifted overnight recovery score ---
    const recDate = recDates.at(-1) || null;
    const latestRecovDate = [recDate, sleepDate].filter(Boolean).sort().at(-1);
    const recovFresh = latestRecovDate && (daysSinceDate(latestRecovDate) ?? 99) <= 1;
    if (recovFresh) {
      const rec = recDate ? await fetchJSON(`polar/recharge/${recDate}.json`).catch(() => null) : null;
      const hrvs = (await Promise.all(recDates.map(d => fetchJSON(`polar/recharge/${d}.json`).catch(() => null))))
        .map(r => r?.heart_rate_variability_avg).filter(v => v != null);
      const hrvBaseline = hrvs.length ? hrvs.reduce((a, b) => a + b, 0) / hrvs.length : null;
      recoveryScore = computeRecoveryScore(rec, sleepData, hrvBaseline);
      // Corner HRV delta uses the SAME 7-day baseline the physiology grid + LSI
      // use (lunar.physiology.hrv_pct_baseline), so the two never disagree. Falls
      // back to the recovery-score baseline only if the LSI value is unavailable.
      if (lunar?.physiology?.hrv_pct_baseline != null)
        hrvDeltaPct = Math.round(lunar.physiology.hrv_pct_baseline);
      else if (rec?.heart_rate_variability_avg != null && hrvBaseline)
        hrvDeltaPct = Math.round((rec.heart_rate_variability_avg / hrvBaseline - 1) * 100);
      recovery = { pct: recoveryScore, color: LPI.recovery };
    }

    // --- STRAIN — inverse of the old Reserve bar (depletion % of 800 cal) ---
    const actDate = actDates.at(-1) || null;
    const actFresh = actDate && (daysSinceDate(actDate) ?? 99) <= 1;
    const act = actDate ? await fetchJSON(`polar/daily_activity/${actDate}.json`).catch(() => null) : null;
    if (actFresh && act && act["active-calories"] != null) {
      strainCal = Math.round(Number(act["active-calories"]));
      strainPct = Math.min(100, (strainCal / RESERVE_DEPLETION_CAL) * 100);
      strain = { pct: strainPct, color: LPI.strain };
    }
  } catch (e) { /* file:// or no sync yet → orbits stay faint, corners "—" */ }

  renderOrbit({ recovery, sleep, strain, moon });

  // Hero metric corners (big number + label + detail), all from real data.
  setMetricCorner("recovery",
    recoveryScore != null ? `${recoveryScore}` : null,
    recoveryScore != null ? recoveryLabel(recoveryScore) : "",
    hrvDeltaPct != null ? `HRV ${hrvDeltaPct >= 0 ? "+" : ""}${hrvDeltaPct}%` : "",
    LPI.recovery);
  setMetricCorner("sleep",
    sleepScore != null ? `${sleepScore}` : null,
    sleepScore != null ? sleepLabel(sleepScore) : "",
    sleepDur || "",
    LPI.sleep);
  setMetricCorner("strain",
    strainPct != null ? `${Math.round(strainPct)}%` : null,
    strainPct != null ? strainLabel(strainPct) : "",
    strainCal != null ? `Load ${strainCal}` : "",
    LPI.strain);

  // Recovery Window derives from the same recovery/sleep/strain state — render
  // it here so it can never disagree with the corners (no second fetch pass).
  renderRecoveryWindow({ recoveryScore, sleepScore, strainPct, strainCal });
}

// ---------- Recovery Window (derived status card) ----------
// Reads the recovery/sleep/strain state already computed for the rings and
// derives a single window status. The bar visualizes "recovery charge" (the
// recovery score) — there is no server-side future-window/countdown feed, so
// the bar is the charge level, not a literal timer (flagged in LPI v1 risks).
function renderRecoveryWindow(s) {
  const statusEl = document.getElementById("rw-status");
  const dotEl = document.getElementById("rw-status-dot");
  const chipEl = document.getElementById("rw-status-chip");
  const bar = document.getElementById("rw-bar");
  const left = document.getElementById("rw-bar-left");
  const right = document.getElementById("rw-bar-right");
  const note = document.getElementById("rw-note");
  if (!statusEl) return;

  const rec = s.recoveryScore, slp = s.sleepScore, str = s.strainPct;
  if (rec == null) {
    statusEl.textContent = "Awaiting sync";
    if (dotEl) dotEl.style.background = "#64748B";
    if (chipEl) { chipEl.style.color = "#9CA3AF"; chipEl.style.background = "rgba(255,255,255,0.05)"; }
    if (bar) { bar.style.width = "0%"; }
    if (left) left.textContent = ""; if (right) right.textContent = "";
    if (note) note.textContent = "Recovery window computes on the next Polar sync.";
    return;
  }

  // Derivation: recovered + light load → train window open; recovered but heavy
  // load / short sleep → recovery window; mid recovery → build; low → rest.
  let status, color, derived;
  const heavy = (str ?? 0) >= 50;
  const shortSleep = slp != null && slp < 55;
  if (rec >= 70 && !heavy && !shortSleep) {
    status = "Optimal Now"; color = LPI.nutrition;
    derived = "Recovery is high and today's load is still light — this is the window to put in real work.";
  } else if (rec >= 70) {
    status = "Recover & Rebuild"; color = LPI.recovery;
    derived = heavy && shortSleep
      ? "You're recovered, but today ran heavy on short sleep — protect the rebuild: protein, hydration, an earlier night."
      : heavy ? "Recovered, but you've already spent real load today — bank it rather than stacking more strain."
      : "Recovered, but last night ran short — feed the rebuild and get a longer night to convert it.";
  } else if (rec >= 50) {
    status = "Build Phase"; color = LPI.activity;
    derived = "Recovery is mid-range — moderate, controlled effort builds without digging a hole.";
  } else {
    status = "Rest Now"; color = LPI.strain;
    derived = "Recovery is low — back off and let the nervous system reset before the next hard session.";
  }

  statusEl.textContent = status;
  if (dotEl) dotEl.style.background = color;
  if (chipEl) { chipEl.style.color = color; chipEl.style.background = "rgba(255,255,255,0.05)"; }
  if (bar) { bar.style.width = `${Math.max(4, Math.round(rec))}%`; bar.style.background = color; }
  if (left) left.textContent = "Recovery charge";
  if (right) right.textContent = `${Math.round(rec)}%`;
  if (note) note.textContent = derived;
}

// ---------- Physiology grid (Today's Read right column) ----------
// HRV / RHR / Respiratory Rate are real Polar fields. Skin Temp + SpO2 are NOT
// in Alfie's Polar device feed (confirmed Step 0) — rendered as em-dash + muted
// "not tracked", never faked (LPI v1 Known Risks).
async function renderPhysiology() {
  const grid = document.getElementById("physiology-grid");
  if (!grid) return;
  let hrv = null, hrvDelta = null, rhr = null, rhrDelta = null, resp = null;
  try {
    const manifest = await fetchJSON("polar/manifest.json");
    const recDates = ((manifest.categories || {}).recharge || []).slice().sort();
    const recDate = recDates.at(-1);
    if (recDate && (daysSinceDate(recDate) ?? 99) <= 2) {
      const rec = await fetchJSON(`polar/recharge/${recDate}.json`).catch(() => null);
      if (rec) {
        hrv = rec.heart_rate_variability_avg ?? null;
        rhr = rec.heart_rate_avg ?? null;
        resp = rec.breathing_rate_avg ?? null;
      }
    }
    // Deltas from the LSI physiology block (HRV % vs baseline, RHR Δbpm).
    const lunar = await fetchJSON("polar/lunar_stress.json").catch(() => null);
    if (lunar?.physiology) {
      if (lunar.physiology.hrv_pct_baseline != null) hrvDelta = lunar.physiology.hrv_pct_baseline;
      if (lunar.physiology.rhr_delta_bpm != null) rhrDelta = lunar.physiology.rhr_delta_bpm;
    }
  } catch (e) { /* file:// / no sync → all em-dash */ }

  const cell = (label, value, unit, delta, deltaSuffix, color, goodIsUp) => {
    let deltaHTML = "";
    if (delta != null && delta !== 0) {
      const up = delta > 0;
      const good = goodIsUp ? up : !up;
      const dcolor = good ? "#39D98A" : "#FF8A3D";
      deltaHTML = `<span class="text-[11px] font-medium" style="color:${dcolor}">${up ? "▲" : "▼"} ${Math.abs(delta)}${deltaSuffix}</span>`;
    }
    const valHTML = value != null
      ? `<span class="text-xl font-semibold stat-num" style="color:${color}">${value}</span><span class="text-xs text-muted">${unit}</span>`
      : `<span class="text-xl font-semibold stat-num text-muted">—</span>`;
    const muted = value == null ? ' <span class="text-[10px] text-muted/70">not tracked</span>' : "";
    return `<div class="bg-bg rounded-lg p-3 border border-line">
      <div class="text-[11px] uppercase tracking-wider text-muted">${label}${muted}</div>
      <div class="mt-1 flex items-baseline gap-1.5 flex-wrap">${valHTML}${deltaHTML}</div>
    </div>`;
  };

  grid.innerHTML =
    cell("HRV", hrv, " ms", hrvDelta, "%", LPI.recovery, true) +
    cell("Resting HR", rhr, " bpm", rhrDelta, " bpm", LPI.sleep, false) +
    cell("Respiratory", resp, " /min", null, "", LPI.context, false) +
    cell("Skin Temp", null, "", null, "", LPI.activity, false) +
    cell("SpO₂", null, "", null, "", LPI.recovery, true);
}

// ---------- Supporting summary cards (Nutrition / Scale / Activity) ----------
// Compact glance cards that each tap through to their detail section below. Read
// the same JSON the detail sections read — never a divergent source.
async function renderSupportCards() {
  // Nutrition — most recent logged day (probe back 8 days, like renderNutrition).
  try {
    let n = null;
    for (const day of lastN(8).slice().reverse()) {
      try { n = await fetchJSON(`nutrition/daily/${day}.json`); if (!n.date) n.date = day; break; } catch {}
    }
    const valEl = document.getElementById("sc-nutrition-val");
    const detEl = document.getElementById("sc-nutrition-detail");
    if (n && valEl) {
      const t = n.totals || {}, g = n.goals || {};
      valEl.textContent = t.calories != null ? `${Math.round(t.calories).toLocaleString()} cal` : "—";
      const bits = [];
      if (g.calories != null && t.calories != null) bits.push(`${Math.max(0, Math.round(g.calories - t.calories))} left`);
      if (t.protein_g != null && g.protein_g != null) bits.push(`Protein ${Math.round(t.protein_g)}/${Math.round(g.protein_g)}g`);
      if (detEl) detEl.textContent = bits.join(" · ");
    }
  } catch (e) {}

  // Scale — latest VeSync snapshot.
  try {
    const s = await fetchJSON("vesync/snapshot.json");
    const valEl = document.getElementById("sc-scale-val");
    const detEl = document.getElementById("sc-scale-detail");
    if (valEl) valEl.textContent = s.weight_lb != null ? `${fmt(s.weight_lb, 1)} lb` : "—";
    const bits = [];
    if (s.body_fat_pct != null) bits.push(`BF ${fmt(s.body_fat_pct, 1)}%`);
    if (s.muscle_mass_lb != null) bits.push(`Muscle ${fmt(s.muscle_mass_lb, 1)}`);
    if (detEl) detEl.textContent = bits.join(" · ");
  } catch (e) {}

  // Activity — latest Polar daily activity.
  try {
    const manifest = await fetchJSON("polar/manifest.json");
    const dates = ((manifest.categories || {}).daily_activity || []).slice().sort();
    const latest = dates.at(-1);
    const a = latest ? await fetchJSON(`polar/daily_activity/${latest}.json`).catch(() => null) : null;
    const valEl = document.getElementById("sc-activity-val");
    const detEl = document.getElementById("sc-activity-detail");
    if (a && valEl) {
      const steps = a["active-steps"] ?? a.step_count ?? null;
      valEl.textContent = steps != null ? `${Number(steps).toLocaleString()} steps` : "—";
      const bits = [];
      const hm = isoDurationToHM(a.duration) || isoDurationToHM(a["active-time"]);
      if (hm) bits.push(`${hm} active`);
      if (a.calories != null) bits.push(`${Number(a.calories).toLocaleString()} cal`);
      if (detEl) detEl.textContent = bits.join(" · ");
    }
  } catch (e) {}
}

// Tap-through: hero metric corners + bottom-nav anchors scroll to their section.
function scrollToId(id) {
  const t = document.getElementById(id);
  if (t) t.scrollIntoView({ behavior: "smooth", block: "start" });
}
function wireRings() {
  document.querySelectorAll(".ring-corner[data-target]").forEach(btn => {
    btn.addEventListener("click", () => scrollToId(btn.dataset.target));
  });
  // Bottom nav. Dashboard/History/Insights scroll to anchors; Add + Settings are
  // visual placeholders for v1 (no-op) — flagged in LPI v1 Known Risks.
  const navTargets = { dashboard: "lpi-hero", history: "scale-history-panel", insights: "lunar-stress" };
  document.querySelectorAll("#lpi-bottom-nav button[data-nav]").forEach(btn => {
    btn.addEventListener("click", () => {
      const t = navTargets[btn.dataset.nav];
      if (t === "lpi-hero") window.scrollTo({ top: 0, behavior: "smooth" });
      else if (t) scrollToId(t);
    });
  });
}

// Block A — vertical stack of 6-dot Nightly Recharge rows (newest on top).
// `days` is pre-filtered to nights with data, so every row renders dots.
function renderRechargeStack(days, recMap) {
  const title = document.getElementById("polar-recharge-title");
  if (title) title.textContent = `Nightly Recharge · last ${days.length} night${days.length === 1 ? "" : "s"} with data`;
  const rows = days.slice().reverse().map(d => {
    const st = recMap[d]?.ans_charge_status ?? 0;
    const cells = Array.from({ length: 6 }, (_, i) => i < st
      ? `<span class="inline-block w-3 h-3 rounded-full" style="background:#06B6D4"></span>`
      : `<span class="inline-block w-3 h-3 rounded-full bg-card border border-line"></span>`).join("");
    return `<div class="flex items-center gap-2">
      <span class="text-xs text-muted w-12 shrink-0">${labelMD(d)}</span>
      <span class="flex items-center gap-1">${cells}</span>
    </div>`;
  });
  document.getElementById("polar-recharge-stack").innerHTML = rows.join("");
}

// Least-squares trend over the rendered nights-with-data window.
// `totalWithData` = how many qualifying nights exist in the last 90 days, used
// only to surface a "band not worn other nights" note when fewer than 10.
function renderRechargeTrend(days, recMap, totalWithData) {
  const el = document.getElementById("polar-recharge-trend");
  const note = document.getElementById("polar-recharge-note");
  const pts = [];
  days.forEach((d, i) => { const st = recMap[d]?.ans_charge_status; if (st != null) pts.push([i, st]); });
  if (pts.length < 2) {
    el.textContent = "";
  } else {
    const n = pts.length;
    const sx = pts.reduce((a, p) => a + p[0], 0), sy = pts.reduce((a, p) => a + p[1], 0);
    const sxx = pts.reduce((a, p) => a + p[0] * p[0], 0), sxy = pts.reduce((a, p) => a + p[0] * p[1], 0);
    const denom = n * sxx - sx * sx;
    if (!denom) { el.textContent = ""; }
    else {
      const slope = (n * sxy - sx * sy) / denom;
      // Change across the OBSERVED range — honest on a 1–6 scale. Clamp to span.
      const observed = pts.at(-1)[0] - pts[0][0];
      let change = Math.max(-5, Math.min(5, Math.round(slope * observed)));
      const arrow = change > 0 ? "↑" : change < 0 ? "↓" : "→";
      el.textContent = `trending: ${arrow} ${change > 0 ? "+" : ""}${change} over ${days.length} night${days.length === 1 ? "" : "s"} with data`;
    }
  }
  if (note) {
    note.textContent = (totalWithData != null && totalWithData < 10)
      ? `Only ${totalWithData} night${totalWithData === 1 ? "" : "s"} with data in the last 90 days · band not worn other nights.`
      : "";
  }
}

// Block B — sleep stage bar for the most recent date with sleep data (unchanged pattern).
function renderPolarSleep(sleep) {
  const wrap = document.getElementById("polar-sleep-wrap");
  if (!wrap) return;
  const light = sleep?.light_sleep || 0, deep = sleep?.deep_sleep || 0, rem = sleep?.rem_sleep || 0;
  const total = light + deep + rem;
  if (!total) { wrap.innerHTML = ""; return; }
  const pct = s => (s / total * 100).toFixed(1) + "%";
  wrap.innerHTML = `
    <h3 class="text-sm font-medium text-cobalt/80 mb-2">Sleep stages · ${labelMD(sleep.date)}</h3>
    <div class="stage-bar">
      <div style="width:${pct(deep)};background:#0891B2" title="Deep ${secsToHM(deep)}"></div>
      <div style="width:${pct(light)};background:#06B6D4" title="Light ${secsToHM(light)}"></div>
      <div style="width:${pct(rem)};background:#67E8F9" title="REM ${secsToHM(rem)}"></div>
    </div>
    <div class="flex flex-wrap gap-4 text-xs text-muted mt-2">
      <span><span class="inline-block w-2 h-2 rounded-full align-middle" style="background:#0891B2"></span> Deep ${secsToHM(deep)}</span>
      <span><span class="inline-block w-2 h-2 rounded-full align-middle" style="background:#06B6D4"></span> Light ${secsToHM(light)}</span>
      <span><span class="inline-block w-2 h-2 rounded-full align-middle" style="background:#67E8F9"></span> REM ${secsToHM(rem)}</span>
    </div>`;
}

// Block C — HRV big number + inline 7-day SVG sparkline + 7d avg/delta.
function renderHRV(recDates, recMap) {
  const numEl = document.getElementById("polar-hrv-num");
  const sparkEl = document.getElementById("polar-hrv-spark");
  const subEl = document.getElementById("polar-hrv-sub");
  const hrvs = recDates.map(d => recMap[d]?.heart_rate_variability_avg).filter(v => v != null);
  if (!hrvs.length) { numEl.textContent = "—"; sparkEl.innerHTML = ""; subEl.textContent = ""; return; }

  numEl.innerHTML = `${hrvs.at(-1)} <span class="text-base text-muted font-normal">ms</span>`;
  const last7 = hrvs.slice(-7), prior7 = hrvs.slice(-14, -7);
  sparkEl.innerHTML = sparkline(last7);

  const avg = a => a.reduce((x, y) => x + y, 0) / a.length;
  let sub = `7-day avg ${Math.round(avg(last7))} ms`;
  if (prior7.length) {
    const d = Math.round(avg(last7) - avg(prior7));
    sub += ` · ${d > 0 ? "↑" : d < 0 ? "↓" : "="} ${Math.abs(d)} vs prior 7d`;
  }
  subEl.textContent = sub;
}

// Inline SVG sparkline — 100×24 viewBox, normalized polyline, stroke=currentColor.
function sparkline(vals) {
  if (vals.length < 2) return "";
  const w = 100, h = 24, pad = 2, min = Math.min(...vals), max = Math.max(...vals), span = max - min || 1;
  const pts = vals.map((v, i) => {
    const x = (i / (vals.length - 1)) * (w - pad * 2) + pad;
    const y = h - pad - ((v - min) / span) * (h - pad * 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  return `<svg viewBox="0 0 ${w} ${h}" width="100%" height="24" preserveAspectRatio="none" fill="none"><polyline points="${pts}" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
}

// Plain-English Today's read — renders the `simple` block from summary.py.
// No raw numbers, units, biometric labels, or astrology jargon (enforced in the
// prompt). Recovery is a color-coded single word; Transit Impact only shows when
// a real transit is hitting.
// Concept 02 semantic recovery-word colors + same-hue glow. Ascending state:
// poor(coral)→average(amber)→good(cyan)→excellent(green).
const RECOVERY_COLORS = {
  poor: "text-coral glow-coral",       // coral — depleted / recovery risk
  average: "text-amber glow-amber",    // amber — caution
  good: "text-cyan glow-cyan",         // cyan — restored (recovery good)
  excellent: "text-green glow-green",  // green — peak recovery / performance-ready
};
// "Wind down" / "Rest day" are evening / off verdicts (sleep prep / day's-done
// framing — metadata, not a performance state); the others are daytime training
// calls. All are bolded by renderTodaysRead(), and the verdict word itself is
// colored by meaning: green = push/improve, cyan = recovery-is-good, amber =
// caution, gray = neutral non-state. Longer phrases first so startsWith() wins.
const PERF_VERDICTS = ["Push hard", "Train normally", "Moderate effort", "Prioritize recovery", "Wind down", "Rest day"];
// Concept 02 semantic verdict palette — a green→cyan→amber→coral severity
// gradient by physiological state, with neutral grays for the non-state
// evening/off verdicts. Each carries a same-hue glow.
const PERF_VERDICT_COLORS = {
  "Push hard":          "text-green glow-green",   // green — excellent state, go for output
  "Train normally":     "text-cyan glow-cyan",     // cyan — good readiness
  "Moderate effort":    "text-amber glow-amber",   // amber — caution / moderate
  "Prioritize recovery":"text-coral glow-coral",   // coral — poor recovery, back off
  "Wind down":          "text-muted",              // muted — evening, no state
  "Rest day":           "text-muted",              // muted — day's done, no state
};

// Short paragraph block with a small uppercase subtitle.
function readBlock(subtitle, text) {
  const sec = document.createElement("div");
  if (subtitle) {
    const h = document.createElement("div");
    h.className = "text-xs uppercase tracking-wider text-muted mb-1";
    h.textContent = subtitle;
    sec.appendChild(h);
  }
  const p = document.createElement("p");
  p.className = "text-base leading-relaxed text-neutral-200";
  p.style.fontSize = "15px";
  p.textContent = text;
  sec.appendChild(p);
  return sec;
}

async function renderTodaysRead() {
  const ts = document.getElementById("read-ts");
  const body = document.getElementById("read-body");
  const basis = document.getElementById("read-basis");
  if (!body) return;
  const clearWrap = () => { const p = document.getElementById("read-sections"); if (p) p.remove(); };
  try {
    const s = await fetchJSON("polar/summary.json");
    clearWrap();
    const simple = s.simple || null;
    const hasSimple = simple && (simple.recovery || simple.reading || simple.performance);
    if (hasSimple) {
      body.textContent = "";
      body.style.display = "none";
      const wrap = document.createElement("div");
      wrap.id = "read-sections";
      wrap.className = "space-y-4";

      // Recovery — color-coded single word at top.
      if (simple.recovery) {
        const word = String(simple.recovery).trim();
        const colorCls = RECOVERY_COLORS[word.toLowerCase()] || "text-slate-200";
        const badge = document.createElement("div");
        badge.className = "flex items-center gap-2";
        const lbl = document.createElement("span");
        lbl.className = "text-xs uppercase tracking-wider text-muted";
        lbl.textContent = "Recovery";
        const val = document.createElement("span");
        val.className = `text-2xl font-semibold ${colorCls}`;
        val.textContent = word;
        badge.appendChild(lbl);
        badge.appendChild(val);
        wrap.appendChild(badge);
      }

      // Reading — single flowing paragraph fusing physical + astrology texture.
      // No section label: the Recovery badge is the only "header" element.
      if (simple.reading)
        wrap.appendChild(readBlock(null, simple.reading));

      // Performance — inline bold "Performance:" prefix + bolded leading verdict.
      if (simple.performance) {
        const sec = document.createElement("div");
        const p = document.createElement("p");
        p.className = "text-base leading-relaxed text-neutral-200";
        p.style.fontSize = "15px";
        const lead = document.createElement("strong");
        lead.className = "text-neutral-200";
        lead.textContent = "Performance: ";
        p.appendChild(lead);
        const t = String(simple.performance).trim();
        const v = PERF_VERDICTS.find(v => t.toLowerCase().startsWith(v.toLowerCase()));
        if (v) {
          const strong = document.createElement("strong");
          strong.className = PERF_VERDICT_COLORS[v] || "text-neutral-200";
          strong.textContent = t.slice(0, v.length);
          p.appendChild(strong);
          p.appendChild(document.createTextNode(t.slice(v.length)));
        } else {
          p.appendChild(document.createTextNode(t));
        }
        sec.appendChild(p);
        wrap.appendChild(sec);
      }

      // Transit — only when a real transit is hitting (non-null/non-empty).
      if (simple.transit && String(simple.transit).trim())
        wrap.appendChild(readBlock(null, simple.transit));

      body.parentNode.insertBefore(wrap, body.nextSibling);
    } else {
      // No `simple` block (legacy summary.json) — fall back to the flat read.
      body.style.display = "";
      body.textContent = s.summary || "First read drops at 9:05 AM";
    }
    if (ts && s.generated_at) {
      const t = new Date(s.generated_at);
      ts.textContent = "updated " + t.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
    }
    if (basis) {
      // Trimmed footer: just freshness ("Today · YYYY-MM-DD"), no raw metrics.
      const dataDate = (s.generated_at || "").slice(0, 10);
      basis.innerHTML = dataDate ? freshnessHTML(dataDate, "wear the watch") : "";
    }
  } catch (e) {
    clearWrap();
    body.style.display = "";
    body.textContent = "First read drops at 9:05 AM";   // file missing / file://
    if (ts) ts.textContent = "";
    if (basis) basis.textContent = "";
  }
}

// ---------- Lunar tracker (polar/lunar_stress.py `lunar` block) ----------
// Direct-data reframe (2026-06-03): the card is now a pure lunar readout — moon
// sign + degree, phase, next sign change, void-of-course window, active major
// transits. No band labels, no score, no contribution bars, no behavioral
// directive (those still compute inside lunar_stress.json for trend math + the
// daily pattern log, but they are no longer the surface). Color tokens: gray for
// metadata, amber (text-warn) when void-of-course is active or Mercury is retro.
// LPI v1 (2026-06-04): the card REVERTS to score framing per Alfie's spec — the
// internal `score` (always computed in lunar_stress.json, hidden by the 06-03
// reframe) is resurfaced as a band + a 0–10 index, with the moon sign/degree/
// phase/next-change/void readout kept accessible directly underneath. The raw
// `score` is an OPEN-ENDED points total (transit cap 55 + body cap 40 = 95), so
// the X/10 shown is score normalized onto a 10-point scale, NOT the raw score.
function lsiIndex10(d) {
  const maxTotal = ((d.bars?.transit?.max) || 0) + ((d.bars?.body?.max) || 0);
  if (!maxTotal || d.score == null) return null;
  return Math.max(0, Math.min(10, Math.round((d.score / maxTotal) * 10)));
}
async function renderLunarStress() {
  const empty = document.getElementById("lsi-empty");
  const content = document.getElementById("lsi-content");
  if (!content) return;
  let d;
  try {
    d = await fetchJSON("polar/lunar_stress.json");
  } catch (e) {
    if (empty) empty.classList.remove("hidden");
    content.classList.add("hidden");
    return;
  }
  if (empty) empty.classList.add("hidden");
  content.classList.remove("hidden");

  const L = d.lunar || {};
  const voc = L.void_of_course;
  const transits = L.active_transits || [];
  const isRetro = t => /mercury\s+retrograde/i.test(t);

  // --- Score header: "{idx}/10" + band ---
  const idx = lsiIndex10(d);
  const scoreEl = document.getElementById("lsi-score");
  if (scoreEl) scoreEl.textContent = idx != null ? `${idx}/10` : (d.score != null ? `${d.score}` : "—");
  const bandEl = document.getElementById("lsi-band");
  if (bandEl) bandEl.textContent = d.band || "";
  const trigEl = document.getElementById("lsi-trigger");
  if (trigEl) trigEl.textContent = d.trigger ? `Driver: ${d.trigger}` : "";

  // --- Moon details (kept accessible per spec) ---
  const row = (label, value, amber) => {
    if (!value) return "";
    return `<div class="flex gap-2 text-sm leading-relaxed">` +
      `<span class="text-muted w-28 shrink-0">${label}</span>` +
      `<span class="${amber ? "text-warn font-medium" : "text-neutral-200"}">${value}</span></div>`;
  };
  let rows = "";
  rows += row("Moon", L.sign ? `${L.sign}${L.degree ? ` · ${L.degree}` : ""}` : "");
  rows += row("Phase", L.phase);
  rows += row("Next sign", L.next_sign_change && L.next_sign_change.display);
  if (voc && voc.active) rows += row("Void of Course", `now through ${voc.until_display || "next ingress"}`, true);
  if (transits.length) rows += transits.map((t, i) => row(i === 0 ? "Transits" : "", t, isRetro(t))).join("");
  const rowsEl = document.getElementById("lsi-detail-rows");
  if (rowsEl) rowsEl.innerHTML = rows;

  // --- Recommendation ---
  const recEl = document.getElementById("lsi-recommendation");
  if (recEl) recEl.textContent = d.recommendation || "";

  // Timestamp + freshness (lunar position drifts; flag >2h old, amber stamp).
  const ts = document.getElementById("lsi-ts");
  if (ts && d.generated_at) {
    const t = new Date(d.generated_at);
    const ageH = (Date.now() - t.getTime()) / 3600000;
    ts.textContent = (ageH > 2 ? "⚠️ " : "") + "updated " +
      t.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
    ts.className = ageH > 2 ? "text-xs text-warn font-medium" : "text-xs text-neutral-400";
  }
}

// ---------- Nutrition (Calories Club macros via nutrition/sync.py) ----------
async function renderNutrition() {
  const empty = document.getElementById("nutrition-empty");
  const content = document.getElementById("nutrition-content");
  if (!content) return;
  // No nutrition manifest — probe today back 7 days for the most recent logged day.
  let n = null;
  for (const day of lastN(8).slice().reverse()) {
    try { n = await fetchJSON(`nutrition/daily/${day}.json`); if (!n.date) n.date = day; break; } catch {}
  }
  try {
    if (!n) throw new Error("no nutrition days");
    const t = n.totals || {};
    const g = n.goals || {};
    const macros = [
      { label: "Calories", key: "calories", goal: g.calories, unit: "" },
      { label: "Protein", key: "protein_g", goal: g.protein_g, unit: "g" },
      { label: "Carbs", key: "carbs_g", goal: g.carbs_g, unit: "g" },
      { label: "Fat", key: "fat_g", goal: g.fat_g, unit: "g" },
    ];
    content.innerHTML = macros.map(m => {
      const val = t[m.key];
      const valTxt = val != null ? Math.round(val) + m.unit : "—";
      const goalTxt = m.goal != null ? `/ ${Math.round(m.goal)}${m.unit} goal` : "";
      const pct = (val != null && m.goal) ? Math.min(100, Math.round((val / m.goal) * 100)) : null;
      const bar = pct != null
        ? `<div class="h-1.5 bg-neutral-800 rounded-full mt-2 overflow-hidden"><div class="h-full bg-accent/80" style="width:${pct}%"></div></div>`
        : "";
      return `<div class="bg-bg rounded-lg p-3 border border-line">
        <div class="text-xs text-muted">${m.label}</div>
        <div class="text-2xl font-semibold stat-num mt-1">${valTxt}</div>
        <div class="text-xs text-muted mt-1">${goalTxt}</div>${bar}
      </div>`;
    }).join("");
    empty.classList.add("hidden");
    content.classList.remove("hidden");
    const sub = document.getElementById("nutrition-sub");
    if (sub) sub.innerHTML = freshnessHTML(n.date, "log meals");
  } catch (e) {
    empty.classList.remove("hidden");
    content.classList.add("hidden");
  }
}

// ---------- Nutrition nudge (single-line, time-aware; polar/summary.py) ----------
// Sits directly under the Nutrition card. Reads summary.json.nutrition_nudge —
// shows the line with an arrow cue, or hides itself when empty (off-clock / no data).
async function renderNutritionNudge() {
  const el = document.getElementById("nutrition-nudge");
  if (!el) return;
  try {
    const s = await fetchJSON("polar/summary.json");
    const nudge = (s.nutrition_nudge || "").trim();
    if (nudge) {
      el.textContent = "→ " + nudge;
      el.classList.remove("hidden");
    } else {
      el.textContent = "";
      el.classList.add("hidden");
    }
  } catch (e) {
    el.textContent = "";
    el.classList.add("hidden");
  }
}

// ---------- Latest scale snapshot (VeSync ESF-551 screenshot OCR via Penny) ----------
// Reads vesync/snapshot.json — manually OCR'd from a screenshot since the BT-only
// ESF-551 has no body-comp cloud API. Missing file or all-null values → empty state.
function formatSnapshotTS(iso) {
  // Format the captured timestamp WITHOUT timezone math (it's already Central):
  // "2026-06-01T12:30:00-05:00" → "2026-06-01 ~12:30 PM".
  const m = /^(\d{4}-\d{2}-\d{2})T(\d{2}):(\d{2})/.exec(iso || "");
  if (!m) return iso || "";
  const [, date, hhStr, mm] = m;
  let hh = parseInt(hhStr, 10);
  const ampm = hh >= 12 ? "PM" : "AM";
  hh = hh % 12 || 12;
  return `${date} ~${hh}:${mm} ${ampm}`;
}

async function renderScaleSnapshot() {
  const empty = document.getElementById("snapshot-empty");
  const content = document.getElementById("snapshot-content");
  const sub = document.getElementById("snapshot-sub");
  if (!empty || !content) return;
  const showEmpty = () => {
    empty.classList.remove("hidden"); content.classList.add("hidden");
    if (sub) sub.textContent = "";
  };
  try {
    const s = await fetchJSON("vesync/snapshot.json");
    const tiles = [
      { label: "Weight",       value: s.weight_lb,           unit: " lbs", d: 1 },
      { label: "Body fat",     value: s.body_fat_pct,        unit: "%",    d: 1 },
      { label: "Muscle",       value: s.muscle_mass_lb,      unit: " lbs", d: 1 },
      { label: "Body water",   value: s.body_water_pct,      unit: "%",    d: 1 },
      { label: "BMR",          value: s.bmr_cal,             unit: " cal", d: 0 },
      { label: "Visceral fat", value: s.visceral_fat_rating, unit: "",     d: 0 },
    ];
    if (!tiles.some(t => t.value != null)) return showEmpty(); // nothing parsed yet
    content.innerHTML = tiles.map(t => `
      <div class="bg-bg rounded-lg p-3 border border-line">
        <div class="text-xs uppercase tracking-wider text-muted">${t.label}</div>
        <div class="text-xl font-semibold stat-num mt-1">${t.value != null ? fmt(t.value, t.d) + t.unit : "—"}</div>
      </div>`).join("");
    empty.classList.add("hidden");
    content.classList.remove("hidden");
    if (sub) sub.textContent = s.captured_at ? "Last update: " + formatSnapshotTS(s.captured_at) : "";
  } catch (e) {
    showEmpty(); // file missing / file://
  }
}

// ---------- Day in review (nightly freeze via polar/summary.py 9:45 PM fire) ----------
// Reads polar/day_review.json — frozen once nightly: the day's stats + a single
// color-coded verdict + an AI plain-English wrap-up. Read next morning until the
// next night's fire overwrites it. Empty state before the first fire; amber stale
// warning if the frozen date is from more than a day ago.
const DAY_REVIEW_BADGES = {
  easy:  { label: "Easy day",  cls: "text-cyan bg-cyan/15" },    // cyan — recovered / low strain
  solid: { label: "Solid day", cls: "text-green bg-green/15" },  // green — good performance
  great: { label: "Great day", cls: "text-coral bg-coral/15" }, // coral — peak output / high effort
  big:   { label: "Big day",   cls: "text-amber bg-amber/15" }, // amber — heavy load / big volume
};

async function renderDayReview() {
  const empty = document.getElementById("day-review-empty");
  const content = document.getElementById("day-review-content");
  if (!empty || !content) return;
  const showEmpty = () => {
    empty.classList.remove("hidden"); content.classList.add("hidden");
    const sub = document.getElementById("day-review-sub"); if (sub) sub.textContent = "";
    const dl = document.getElementById("day-review-date"); if (dl) dl.textContent = "";
  };
  try {
    const r = await fetchJSON("polar/day_review.json");
    const s = r.stats || {};

    // Header date — "· Mon, Jun 1" from the frozen date.
    const dl = document.getElementById("day-review-date");
    if (dl && r.date) {
      const dObj = new Date(r.date + "T00:00:00");
      dl.textContent = "· " + dObj.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
    }

    // Verdict badge — single color-coded label.
    const v = String(r.verdict || "").trim().toLowerCase();
    const badge = DAY_REVIEW_BADGES[v] || { label: r.verdict || "—", cls: "text-slate-300 bg-slate-800" };
    document.getElementById("day-review-badge").innerHTML =
      `<span class="inline-block text-sm font-semibold px-3 py-1 rounded-full ${badge.cls}">${badge.label}</span>`;

    // Stats line — plain numbers, no jargon. Each piece only if present.
    const nf = n => Number(n).toLocaleString();
    const lines = [];
    const l1 = [];
    if (s.steps != null) l1.push(`${nf(s.steps)} steps`);
    if (s.active_time_display && s.active_time_display !== "—") l1.push(`${s.active_time_display} active`);
    if (s.calories_burned != null) l1.push(`${nf(s.calories_burned)} cal burned`);
    if (l1.length) lines.push(l1.join(" · "));
    if (s.calories_eaten != null) {
      let l2 = `Ate ${nf(s.calories_eaten)}`;
      if (s.net_deficit != null) {
        l2 += s.net_deficit > 0 ? ` · net deficit of ${nf(s.net_deficit)}`
            : s.net_deficit < 0 ? ` · net surplus of ${nf(Math.abs(s.net_deficit))}`
            : ` · even with what you burned`;
      }
      lines.push(l2);
    }
    if (s.protein_g != null) {
      let l3 = `Protein ${nf(s.protein_g)}g`;
      if (s.protein_gap_g != null && s.protein_target_g != null) {
        l3 += s.protein_gap_g > 0
          ? ` (${nf(s.protein_gap_g)}g short of ${nf(s.protein_target_g)}g target)`
          : ` (hit ${nf(s.protein_target_g)}g target)`;
      }
      lines.push(l3);
    }
    document.getElementById("day-review-stats").innerHTML = lines.join("<br>");

    // AI prose.
    const proseEl = document.getElementById("day-review-prose");
    proseEl.textContent = r.prose || "";
    proseEl.style.display = r.prose ? "" : "none";

    // Subtitle — frozen time + stale warning if the date is >1 day old.
    const sub = document.getElementById("day-review-sub");
    const age = daysSinceDate(r.date);
    if (sub) {
      if (age != null && age > 1) {
        sub.innerHTML = `<span class="text-warn font-medium">⚠️ ${age} days old — last frozen ${r.date}</span>`;
      } else if (r.generated_at) {
        const t = new Date(r.generated_at);
        sub.textContent = "frozen " + t.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
      } else {
        sub.textContent = "";
      }
    }

    empty.classList.add("hidden");
    content.classList.remove("hidden");
  } catch (e) {
    showEmpty(); // file missing (before first 9:45 PM fire) / file://
  }
}

// ---------- Scale history (VeSync ESF-551 manual screenshot readings) ----------
// Reads vesync/history.json — array of readings, newest first. Compact table,
// no charts (per dashboard convention). Missing file / file:// → empty state.
function fmtDelta(d) {
  if (d == null || isNaN(d)) return "—";
  const n = Number(d);
  const sign = n > 0 ? "+" : "";
  const cls = n > 0 ? "text-warn" : n < 0 ? "text-good" : "text-muted";
  return `<span class="${cls}">${sign}${n.toFixed(1)}</span>`;
}

async function renderScaleHistory() {
  const empty = document.getElementById("scale-history-empty");
  const content = document.getElementById("scale-history-content");
  const rows = document.getElementById("scale-history-rows");
  const sub = document.getElementById("scale-history-sub");
  const caption = document.getElementById("scale-history-caption");
  if (!empty || !content || !rows) return;
  const showEmpty = () => {
    empty.classList.remove("hidden"); content.classList.add("hidden");
    if (sub) sub.textContent = "";
    if (caption) caption.textContent = "";
  };
  try {
    const hist = await fetchJSON("vesync/history.json");
    if (!Array.isArray(hist) || hist.length === 0) return showEmpty();
    const sorted = [...hist].sort((a, b) => (a.date < b.date ? 1 : -1)); // newest first
    rows.innerHTML = sorted.map(r => `
      <tr class="border-b border-line/50">
        <td class="py-2 pr-2 text-neutral-200">${r.date}</td>
        <td class="py-2 px-2 text-right">${fmt(r.weight_lb, 1)}</td>
        <td class="py-2 px-2 text-right">${fmtDelta(r.delta_lb)}</td>
        <td class="py-2 px-2 text-right">${r.body_fat_pct != null ? fmt(r.body_fat_pct, 1) + "%" : "—"}</td>
        <td class="py-2 px-2 text-right">${fmt(r.muscle_mass_lb, 1)}</td>
        <td class="py-2 pl-2 text-right">${r.visceral_fat_rating != null ? r.visceral_fat_rating : "—"}</td>
      </tr>`).join("");
    empty.classList.add("hidden");
    content.classList.remove("hidden");
    if (sub) sub.textContent = `${sorted.length} reading${sorted.length === 1 ? "" : "s"}`;
    if (caption) caption.textContent =
      `${sorted.length} manual readings, Feb–May 2026 · BT scale doesn't auto-sync to API · next reading: send screenshot to Penny.`;
  } catch (e) {
    showEmpty(); // file missing / file://
  }
}

// ---------- Activity · today (Polar Loop Gen 2 daily activity via polar/sync.py) ----------
// Reads the daily_activity dates from polar/manifest.json + the latest per-day JSON
// written by sync.py. The AccessLink daily-activity *summary* payload exposes step
// count, active time (ISO8601 duration), active + total calories — but NOT a goal %
// or activity-zone breakdown. So the 3 tiles render from verified real fields, and
// the goal/zone footer renders only if a payload ever carries them (graceful);
// otherwise it shows active calories + an honest note that zones aren't in the feed.
function isoDurationToHM(iso) {
  // "PT2H16M" -> "2h 16m", "PT2M" -> "2m", "PT45S"/"PT0S" -> "0m"
  if (!iso || typeof iso !== "string") return null;
  const m = /^P(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$/.exec(iso);
  if (!m) return null;
  const h = +(m[1] || 0), min = +(m[2] || 0);
  if (h && min) return `${h}h ${min}m`;
  if (h) return `${h}h`;
  return `${min}m`;
}

// Relative "last synced" stamp for the Activity card, tied to polar/sync.py's
// 30-min cadence (manifest.synced_at). Gray (metadata) when fresh; flips amber
// (caution) past the 2-hour drift threshold — a soft "sync may be dead" signal
// complementary to the dashboard-wide staleness banner (WHEN_HOME #9).
function activitySyncStamp(syncedAtISO) {
  if (!syncedAtISO) return null;                 // old manifest, no timestamp yet
  const t = new Date(syncedAtISO).getTime();
  if (!isFinite(t)) return null;
  const mins = Math.max(0, Math.floor((Date.now() - t) / 60000)); // clamp clock skew
  if (mins >= 120) return { text: "Updated 2h+ ago", stale: true };
  if (mins >= 60)  return { text: `Updated ${Math.floor(mins / 60)} hr ago`, stale: false };
  if (mins >= 1)   return { text: `Updated ${mins} min ago`, stale: false };
  return { text: "Updated just now", stale: false };
}

async function renderActivity() {
  const empty = document.getElementById("activity-empty");
  const content = document.getElementById("activity-content");
  const sub = document.getElementById("activity-sub");
  if (!empty || !content) return;
  const showEmpty = () => {
    empty.classList.remove("hidden"); content.classList.add("hidden");
    if (sub) sub.textContent = "";
  };
  try {
    const manifest = await fetchJSON("polar/manifest.json");

    // "Updated N min ago" stamp from polar/sync.py's per-run manifest timestamp.
    const upd = document.getElementById("activity-updated");
    if (upd) {
      const stamp = activitySyncStamp(manifest.synced_at);
      upd.textContent = stamp ? stamp.text : "";
      upd.classList.toggle("text-coral", !!stamp && stamp.stale);  // coral past 2h drift
      upd.classList.toggle("text-muted", !stamp || !stamp.stale);  // muted blue-gray when fresh
    }

    const dates = ((manifest.categories || {}).daily_activity || []).slice().sort();
    if (!dates.length) return showEmpty();                       // no synced activity → empty
    const latest = dates.at(-1);
    const a = await fetchJSON(`polar/daily_activity/${latest}.json`).catch(() => null);
    if (!a) return showEmpty();                                   // file missing / file:// → empty
    const day = (a.date || latest).slice(0, 10);

    // --- 3 tiles: steps / active time / calories (fields verified from a real JSON) ---
    const steps = a["active-steps"] ?? a.step_count ?? null;
    const activeHM = isoDurationToHM(a.duration) || isoDurationToHM(a["active-time"]);
    const cal = a.calories ?? null;                               // total daily calories
    const tiles = [
      { label: "steps",       value: steps != null ? Number(steps).toLocaleString() : "—" },
      { label: "active time", value: activeHM || "—" },
      { label: "calories",    value: cal != null ? Number(cal).toLocaleString() : "—" },
    ];
    document.getElementById("activity-tiles").innerHTML = tiles.map(t => `
      <div class="bg-bg rounded-lg p-3 border border-line min-w-0">
        <div class="text-2xl font-semibold stat-num leading-tight truncate">${t.value}</div>
        <div class="text-xs text-muted mt-1">${t.label}</div>
      </div>`).join("");

    // --- footer: goal % + intensity-zone breakdown — only if the payload carries them ---
    const goal = a["daily-activity-goal-completion-percentage"]
      ?? a["activity-goal-completion"] ?? a["goal_percentage"] ?? a["goal-percentage"] ?? null;
    const z = {
      light:    a["light_activity_seconds"]    ?? a["light-activity-seconds"]    ?? null,
      moderate: a["moderate_activity_seconds"] ?? a["moderate-activity-seconds"] ?? null,
      vigorous: a["vigorous_activity_seconds"] ?? a["vigorous-activity-seconds"] ?? null,
    };
    const bits = [];
    if (goal != null) bits.push(`Goal: ${Math.round(goal)}%`);
    const compactHM = s => { const h = Math.floor(s / 3600), m = Math.round((s % 3600) / 60); return h ? `${h}h ${m}m` : `${m}m`; };
    const zoneTxt = ["light", "moderate", "vigorous"]
      .filter(k => z[k] != null)
      .map(k => `${k[0].toUpperCase()}${k.slice(1)} ${compactHM(z[k])}`).join(" · ");
    if (zoneTxt) bits.push(zoneTxt);
    if (!bits.length) {
      // Honest fallback — Loop Gen 2's daily-activity summary has no goal %/zones.
      const activeCal = a["active-calories"];
      if (activeCal != null) bits.push(`${Number(activeCal).toLocaleString()} active cal`);
      bits.push("goal % &amp; intensity zones aren't in the Loop Gen 2 daily-activity feed");
    }
    // Load band chip — the SAME loadBandFor() the Recovery tile's "Spent" line uses,
    // on the SAME active-calories value. The chip is the interpretation; "X active
    // cal" above is the raw figure. They are guaranteed consistent.
    const band = loadBandFor(a["active-calories"]);
    const bandChip = `<span class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-card border border-line">`
      + `<span class="inline-block w-2 h-2 rounded-full" style="background:${band.dot}"></span>Load: ${band.name}</span>`;
    document.getElementById("activity-footer").innerHTML =
      bandChip + "&nbsp;&nbsp;·&nbsp;&nbsp;" + bits.join("&nbsp;&nbsp;·&nbsp;&nbsp;");

    // --- subtitle: "Mon · Jun 1" when fresh, amber stale warning when >1 day old ---
    const dObj = new Date(day + "T00:00:00");
    const wd = dObj.toLocaleDateString("en-US", { weekday: "short" });
    const md = dObj.toLocaleDateString("en-US", { month: "short", day: "numeric" });
    const age = daysSinceDate(day);
    if (sub) {
      sub.innerHTML = (age != null && age > 1)
        ? `<span class="text-warn font-medium">⚠️ ${age} days stale · ${wd} · ${md}</span>`
        : `<span class="text-slate-300">${wd} · ${md}</span>`;
    }

    empty.classList.add("hidden");
    content.classList.remove("hidden");
  } catch (e) {
    showEmpty(); // file:// or no sync yet
  }
}

function renderAll() {
  renderTodaysRead(); // async, AI health summary
  renderLunarStress(); // async, Lunar Stress Index (polar/lunar_stress.py)
  renderNutrition(); // async, today's macros from Calories Club
  renderNutritionNudge(); // async, single-line time-aware nutrition nudge (summary.json)
  renderHeader();
  renderProfileStrip();
  renderScaleSnapshot(); // async, VeSync screenshot OCR snapshot (manual via Penny)
  renderScaleHistory(); // async, VeSync scale history table (manual via Penny)
  renderRings(); // async, LPI hero: moon + 3 orbital rings + metric corners + recovery window
  renderPhysiology(); // async, Today's Read physiology grid (HRV/RHR/Resp + em-dash Skin Temp/SpO2)
  renderSupportCards(); // async, Nutrition / Scale / Activity summary cards
  wireRings();   // tap-through scroll on metric corners + bottom nav
  renderActivity(); // async, Polar Loop Gen 2 daily activity (steps / active time / calories)
  renderPolar(); // async, live Polar Loop data
  renderDayReview(); // async, nightly Day-in-Review freeze (polar/day_review.json)
}

renderAll();
