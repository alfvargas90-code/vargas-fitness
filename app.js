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

// ---------- Polar Nightly Recharge component status words (1–6 ladder) ----------
// ans_charge_status, nightly_recharge_status, and sleep_charge all ride Polar's
// 1–6 qualitative scale. Index 0 / null is the no-data placeholder.
const POLAR_STATUS_WORD = ["—", "Very poor", "Poor", "Compromised", "OK", "Good", "Very good"];
const polarStatusWord = s => (s == null ? "—" : (POLAR_STATUS_WORD[s] || "—"));
// Status → semantic color (ascending red→amber→cyan→green), matching the dashboard
// recovery palette so the word's hue matches its meaning.
const POLAR_STATUS_COLOR = ["#8A90A6", "#FF5E62", "#FF5E62", "#FF8A3D", "#00C8FF", "#39D98A", "#39D98A"];
const polarStatusColor = s => (s == null ? "#8A90A6" : (POLAR_STATUS_COLOR[s] || "#8A90A6"));

// ---------- Last Synced badge (Now row) ----------
// Reads polar/manifest.json `synced_at` (ISO, rewritten every polar/sync.py run) and
// renders a relative "synced N ago" stamp + a freshness dot:
//   <30 min → green · 30 min–2 h → yellow · >2 h → red + ⚠ prefix.
// Pure client-side read; no pipeline touch. Tap re-fetches + re-renders (wireLastSynced).
function relSyncPhrase(mins) {
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const h = Math.floor(mins / 60), m = mins % 60;
  return m ? `${h} hr ${m} min ago` : `${h} hr ago`;
}
async function renderLastSynced() {
  const dot = document.getElementById("last-synced-dot");
  const txt = document.getElementById("last-synced-text");
  if (!txt) return;
  try {
    const manifest = await fetchJSON("polar/manifest.json");
    const t = manifest.synced_at ? new Date(manifest.synced_at).getTime() : NaN;
    if (!isFinite(t)) {
      txt.textContent = "sync time unknown"; txt.style.color = "#8A90A6";
      if (dot) { dot.style.background = "#8A90A6"; dot.style.boxShadow = "none"; }
      return;
    }
    const mins = Math.max(0, Math.floor((Date.now() - t) / 60000));  // clamp clock skew
    let color, warn = "";
    if (mins < 30)       color = "#39D98A";            // green — fresh
    else if (mins < 120) color = "#FFC400";            // yellow — aging
    else { color = "#FF5E62"; warn = "⚠ "; }           // red — stale
    if (dot) { dot.style.background = color; dot.style.boxShadow = `0 0 6px ${color}`; }
    txt.textContent = `${warn}synced ${relSyncPhrase(mins)}`;
    txt.style.color = color;
  } catch (e) {
    txt.textContent = "sync offline"; txt.style.color = "#8A90A6";
    if (dot) { dot.style.background = "#8A90A6"; dot.style.boxShadow = "none"; }
  }
}
// Tap-to-refresh — re-fetch the freshness + the live data renderers (no full
// renderAll, which would re-bind tap-through listeners). Bound once.
function wireLastSynced() {
  const btn = document.getElementById("last-synced");
  if (!btn || btn._wired) return;
  btn._wired = true;
  btn.addEventListener("click", () => {
    renderLastSynced();
    renderRings(); renderActivity(); renderPolar();
    renderSupportCards(); renderPhysiology(); renderTodaysRead(); renderCoach();
  });
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
  sub.textContent = date;
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

// Monthly Historical Card — reads ONE hardcoded month file (no auto-discovery yet,
// per Alfie's manual option B). Static data: fetched once on load, no polling. On any
// fetch/parse failure the card simply stays hidden (no throw, no break). No sport
// breakdown is rendered (hidden until Alfie provides the code map).
async function renderMonthlyHistory() {
  const card = document.getElementById("monthly-history-card");
  if (!card) return;
  try {
    const h = await fetchJSON("polar/history/2026-05.json");
    if (!h || !h.headlines) return; // malformed → stay hidden
    const hl = h.headlines;
    const set = (id, txt) => { const el = document.getElementById(id); if (el) el.textContent = txt; };
    set("mh-title", `${h.month} · ${h.year}`);
    set("mh-stats-1", `${hl.sessions} sessions · ${hl.active_days} active days`);
    set("mh-stats-2", `Sleep avg ${hl.sleep_avg} · top week ${hl.top_week_sessions}`);
    set("mh-recommendation", h.recommendation || "");
    card.classList.remove("hidden");                       // show the May sub-block
    document.getElementById("pattern-engine")?.classList.remove("hidden"); // May alone justifies the section
  } catch (e) {
    // fetch failed (e.g. file absent) → May sub-block + section stay hidden gracefully
  }
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

// Historical baseline (polar/baseline.json) — fetched ONCE on page load, memoized.
// Render functions `await loadBaseline()` to annotate "vs typical" deltas. Returns
// null on any failure, so displays render WITHOUT deltas (graceful = current behavior).
let _baselinePromise = null;
function loadBaseline() {
  if (!_baselinePromise) _baselinePromise = fetchJSON("polar/baseline.json").catch(() => null);
  return _baselinePromise;
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
    // recharge value (band worn), within the last 90 days — then take the 7 most
    // recent. No empty placeholder rows for nights the band wasn't worn.
    const cutoff90 = lastN(90)[0];
    const rechargeDays = recDates.filter(d => d >= cutoff90 && recMap[d]?.ans_charge_status != null);
    const window7 = rechargeDays.slice(-7);
    renderRechargeStack(window7, recMap);
    renderRechargeTrend(window7, recMap, rechargeDays.length);
    renderPolarSleep(sleepMap[sleepDates.at(-1)]);   // Block B — most recent date with sleep data
    renderHRV(recDates, recMap);
    renderRechargeDetail(recMap[recDates.at(-1)], sleepMap[sleepDates.at(-1)]); // ANS/Sleep/Nightly
    fillRecoveryHeader(recMap[recDates.at(-1)], sleepMap[sleepDates.at(-1)], recDates, recMap); // Recovery-tab 3-col header

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
function strainColor(pct) {           // Strain — graduated; RED ONLY near max load
  return pct < 30 ? "#7d84a8"   // muted metadata gray — low load, no urgency
       : pct < 60 ? "#FFBA00"   // gold — building (warm caution)
       : pct < 80 ? "#FF6B6B"   // coral — heavy load
       :            "#FF5E62";  // red — approaching max (the only red zone)
}
// Visual-PRESENCE color for the Strain ring glow + corner: same graduation as
// strainColor() except the low-load band floors to warm coral instead of cold gray,
// so a quiet morning still reads "coral, alive" and the corner keeps parity with the
// cyan Recovery / purple Sleep corners. Semantic logic (bands, labels) stays on
// strainColor(); this only governs the rendered hue.
function strainPresenceColor(pct) {
  const c = strainColor(pct);
  return c === "#7d84a8" ? "#FF8A7A" : c;   // floor: warm coral, not gray-zone
}

// Overnight recovery score — combines recharge + sleep + HRV vs an adaptive HRV
// baseline. Lifted verbatim from the deleted renderRecoveryTile so the Recovery
// ring stays data-honest. Each part falls back if its metric is missing.
function computeRecoveryScore(rec, sleep, hrvBaseline) {
  const rechargePart = rec?.ans_charge_status != null ? (rec.ans_charge_status / 6) * 50 : 25;
  const sleepPart    = sleep?.sleep_score > 0 ? (sleep.sleep_score / 100) * 30 : 15;
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

// LPI v1 replica — FLAT concentric gradient rings (matching the source mockup).
// viewBox is 0 0 260 260, center (130,130). Sleep innermost (purple), Recovery
// middle (cyan→blue), Strain outer (orange→red) + highest visual weight. Each
// ring = faint full track + bright gradient progress arc swept clockwise from
// 12 o'clock, with a same-hue glow. Measured from the mockup: moon r≈40, rings
// at r≈63/84/100, stroke ≈6px.
// Moon as VISUAL ANCHOR (2026-06-04): moonR +15% (40→46) so the body dominates;
// rings quieted ~20% (thinner stroke, lower arc opacity, subtler glow) so they
// support rather than compete. Three depth planes: moon (sharp, haloed) → rings
// (subtler) → background waves/particles (soft, receding).
const ORBIT = {
  cx: 130, cy: 130,
  moonR: 62,                 // was 40 → +15% (moon is now the anchor)
  rings: {                   // inside → out
    sleep:    { r: 76,  grad: "gSleep",  glow: "#8A5CFF" },
    recovery: { r: 90,  grad: "gRecov",  glow: "#00C8FF" },
    strain:   { r: 104, grad: "gStrain", glow: "#FF5E62" },
  },
  arcW: 6.5, baseW: 6.5,     // BOLD rings — match the mockup's prominent glowing orbits
  arcOpacity: 0.97,          // vivid arcs (mockup reads at near-full opacity)
  base: "rgba(255,255,255,0.028)", // (track now tints to each ring's hue — see orbitGroup)
};

// SVG <defs> — per-ring linear gradients tuned to the mockup's ring hues.
const ORBIT_DEFS = `<defs>
  <linearGradient id="gSleep" x1="0.15" y1="0" x2="0.85" y2="1">
    <stop offset="0" stop-color="#6E3FD6"/><stop offset="1" stop-color="#B58CFF"/>
  </linearGradient>
  <linearGradient id="gRecov" x1="0" y1="0.2" x2="1" y2="0.9">
    <stop offset="0" stop-color="#5CEBFF"/><stop offset="1" stop-color="#00B4FF"/>
  </linearGradient>
  <linearGradient id="gStrain" x1="0.1" y1="0" x2="0.95" y2="1">
    <stop offset="0" stop-color="#FF9A3D"/><stop offset="0.55" stop-color="#FF5E62"/><stop offset="1" stop-color="#FF2E55"/>
  </linearGradient>
</defs>`;

// One flat ring: faint full track + bright arc (clockwise from top). Pass a
// `solidColor` to override the gradient with a flat stroke+glow — used by the
// Strain ring so its hue can graduate with load (gray → gold → coral → red).
// `emphasis` boosts the bloom (halo opacity +50%, halo blur +25%, arc blur 7→10px)
// so the Strain ring reads "active, energetic, loaded" — equal visual weight to the
// cyan Recovery glow rather than the weaker coral it had before.
function orbitGroup(r, pct, gradId, glowColor, solidColor, emphasis) {
  const c = 2 * Math.PI * r;
  const arc = (Math.max(0, Math.min(100, pct || 0)) / 100) * c;
  // Full track tinted to the ring's own hue (low alpha + faint bloom) so all three
  // read as COMPLETE glowing orbits — the mockup look — while the bright arc on top
  // still encodes the metric value.
  const track = `<circle cx="130" cy="130" r="${r}" fill="none" stroke="#243056" stroke-opacity="0.55" stroke-width="${ORBIT.baseW}"/>`;
  if (!(pct > 0)) return track;
  const stroke = solidColor || `url(#${gradId})`;
  const glow = solidColor || glowColor;
  const dash = `stroke-dasharray="${arc.toFixed(2)} ${(c - arc).toFixed(2)}" transform="rotate(-90 130 130)"`;
  const haloOpacity = emphasis ? 0.34 : 0.28;   // restrained bloom — clean concentric rings
  const haloBlur    = emphasis ? 21 : 17;        // tighter halo, less inter-ring bleed
  const progBlur    = emphasis ? 15 : 12;         // crisp arc with soft glow
  // Soft color bleed — a wide, very low-alpha echo of the arc that lets each ring's
  // hue diffuse outward (cyan / coral / violet aura), separate from the tighter halo.
  const auraOpacity = emphasis ? 0.16 : 0.13;
  const auraBlur    = emphasis ? 33 : 27;
  const aura = `<circle cx="130" cy="130" r="${r}" fill="none" stroke="${glow}"
      stroke-width="${ORBIT.arcW + 8}" stroke-linecap="round" stroke-opacity="${auraOpacity}"
      ${dash} style="filter:drop-shadow(0 0 ${auraBlur}px ${glow})"/>`;
  // Outer bloom halo — a low-alpha, wide-blur echo of the arc so the ring reads
  // as energy emanating outward rather than a hard progress stroke.
  const halo = `<circle cx="130" cy="130" r="${r}" fill="none" stroke="${glow}"
      stroke-width="${ORBIT.arcW + 3}" stroke-linecap="round" stroke-opacity="${haloOpacity}"
      ${dash} style="filter:drop-shadow(0 0 ${haloBlur}px ${glow})"/>`;
  // Bright arc — softer, dreamier bloom (drop-shadow 4 → 7px, → 10px when emphasized).
  const prog = `<circle cx="130" cy="130" r="${r}" fill="none" stroke="${stroke}"
      stroke-width="${ORBIT.arcW}" stroke-linecap="round" stroke-opacity="${ORBIT.arcOpacity}"
      ${dash} style="filter:drop-shadow(0 0 ${progBlur}px ${glow})"/>`;
  return track + aura + halo + prog;
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

// Photographic moon (2026-06-04). The body is a real NASA Lunar Reconnaissance
// Orbiter WAC near-side mosaic (PUBLIC DOMAIN — NASA/GSFC/Arizona State Univ.),
// processed to a clean 440px circular asset in assets/moon-lro.webp. The near
// side is tidally locked, so the mosaic's fixed maria + craters are physically
// correct every render; only the phase shadow advances over it.
//
// Layered for the "floating object" depth read:
//   1. cast shadow on the orbital plane (subtle dark ellipse below the moon)
//   2. atmospheric halo (bluish-white bloom — behind moon, in front of rings)
//   3. the photographic disk (clipped) + soft limb darkening + phase terminator
//   4. a faint rim to seat the disk against the halo
function moonSVG(r, illum, waning) {
  const rxT = +(r * Math.abs(1 - 2 * illum)).toFixed(2); // terminator semi-axis
  const limbSweep = waning ? 1 : 0;                       // outer semicircle on the shadow side
  const termSweep = waning ? (illum >= 0.5 ? 0 : 1) : (illum >= 0.5 ? 1 : 0);
  const shadow = `M 0 ${-r} A ${r} ${r} 0 0 ${limbSweep} 0 ${r} A ${rxT} ${r} 0 0 ${termSweep} 0 ${-r} Z`;
  const dim = illum > 0.99; // full moon → no shadow path
  const f = (n) => +(n * r).toFixed(2);
  const haloR = f(2.05);
  const outerHaloR = f(3.15);
  const innerHaloR = f(1.36);

  return `<defs>
      <clipPath id="moonClip"><circle cx="0" cy="0" r="${r}"/></clipPath>
      <radialGradient id="moonOuterHalo" cx="50%" cy="50%" r="50%">
        <stop offset="0%"   stop-color="#E4ECFF" stop-opacity="0.22"/>
        <stop offset="38%"  stop-color="#C8D8FF" stop-opacity="0.14"/>
        <stop offset="72%"  stop-color="#AAC3F0" stop-opacity="0.045"/>
        <stop offset="100%" stop-color="#96B4EB" stop-opacity="0"/>
      </radialGradient>
      <radialGradient id="moonHalo" cx="50%" cy="50%" r="50%">
        <stop offset="0%"   stop-color="#E4ECFF" stop-opacity="0.34"/>
        <stop offset="42%"  stop-color="#C8D8FF" stop-opacity="0.22"/>
        <stop offset="70%"  stop-color="#AAC3F0" stop-opacity="0.11"/>
        <stop offset="100%" stop-color="#96B4EB" stop-opacity="0"/>
      </radialGradient>
      <radialGradient id="moonInnerHalo" cx="50%" cy="50%" r="50%">
        <stop offset="0%"   stop-color="#F4F8FF" stop-opacity="0.36"/>
        <stop offset="46%"  stop-color="#E4ECFF" stop-opacity="0.24"/>
        <stop offset="78%"  stop-color="#C8D8FF" stop-opacity="0.09"/>
        <stop offset="100%" stop-color="#AAC3F0" stop-opacity="0"/>
      </radialGradient>
      <radialGradient id="moonLimb" cx="42%" cy="38%" r="62%">
        <stop offset="0%"   stop-color="#FFFCF4" stop-opacity="0.10"/>
        <stop offset="55%"  stop-color="#FFFFFF" stop-opacity="0"/>
        <stop offset="82%"  stop-color="#000000" stop-opacity="0"/>
        <stop offset="100%" stop-color="#08080E" stop-opacity="0.50"/>
      </radialGradient>
      <radialGradient id="moonSpec" cx="34%" cy="28%" r="50%">
        <stop offset="0%" stop-color="#FFFDF6" stop-opacity="0.20"/>
        <stop offset="45%" stop-color="#EAF1FF" stop-opacity="0.07"/>
        <stop offset="100%" stop-color="#EAF1FF" stop-opacity="0"/>
      </radialGradient>
      <filter id="moonRimBlur" x="-60%" y="-60%" width="220%" height="220%"><feGaussianBlur stdDev="${f(0.05)}"/></filter>
      <filter id="moonOuterHaloBlur" x="-120%" y="-120%" width="340%" height="340%">
        <feGaussianBlur stdDev="${f(0.34)}"/></filter>
      <filter id="moonHaloBlur" x="-90%" y="-90%" width="280%" height="280%">
        <feGaussianBlur stdDev="${f(0.22)}"/></filter>
      <filter id="moonInnerHaloBlur" x="-70%" y="-70%" width="240%" height="240%">
        <feGaussianBlur stdDev="${f(0.12)}"/></filter>
      <filter id="moonTerm" x="-50%" y="-50%" width="200%" height="200%">
        <feGaussianBlur stdDev="${f(0.07)}"/></filter>
      <filter id="moonCast" x="-140%" y="-140%" width="380%" height="380%">
        <feGaussianBlur stdDev="${f(0.16)}"/></filter>
    </defs>
    <ellipse cx="0" cy="${f(0.32)}" rx="${f(1.14)}" ry="${f(0.42)}" fill="#02030A" opacity="0.44" filter="url(#moonCast)"/>
    <circle cx="0" cy="0" r="${outerHaloR}" fill="url(#moonOuterHalo)" filter="url(#moonOuterHaloBlur)"/>
    <circle cx="0" cy="0" r="${haloR}" fill="url(#moonHalo)" filter="url(#moonHaloBlur)"/>
    <circle cx="0" cy="0" r="${innerHaloR}" fill="url(#moonInnerHalo)" filter="url(#moonInnerHaloBlur)"/>
    <g clip-path="url(#moonClip)">
      <image href="assets/moon-lro.webp" x="${-r}" y="${-r}" width="${2 * r}" height="${2 * r}"
             preserveAspectRatio="xMidYMid slice" style="filter:brightness(1.12)"/>
      <circle cx="0" cy="0" r="${r}" fill="url(#moonLimb)"/>
      <circle cx="0" cy="0" r="${r}" fill="url(#moonSpec)"/>
      ${dim ? "" : `<path d="${shadow}" fill="#070B16" opacity="0.86" filter="url(#moonTerm)"/>`}
    </g>
    <circle cx="0" cy="0" r="${r}" fill="none" stroke="#CFE0FF" stroke-opacity="0.50" stroke-width="${f(0.045)}" filter="url(#moonRimBlur)"/>
    <circle cx="0" cy="0" r="${r}" fill="none" stroke="#EAF1FF" stroke-opacity="0.60" stroke-width="${f(0.018)}"/>`;
}

// Assemble the composite SVG and inject; null pct → empty orbit (faint only).
function renderOrbit({ recovery, sleep, strain, moon }) {
  const host = document.getElementById("rings-orbit-svg");
  if (!host) return;
  const { cx, cy, moonR, rings } = ORBIT;
  const m = moon || { illum: 0.5, waning: true };
  host.innerHTML = `<svg viewBox="0 0 260 260" width="100%" height="100%" class="block"
       preserveAspectRatio="xMidYMid meet" style="overflow:visible" aria-label="Orbit rings around moon">
    ${ORBIT_DEFS}
    ${orbitGroup(rings.strain.r,   strain?.pct,   rings.strain.grad,   rings.strain.glow,
                 null, true)}
    ${orbitGroup(rings.recovery.r, recovery?.pct, rings.recovery.grad, rings.recovery.glow)}
    ${orbitGroup(rings.sleep.r,    sleep?.pct,    rings.sleep.grad,    rings.sleep.glow)}
    <g transform="translate(${cx} ${cy})">${moonSVG(moonR, m.illum, m.waning)}</g>
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
function setMetricCorner(key, val, label, detail, color, numColor) {
  const numEl = document.getElementById(`m-${key}-val`);
  const lblEl = document.getElementById(`m-${key}-label`);
  const detEl = document.getElementById(`m-${key}-detail`);
  if (numEl) {
    numEl.textContent = val ?? "—";
    numEl.style.color = val != null ? (numColor || color || "#8A90A6") : "#5A607A";
    // Layered illuminated glow: faint dark seat (legibility over the moon) +
    // tight bright core + wide soft bloom — numbers read as lit, not printed.
    numEl.style.textShadow = (val != null)
      ? `0 0 1px rgba(3,5,15,0.65), 0 0 10px ${color}, 0 0 22px ${color}b3, 0 0 40px ${color}59`
      : "none";
  }
  if (lblEl) {
    lblEl.textContent = label || "";
    lblEl.style.color = color || "#8A90A6";
    lblEl.style.textShadow = label ? `0 0 12px ${color}99` : "none";
  }
  if (detEl) detEl.textContent = detail || "";
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

    // Hero under-moon lunar context — REAL data from lunar_stress.json, mirroring
    // the mockup's 4-line block: phase / "Moon in {sign}" / "Leaves {sign}" / ingress
    // time. Never hardcoded; the sign + ingress come straight from lunar.lunar.
    const moonCtxHero = document.getElementById("moon-context-hero");
    if (moonCtxHero && lunar?.lunar) {
      const L = lunar.lunar;
      const rows = [];
      if (L.phase) rows.push(`<div class="text-[10px] font-semibold tracking-wide" style="color:#B6A0FF;text-shadow:0 0 2px rgba(3,5,15,0.95),0 1px 7px rgba(3,5,15,0.85),0 0 13px rgba(154,107,255,0.5)">${L.phase}</div>`);
      if (L.sign)  rows.push(`<div class="text-[15px] font-semibold leading-tight mt-0.5" style="color:#F4F7FF;text-shadow:0 0 12px rgba(3,5,15,0.85)">Moon in ${L.sign}</div>`);
      const nsc = L.next_sign_change;
      if (nsc) {
        if (nsc.sign) rows.push(`<div class="text-[10px] font-semibold tracking-wide mt-1" style="color:#B6A0FF;text-shadow:0 0 2px rgba(3,5,15,0.92),0 1px 6px rgba(3,5,15,0.8)">Enters ${nsc.sign}</div>`);
        const mt = (nsc.at || "").match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/);
        if (mt) { let h = +mt[4]; const ap = h >= 12 ? "PM" : "AM"; h = h % 12 || 12; rows.push(`<div class="text-[10px] font-semibold tracking-wide" style="color:#B6A0FF;text-shadow:0 0 2px rgba(3,5,15,0.92),0 1px 6px rgba(3,5,15,0.8)">${+mt[2]}/${+mt[3]} · ${h}:${mt[5]} ${ap}</div>`); }
      }
      moonCtxHero.innerHTML = rows.join("");
    }

    const cats = (await fetchJSON("polar/manifest.json")).categories || {};
    const recDates   = (cats.recharge || []).slice().sort();
    const sleepDates = (cats.sleep || []).slice().sort();
    const actDates   = (cats.daily_activity || []).slice().sort();

    // --- SLEEP — most recent sleep_score, only if fresh (≤1 day old) ---
    const sleepDate = sleepDates.at(-1) || null;
    const sleepFresh = sleepDate && (daysSinceDate(sleepDate) ?? 99) <= 1;
    const sleepData = sleepDate ? await fetchJSON(`polar/sleep/${sleepDate}.json`).catch(() => null) : null;
    if (sleepFresh && sleepData) {
      // Duration = sleep_start → sleep_end SPAN (time in bed), matching the Polar
      // app exactly. NOT the sum of light+deep+rem stages — that excludes
      // interruptions and reads short (e.g. 5h 34m vs the real 6h 10m span).
      const st = Date.parse(sleepData.sleep_start_time);
      const en = Date.parse(sleepData.sleep_end_time);
      let durSecs = (!isNaN(st) && !isNaN(en) && en > st) ? Math.round((en - st) / 1000) : null;
      if (durSecs == null) {   // fallback only if span timestamps are missing
        const stages = (sleepData.light_sleep || 0) + (sleepData.deep_sleep || 0) + (sleepData.rem_sleep || 0);
        durSecs = stages || null;
      }
      sleepDur = durSecs ? secsToHM(durSecs) : null;
      // Polar sometimes publishes a night with no finalized Sleep Score (0 + null
      // charge) — e.g. very low continuity, or SleepWise-only data. Treat 0 as
      // "not scored": still show the duration, but no false number, and let the
      // recovery ring use its neutral sleep fallback instead of being dragged to 0.
      if (sleepData.sleep_score > 0) {
        sleepScore = Math.round(sleepData.sleep_score);
        sleep = { pct: sleepScore, color: LPI.sleep };
      }
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
  // Recovery number reads near-white (cyan glow); Sleep/Strain numbers carry
  // their own hue — matching the source mockup.
  setMetricCorner("recovery",
    recoveryScore != null ? `${recoveryScore}` : null,
    recoveryScore != null ? recoveryLabel(recoveryScore) : "",
    hrvDeltaPct != null ? `HRV ${hrvDeltaPct >= 0 ? "+" : ""}${hrvDeltaPct}%` : "",
    LPI.recovery, "#E9F7FF");
  setMetricCorner("sleep",
    sleepScore != null ? `${sleepScore}` : null,
    sleepScore != null ? sleepLabel(sleepScore) : "",
    sleepDur || "",
    LPI.sleep, "#9A6BFF");
  // Strain hue graduates with load (coral → gold → coral → red) — red is the
  // approaching-max signal, not the default. Number, label, glow + caption all
  // share the PRESENCE color so a low-load morning still reads coral and alive
  // (floored off the cold gray-zone), with equal weight to Recovery/Sleep.
  const strainHue = LPI.strain;
  setMetricCorner("strain",
    strainPct != null ? `${Math.round(strainPct)}%` : null,
    strainPct != null ? strainLabel(strainPct) : "",
    strainCal != null ? `Load ${strainCal}` : "",
    strainHue, strainHue);
  const strainCap = document.getElementById("m-strain-cap");
  if (strainCap) {
    strainCap.style.color = strainHue;
    strainCap.style.letterSpacing = "1.8px";   // slight bump → label presence on par with RECOVERY/SLEEP
  }

  // Recovery Window derives from the same recovery/sleep/strain state — render
  // it here so it can never disagree with the corners (no second fetch pass).
  renderRecoveryWindow({ recoveryScore, sleepScore, strainPct, strainCal });

  // Currents State metric echo — computed LIVE from the same ring values so it can
  // never disagree with the rings (the numbers in summary.json are a frozen snapshot
  // and drift when a sync lands between fires; these are authoritative).
  setStateMetricLine(recoveryScore, sleepScore, strainPct);
}

// The deterministic "Recovery N • Sleep N • Strain N%" line under the Currents State
// word. Driven by renderRings so it always mirrors the rings exactly.
function setStateMetricLine(recovery, sleep, strain) {
  const el = document.getElementById("read-metrics");
  if (!el) return;
  const r = recovery != null ? Math.round(recovery) : "—";
  const s = sleep != null ? Math.round(sleep) : "—";
  const st = strain != null ? `${Math.round(strain)}%` : "—";
  el.textContent = `Recovery ${r} • Sleep ${s} • Strain ${st}`;
}

// ---------- Recovery Window (derived status card) ----------
// Reads the recovery/sleep/strain state already computed for the rings and
// derives a single window status. The bar visualizes "recovery charge" (the
// recovery score) — there is no server-side future-window/countdown feed, so
// the bar is the charge level, not a literal timer (flagged in LPI v1 risks).
function renderRecoveryWindow(s) {
  const statusEl = document.getElementById("rw-status");
  const nowEl = document.getElementById("rw-now");
  const bar = document.getElementById("rw-bar");
  const dot = document.getElementById("rw-dot");
  const left = document.getElementById("rw-bar-left");
  const right = document.getElementById("rw-bar-right");
  const note = document.getElementById("rw-note");
  if (!statusEl) return;

  const rec = s.recoveryScore, slp = s.sleepScore, str = s.strainPct;
  if (rec == null) {
    statusEl.textContent = "Awaiting";
    statusEl.style.color = "#8A90A6";
    if (nowEl) nowEl.textContent = "";
    if (bar) bar.style.width = "0%";
    if (dot) dot.style.left = "0%";
    if (left) left.textContent = ""; if (right) right.textContent = "";
    if (note) note.textContent = "Recovery window computes on the next Polar sync.";
    return;
  }

  // Status: Optimal when recovery is high (≥75) — primary driver per spec. Build/
  // Recover/Rest below that. Strain modifies the note, not the gate (no intraday
  // strain-trend feed to test "trending down").
  let status, color, grad, derived;
  const heavy = (str ?? 0) >= 50;
  const shortSleep = slp != null && slp < 55;
  if (rec >= 75) {
    status = "Optimal"; color = LPI.nutrition; grad = "linear-gradient(90deg,#1f8f5f,#39D98A)";
    derived = "Your body is in a good place to recover.";
  } else if (rec >= 55) {
    status = "Building"; color = LPI.recovery; grad = "linear-gradient(90deg,#0a6f8f,#00C8FF)";
    derived = heavy ? "Recovered enough to build — keep effort controlled and bank the rest."
                    : "Mid-range charge — steady, moderate effort builds without digging a hole.";
  } else if (rec >= 40) {
    status = "Recover"; color = LPI.activity; grad = "linear-gradient(90deg,#a85a1f,#FF8A3D)";
    derived = "Charge is down — feed the rebuild: protein, hydration, an earlier night.";
  } else {
    status = "Rest"; color = LPI.strain; grad = "linear-gradient(90deg,#a82e3a,#FF5E62)";
    derived = "Recovery is low — let the nervous system reset before the next hard session.";
  }

  // Window = a 2-hour recovery band anchored on the current clock. The bar/dot
  // position visualizes recovery charge within that band (no server window feed).
  const now = new Date();
  const end = new Date(now.getTime() + 2 * 3600000);
  const hm = d => `${d.getHours()}:${String(d.getMinutes()).padStart(2, "0")}`;
  const pos = Math.max(6, Math.min(96, Math.round(rec)));

  statusEl.textContent = status;
  statusEl.style.color = color;
  statusEl.style.textShadow = `0 0 12px ${color}`;
  if (nowEl) {
    nowEl.textContent = "Now";
    nowEl.style.color = "#E9EDF5";
    nowEl.style.textShadow = "0 0 8px rgba(233,237,245,0.45)";
    nowEl.style.fontWeight = "700";
  }
  if (bar) { bar.style.width = `${pos}%`; bar.style.background = grad; }
  if (dot) { dot.style.left = `${pos}%`; dot.style.background = color; dot.style.boxShadow = `0 0 11px ${color}, 0 0 22px ${color}66, -7px 0 16px ${color}55`; }
  if (left) left.textContent = hm(now);
  if (right) right.textContent = hm(end);
  if (note) note.textContent = derived;
}

// ---------- Physiology grid (Recovery Window metric strip) ----------
// HRV / RHR / Respiratory Rate are real Polar fields. Skin Temp + SpO2 are NOT
// in Alfie's Polar device feed, so they're not shown (removed 2026-06-04).
async function renderPhysiology() {
  const grid = document.getElementById("physiology-grid");
  if (!grid) return;
  let hrv = null, hrvDelta = null, rhr = null, rhrDelta = null, resp = null, respDelta = null;
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
    // Breathing-rate delta vs the history-export baseline (baseline.json) — Resp is
    // the one physiology row without an LSI-supplied delta. Lower than baseline =
    // calmer (good), so goodIsUp:false on the row keeps a downward arrow green.
    const baseline = await loadBaseline();
    const respBaseline = baseline?.nightly_recharge?.breathing_rate_avg ?? null;
    if (resp != null && respBaseline != null) respDelta = +(resp - respBaseline).toFixed(1);
  } catch (e) { /* file:// / no sync → all em-dash */ }

  // Icon set — matches the mockup's row glyphs (heart, heart, lungs).
  const ICONS = {
    heart: '<path d="M19 5.5a4 4 0 0 0-7-2 4 4 0 0 0-7 2c0 4 7 8.5 7 8.5s7-4.5 7-8.5z"/>',
    lungs: '<path d="M12 3v8M8 21c-2 0-3-1.5-3-4 0-3 1-5 2.5-6.5C9 9 9.5 10 9.5 12V18c0 2-.5 3-1.5 3zM16 21c2 0 3-1.5 3-4 0-3-1-5-2.5-6.5C15 9 14.5 10 14.5 12V18c0 2 .5 3 1.5 3z"/>',
  };
  // `meaning` is a one-line, always-visible plain-language gloss rendered under
  // the value column (muted/secondary) so each number reads as "what it says +
  // how to use it" without a tap-to-expand. Clamps to one line at 390px.
  const row = (icon, iconColor, label, value, unit, delta, deltaSuffix, goodIsUp, meaning) => {
    let deltaHTML = "";
    if (delta != null && delta !== 0) {
      const up = delta > 0;
      const good = goodIsUp ? up : !up;
      const dcolor = good ? "#39D98A" : "#FF8A3D";
      deltaHTML = `<span class="text-[10.5px] font-bold stat-num shrink-0" style="color:${dcolor}">${up ? "▲" : "▼"}${Math.abs(delta)}${deltaSuffix}</span>`;
    }
    const valHTML = value != null
      ? `<span class="text-[14px] font-bold stat-num text-white">${value}</span><span class="text-[9px] text-muted">${unit}</span>`
      : `<span class="text-[13px] font-semibold stat-num text-muted">—</span>`;
    return `<div class="phys-row">
      <div class="phys-top">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="${iconColor}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" class="shrink-0">${ICONS[icon]}</svg>
        <span class="text-[9px] uppercase tracking-wide text-muted font-semibold flex-1 min-w-0">${label}</span>
        <span class="flex items-baseline gap-0.5 shrink-0">${valHTML}</span>
        <span class="w-7 text-right shrink-0">${deltaHTML}</span>
      </div>
      <div class="phys-sub">${meaning}</div>
    </div>`;
  };

  grid.innerHTML =
    row("heart",  "#FF5E62", "HRV",   hrv,  "", hrvDelta, "%",   true,
        hrvState(hrvDelta)) +
    row("heart",  "#FF5E62", "RHR",   rhr,  "", rhrDelta, "",    false,
        rhrState(rhrDelta)) +
    row("lungs",  "#00C8FF", "Resp",  resp, "", respDelta, "",   false,
        respState(resp));
}

// ---------- State-aware physiology meanings ----------
// Each maps the CURRENT reading (delta vs baseline, or raw value) to a one-line
// interpretation + suggested action. Replaces the old static metric glosses so
// the subtitle says what THIS number means right now, not what the metric is.
// Null input (no sync / no baseline) falls back to the generic gloss.
function hrvState(deltaPct) {
  if (deltaPct == null) return "Autonomic balance. Higher = recovered; lower = stress.";
  const d = Math.round(deltaPct);
  if (d >= 8)   return "Above baseline. Recovered. Push normally or harder if rested.";
  if (d >= 3)   return "Slightly above baseline. Recovered. Train as planned.";
  if (d >= -3)  return "On baseline. Normal recovery profile.";
  if (d >= -10) return "Below baseline. Mild stress — hydrate, protein, sleep.";
  return "Well below baseline. Real stress — cut intensity, recover.";
}
function rhrState(deltaBpm) {
  if (deltaBpm == null) return "Resting heart rate. Lower trends with fitness; higher = working.";
  const d = Math.round(deltaBpm);
  if (d <= -3) return "Below baseline. Cardiovascular recovery is strong.";
  if (d <= 2)  return "On baseline. Normal resting state.";
  if (d <= 6)  return "Slightly elevated. Working harder — check hydration, sleep.";
  return "Elevated. Real signal — stress, illness, or dehydration. Recover.";
}
function respState(value) {
  if (value == null) return "Breaths per minute. Stable = good; elevated = stress or illness.";
  if (value <= 12.0) return "On the low end of normal. Calm, well-recovered breathing.";
  if (value <= 14.5) return "Stable around normal. Good.";
  if (value <= 16.0) return "Slightly elevated. Stress, activity, or warm sleep environment.";
  return "Elevated. Watch for stress, illness, or poor sleep quality.";
}

// ---------- Supporting summary cards (Nutrition / Scale / Activity) ----------
// Compact glance cards that each tap through to their detail section below. Read
// the same JSON the detail sections read — never a divergent source.
async function renderSupportCards() {
  // ── Nutrition — REMAINING calories (goal − consumed) + consumed/goal donut ──
  try {
    let n = null;
    for (const day of lastN(8).slice().reverse()) {
      try { n = await fetchJSON(`nutrition/daily/${day}.json`); if (!n.date) n.date = day; break; } catch {}
    }
    const valEl = document.getElementById("sc-nutrition-val");
    const unitEl = document.getElementById("sc-nutrition-unit");
    const ringEl = document.getElementById("sc-nutrition-ring");
    const macEl = document.getElementById("sc-nutrition-macros");
    if (n && valEl) {
      const t = n.totals || {}, g = n.goals || {};
      const remain = (g.calories != null && t.calories != null) ? Math.round(g.calories - t.calories) : null;
      valEl.textContent = remain != null ? remain.toLocaleString() : (t.calories != null ? Math.round(t.calories).toLocaleString() : "—");
      if (unitEl) unitEl.textContent = remain != null ? "cal left" : "cal";
      const pct = (t.calories != null && g.calories) ? (t.calories / g.calories) * 100 : 0;
      if (ringEl) ringEl.innerHTML = donutSVG(pct, "#39D98A");
      // macros: compact single line — "P 78  C 257  F 127" (goals live in detail).
      const m = (lbl, v) => v == null ? "" :
        `<span class="mr-1"><span class="text-muted">${lbl}</span> <span class="text-neutral-200 font-semibold stat-num">${Math.round(v)}g</span></span>`;
      if (macEl) macEl.innerHTML = m("P", t.protein_g) + m("C", t.carbs_g) + m("F", t.fat_g);
    }
  } catch (e) {}

  // ── Scale — latest weight + 7-day delta + history sparkline ──
  try {
    const s = await fetchJSON("vesync/snapshot.json");
    const valEl = document.getElementById("sc-scale-val");
    const detEl = document.getElementById("sc-scale-detail");
    const sparkEl = document.getElementById("sc-scale-spark");
    if (valEl) valEl.textContent = s.weight_lb != null ? fmt(s.weight_lb, 1) : "—";
    // history sparkline + delta vs ~7 days prior
    let hist = await fetchJSON("vesync/history.json").catch(() => null);
    let delta = null;
    if (Array.isArray(hist) && hist.length) {
      const sorted = [...hist].filter(r => r.weight_lb != null).sort((a, b) => a.date.localeCompare(b.date));
      const weights = sorted.map(r => r.weight_lb);
      if (sparkEl && weights.length >= 2) sparkEl.innerHTML = sparkline(weights);
      const latest = sorted.at(-1);
      if (latest && latest.delta_lb != null) delta = latest.delta_lb;
      else if (sorted.length >= 2) delta = +(latest.weight_lb - sorted.at(-2).weight_lb).toFixed(1);
    }
    if (detEl) {
      if (delta != null) {
        const c = delta < 0 ? "#39D98A" : delta > 0 ? "#FF8A3D" : "#8A90A6";
        detEl.innerHTML = `<span style="color:${c}" class="font-semibold stat-num">${delta > 0 ? "+" : ""}${delta} lbs</span><span class="text-muted"> vs last 7d</span>`;
      } else detEl.innerHTML = "";
    }
  } catch (e) {}

  // ── Activity — steps + Apple-style multi-ring (steps / active cal / active min) ──
  try {
    const manifest = await fetchJSON("polar/manifest.json");
    const dates = ((manifest.categories || {}).daily_activity || []).slice().sort();
    const latest = dates.at(-1);
    const a = latest ? await fetchJSON(`polar/daily_activity/${latest}.json`).catch(() => null) : null;
    const valEl = document.getElementById("sc-activity-val");
    const ringEl = document.getElementById("sc-activity-ring");
    const statsEl = document.getElementById("sc-activity-stats");
    if (a && valEl) {
      const steps = a["active-steps"] ?? a.step_count ?? null;
      const activeCal = a["active-calories"] != null ? Math.round(a["active-calories"]) : null;
      const activeMin = (() => { const m = /PT(?:(\d+)H)?(?:(\d+)M)?/.exec(a.duration || a["active-time"] || ""); return m ? (+(m[1] || 0)) * 60 + (+(m[2] || 0)) : null; })();
      valEl.textContent = steps != null ? Number(steps).toLocaleString() : "—";
      // Move/Exercise/Stand analogue: steps/10k (outer), active-cal/800 (mid), active-min/60 (inner)
      if (ringEl) ringEl.innerHTML = multiRingSVG([
        { pct: steps != null ? steps / 10000 * 100 : 0, color: "#FF8A3D" },
        { pct: activeCal != null ? activeCal / 800 * 100 : 0, color: "#FF5E62" },
        { pct: activeMin != null ? activeMin / 60 * 100 : 0, color: "#FFD43D" },
      ]);
      // Two stats under the ring (mockup: Distance / Active kcal — distance isn't in
      // the Loop Gen 2 feed, so we surface Active min + Active kcal honestly).
      const stat = (v, lbl) => `<div class="min-w-0"><div class="text-neutral-200 font-bold stat-num text-[11px] leading-none whitespace-nowrap">${v}</div><div class="text-muted text-[8.5px] mt-0.5">${lbl}</div></div>`;
      const activeHM = isoDurationToHM(a.duration) || isoDurationToHM(a["active-time"]);
      if (statsEl) statsEl.innerHTML =
        stat(activeHM || "—", "Active") +
        stat(activeCal != null ? activeCal.toLocaleString() : "—", "Active kcal");
    }

    // ── Calories Burned tile — total daily kcal + active subscript (same feed) ──
    const calTotalEl = document.getElementById("cal-total");
    const calSubEl = document.getElementById("cal-sub");
    if (calTotalEl) {
      const total = a && a.calories != null ? Math.round(a.calories) : null;
      calTotalEl.textContent = total != null ? total.toLocaleString() : "—";
    }
    if (calSubEl) {
      const active = a && a["active-calories"] != null ? Math.round(a["active-calories"]) : null;
      calSubEl.textContent = active != null ? `active ${active.toLocaleString()}` : "active —";
    }

    // ── Recent-burn badge — honest derivation from metrics_history.jsonl ──
    // Polar's live feed has no discrete workouts, only a cumulative daily active-cal
    // sampled at fixed clock-slots. So we surface the REAL active-cal rise over the
    // trailing ~4h, anchored to actual reading times — never a fabricated session.
    // Hidden unless that rise clears a workout-sized threshold.
    renderRecentBurnBadge().catch(() => {});
  } catch (e) {}
}

// Derive "active calories burned in the trailing ~4h" from polar/metrics_history.jsonl
// (timestamped cumulative active_cal snapshots). Shows e.g. "↑ +412 active since 3:00 PM".
// Honest by construction: the number is the delta between two real readings and the
// time is a real reading's timestamp — no per-workout claim, no invented "minutes ago".
const RECENT_BURN_WINDOW_H = 4;   // trailing window the rise is measured over
const RECENT_BURN_THRESHOLD = 150; // kcal — workout-sized rise required to show the badge
async function renderRecentBurnBadge() {
  const el = document.getElementById("cal-workout");
  if (!el) return;
  const hide = () => { el.style.display = "none"; el.textContent = ""; };
  let rows;
  try {
    const txt = await fetch("polar/metrics_history.jsonl", { cache: "no-store" }).then(r => r.ok ? r.text() : "");
    rows = txt.split("\n").map(l => l.trim()).filter(Boolean).map(l => { try { return JSON.parse(l); } catch { return null; } })
      .filter(r => r && r.ts && r.active_cal != null)
      .map(r => ({ t: new Date(r.ts), cal: +r.active_cal }))
      .filter(r => !isNaN(r.t) && !isNaN(r.cal))
      .sort((a, b) => a.t - b.t);
  } catch { return hide(); }
  if (rows.length < 2) return hide();

  const now = new Date();
  const winMs = RECENT_BURN_WINDOW_H * 3600 * 1000;
  const cur = rows[rows.length - 1];
  // Latest reading must itself be fresh, else "recent burn" no longer applies.
  if (now - cur.t > winMs || cur.t > now) return hide();
  // Base = the reading at/just-before the 4h-ago mark (measures the trailing-4h rise).
  const cutoff = new Date(now - winMs);
  let base = null;
  for (const r of rows) { if (r.t <= cutoff) base = r; else break; }
  if (!base) base = rows[0]; // data starts <4h ago — measure from the earliest reading
  const rise = Math.round(cur.cal - base.cal);
  // Cumulative active_cal resets overnight (~4am); a cross-reset window yields a
  // negative/garbage delta — the threshold below naturally suppresses it.
  if (rise < RECENT_BURN_THRESHOLD) return hide();

  const since = base.t.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  el.textContent = `↑ +${rise.toLocaleString()} active since ${since}`;
  el.style.display = "";
}

// Tap-through: hero metric corners scroll to their section.
function scrollToId(id) {
  const t = document.getElementById(id);
  if (t) t.scrollIntoView({ behavior: "smooth", block: "start" });
}

// ---------- Bottom tab navigation (Active / Recovery / Body) ----------
// Single-page: views swap via show/hide (.tab-view.active), no route change. The
// selected tab persists in sessionStorage so refresh/return remembers it.
const TAB_KEY = "fd.activeTab.v1";
const TAB_IDS = ["active", "recovery", "body"];
function setTab(tab) {
  if (!TAB_IDS.includes(tab)) tab = "active";
  TAB_IDS.forEach(t => {
    const view = document.getElementById("tab-" + t);
    if (view) view.classList.toggle("active", t === tab);
    document.querySelectorAll(`#tab-bar .tabnav-item[data-tab="${t}"]`)
      .forEach(b => b.classList.toggle("active", t === tab));
  });
  try { sessionStorage.setItem(TAB_KEY, tab); } catch (e) {}
  window.scrollTo({ top: 0 });
}
// Which tab owns a given element id (so cross-tab tap-throughs jump correctly).
function tabOfElement(id) {
  const el = document.getElementById(id);
  const view = el && el.closest(".tab-view");
  return view ? view.id.replace("tab-", "") : null;
}
function goToTarget(id) {
  const tab = tabOfElement(id);
  if (tab) setTab(tab);
  // wait a frame so the now-visible section has layout before we scroll to it
  requestAnimationFrame(() => requestAnimationFrame(() => scrollToId(id)));
}
function wireTabs() {
  document.querySelectorAll("#tab-bar .tabnav-item").forEach(btn => {
    btn.addEventListener("click", () => setTab(btn.dataset.tab));
  });
  let initial = "active";
  try { const s = sessionStorage.getItem(TAB_KEY); if (s && TAB_IDS.includes(s)) initial = s; } catch (e) {}
  setTab(initial);
}

function wireRings() {
  // Any element with data-target jumps to that section — switching to its owning
  // tab first (sections now live across Active / Recovery / Body views).
  document.querySelectorAll("[data-target]").forEach(btn => {
    btn.addEventListener("click", () => goToTarget(btn.dataset.target));
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
      // Plain-English net-delta read (change is already a rounded integer).
      const x = Math.abs(change);
      const nights = `${days.length} night${days.length === 1 ? "" : "s"}`;
      el.textContent = x < 0.5
        ? `Stable · ${nights}`
        : change > 0
          ? `Trending up · +${x} over ${nights}`
          : `Trending down · −${x} over ${nights}`;
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
      <div style="width:${pct(deep)};background:#2E1F6B" title="Deep ${secsToHM(deep)}"></div>
      <div style="width:${pct(light)};background:#DCCBFF" title="Light ${secsToHM(light)}"></div>
      <div style="width:${pct(rem)};background:#7B4DE0" title="REM ${secsToHM(rem)}"></div>
    </div>
    <div class="flex flex-wrap gap-4 text-xs text-muted mt-2">
      <span><span class="inline-block w-2 h-2 rounded-full align-middle" style="background:#2E1F6B"></span> Deep ${secsToHM(deep)}</span>
      <span><span class="inline-block w-2 h-2 rounded-full align-middle" style="background:#DCCBFF"></span> Light ${secsToHM(light)}</span>
      <span><span class="inline-block w-2 h-2 rounded-full align-middle" style="background:#7B4DE0"></span> REM ${secsToHM(rem)}</span>
    </div>`;
}

// Recharge components detail — surfaces ANS charge (numeric value + 1–6 status
// word), Sleep charge (status), and Nightly Recharge (overall status). These are
// real recharge/sleep fields the dot stack above never shows as numbers/words.
// No historical baseline exists for these (the Polar history export carries no ANS
// Charge — see baseline.json note), so the qualitative word is the qualifier, not a
// delta arrow. PVR-strict: a missing field renders "—".
function renderRechargeDetail(rec, sleep) {
  const host = document.getElementById("recharge-detail");
  if (!host) return;
  const row = (label, valHTML, sub, subColor) => `
    <div class="flex items-baseline justify-between gap-2">
      <span class="text-[9px] uppercase tracking-wide text-muted font-semibold shrink-0">${label}</span>
      <span class="flex items-baseline gap-1.5 min-w-0">
        <span class="text-[13px] font-bold stat-num text-white whitespace-nowrap">${valHTML}</span>
        ${sub ? `<span class="text-[10px] font-semibold whitespace-nowrap" style="color:${subColor || "#8A90A6"}">${sub}</span>` : ""}
      </span>
    </div>`;
  const rows = [];
  // ANS charge — the numeric value leads (signed), status word qualifies it.
  if (rec && rec.ans_charge != null) {
    const v = Number(rec.ans_charge);
    rows.push(row("ANS charge", `${v > 0 ? "+" : ""}${v.toFixed(1)}`,
      polarStatusWord(rec.ans_charge_status), polarStatusColor(rec.ans_charge_status)));
  } else rows.push(row("ANS charge", "—", "", null));
  // Sleep charge — ordinal only (last night's sleep vs your need); word leads, X/6 qualifies.
  if (sleep && sleep.sleep_charge != null) {
    rows.push(row("Sleep charge", polarStatusWord(sleep.sleep_charge),
      `${sleep.sleep_charge}/6`, polarStatusColor(sleep.sleep_charge)));
  } else rows.push(row("Sleep charge", "—", "", null));
  // Boost from sleep — Polar SleepWise alertness boost (0–10). A DIFFERENT metric
  // from the 1–6 Nightly Recharge "Sleep charge" above. Only present when bridged
  // from the app (source-tagged) on nights AccessLink didn't finalize a Sleep Score.
  if (sleep && sleep.sleep_boost != null) {
    rows.push(row("Boost from sleep", `${sleep.sleep_boost}/10`,
      sleep.sleep_boost_status || "", "#39D98A"));
  }
  // Nightly Recharge — overall status word (the dot stack above is its history).
  if (rec && rec.nightly_recharge_status != null) {
    rows.push(row("Nightly Recharge", polarStatusWord(rec.nightly_recharge_status),
      `${rec.nightly_recharge_status}/6`, polarStatusColor(rec.nightly_recharge_status)));
  } else rows.push(row("Nightly Recharge", "—", "", null));
  host.innerHTML = rows.join("");
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

// Recovery-tab 3-col header (SLEEP · ANS CHARGE · HRV). Reuses the data already
// loaded by renderPolar — no extra fetch, no divergent source. PVR-strict: any
// missing field stays "—". Mirrors the kids dashboard SUN/MOON/RISING column row.
function fillRecoveryHeader(rec, sleep, recDates, recMap) {
  const set = (id, txt, sub, subColor) => {
    const v = document.getElementById(id), s = document.getElementById(id.replace("-val", "-sub"));
    if (v) v.textContent = txt;
    if (s) { s.textContent = sub || ""; if (subColor) s.style.color = subColor; }
  };
  // SLEEP — total duration + quality word (sleep charge 1–6)
  if (sleep) {
    const dur = (sleep.light_sleep || 0) + (sleep.deep_sleep || 0) + (sleep.rem_sleep || 0);
    set("rb-sleep-val", dur ? secsToHM(dur) : "—",
        sleep.sleep_charge != null ? `${polarStatusWord(sleep.sleep_charge)} · ${sleep.sleep_charge}/6` : "",
        sleep.sleep_charge != null ? polarStatusColor(sleep.sleep_charge) : null);
  } else { set("rb-sleep-val", "—", "", null); }
  // ANS CHARGE — signed value + recharging / depleting read
  if (rec && rec.ans_charge != null) {
    const a = Number(rec.ans_charge);
    const word = a > 0.1 ? "Recharging" : (a < -0.1 ? "Depleting" : "Steady");
    const wc = a > 0.1 ? "#39D98A" : (a < -0.1 ? "#FF8A3D" : "#8A90A6");
    set("rb-ans-val", `${a > 0 ? "+" : ""}${a.toFixed(1)}`,
        rec.ans_charge_status != null ? `${word} · ${polarStatusWord(rec.ans_charge_status)}` : word, wc);
  } else { set("rb-ans-val", "—", "", null); }
  // HRV — latest value + 7-day delta vs prior 7 days (same math as renderHRV)
  const hrvs = (recDates || []).map(d => recMap[d]?.heart_rate_variability_avg).filter(v => v != null);
  if (hrvs.length) {
    const last7 = hrvs.slice(-7), prior7 = hrvs.slice(-14, -7);
    const avg = a => a.reduce((x, y) => x + y, 0) / a.length;
    let sub = "", sc = "#FF5E8A";
    if (prior7.length) {
      const d = Math.round(avg(last7) - avg(prior7));
      sub = `${d > 0 ? "▲" : d < 0 ? "▼" : "="}${Math.abs(d)} vs 7d`;
      sc = d > 0 ? "#39D98A" : d < 0 ? "#FF8A3D" : "#8A90A6";
    }
    set("rb-hrv-val", `${hrvs.at(-1)} ms`, sub, sc);
  } else { set("rb-hrv-val", "—", "", null); }
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

// Single donut ring (Nutrition card) — pct 0-100, gradient stroke + glow.
function donutSVG(pct, color, size = 38) {
  const r = 17, c = 2 * Math.PI * r, p = Math.max(0, Math.min(100, pct || 0));
  const arc = (p / 100) * c;
  return `<svg width="${size}" height="${size}" viewBox="0 0 42 42" style="overflow:visible">
    <circle cx="21" cy="21" r="${r}" fill="none" stroke="rgba(255,255,255,0.10)" stroke-width="4"/>
    <circle cx="21" cy="21" r="${r}" fill="none" stroke="${color}" stroke-width="4" stroke-linecap="round"
      stroke-dasharray="${arc.toFixed(1)} ${(c - arc).toFixed(1)}" transform="rotate(-90 21 21)"
      style="filter:drop-shadow(0 0 4px ${color})"/>
  </svg>`;
}

// Apple-Activity-style concentric multi-ring (Activity card). rings = [{pct,color}]
// outer → inner. Faint track + bright arc + glow per ring.
function multiRingSVG(rings, size = 40) {
  const radii = [19, 14, 9], stroke = 3.6;
  const body = rings.slice(0, 3).map((ring, i) => {
    const r = radii[i], c = 2 * Math.PI * r, p = Math.max(0, Math.min(100, ring.pct || 0));
    const arc = (p / 100) * c;
    return `<circle cx="23" cy="23" r="${r}" fill="none" stroke="rgba(255,255,255,0.09)" stroke-width="${stroke}"/>` +
      (p > 0 ? `<circle cx="23" cy="23" r="${r}" fill="none" stroke="${ring.color}" stroke-width="${stroke}" stroke-linecap="round"
        stroke-dasharray="${arc.toFixed(1)} ${(c - arc).toFixed(1)}" transform="rotate(-90 23 23)"
        style="filter:drop-shadow(0 0 3px ${ring.color})"/>` : "");
  }).join("");
  return `<svg width="${size}" height="${size}" viewBox="0 0 46 46" style="overflow:visible">${body}</svg>`;
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

// Render the Currents tactical brief. The new prose (summary.py v2) is multiline:
//   State\n{3 metric lines}\n\nRead\n{...}\n\nEligible to work out?\n{...}\n\n...
// Split on blank lines; when a block's first line is a known section header, render
// that header muted/uppercase with the body beneath it (white-space:pre-line keeps the
// 3 State metric lines on separate rows). Old single-paragraph summaries (no known
// header) fall through to one styled paragraph, so an existing summary.json still
// renders cleanly. Section blocks get a small vertical gap.
const BRIEF_HEADERS = ["State", "Read", "Eligible to work out?", "Should you work out?",
                       "Should you eat?", "Should you rest?", "Setup for today?",
                       "TRAINING", "NUTRITION", "RECOVERY"];
function renderBrief(host, text) {
  host.innerHTML = "";
  const blocks = String(text).split(/\n\s*\n/).map(b => b.replace(/\s+$/, "")).filter(b => b.trim());
  const structured = blocks.some(b => BRIEF_HEADERS.includes(b.split("\n")[0].trim()));
  if (!structured) {
    const p = document.createElement("p");
    p.className = "text-[12.5px] leading-snug text-neutral-300";
    p.textContent = text;
    host.appendChild(p);
    return;
  }
  blocks.forEach((b, i) => {
    const lines = b.split("\n");
    const header = lines[0].trim();
    const wrap = document.createElement("div");
    if (i > 0) wrap.style.marginTop = "7px";
    if (BRIEF_HEADERS.includes(header)) {
      const h = document.createElement("div");
      h.className = "text-[10px] uppercase tracking-wider font-semibold text-muted";
      h.textContent = header;
      wrap.appendChild(h);
      const p = document.createElement("p");
      p.className = "text-[12.5px] leading-snug text-neutral-100";
      p.style.whiteSpace = "pre-line";
      p.style.marginTop = "1px";
      p.textContent = lines.slice(1).join("\n").trim();
      wrap.appendChild(p);
    } else {
      const p = document.createElement("p");
      p.className = "text-[12.5px] leading-snug text-neutral-200";
      p.style.whiteSpace = "pre-line";
      p.textContent = b;
      wrap.appendChild(p);
    }
    host.appendChild(wrap);
  });
}

// LPI v1 replica — compact Today's read: a color-coded Recovery word + a
// full-length summary paragraph (Currents IS the full analysis), with an
// "Updated HH:MM" timestamp in the header. Mirrors the source mockup.
const READ_WORD_COLOR = { poor: "#FF5E62", average: "#FF8A3D", good: "#00C8FF", excellent: "#39D98A" };

// Currents v3 brief parser. summary.py writes:
//   State\n{Word}\n{Recovery N • Sleep N • Strain N%}\n\nRead\n{paragraph}\n\n{optional close}
// Split on blank lines; map the State + Read blocks; a short trailing headerless block
// is the optional Close. Legacy single-paragraph (or old TRAINING/NUTRITION) summaries
// degrade gracefully — the whole text falls through to the Read paragraph.
function parseCurrents(text) {
  const blocks = String(text).split(/\n\s*\n/).map(b => b.replace(/\s+$/, "")).filter(b => b.trim());
  let stateWord = "", stateMetrics = "", read = "", closing = "";
  for (const b of blocks) {
    const lines = b.split("\n").map(l => l.trim()).filter(Boolean);
    const head = lines[0] || "";
    if (/^state$/i.test(head)) {
      stateWord = lines[1] || "";
      stateMetrics = lines[2] || "";
    } else if (/^read$/i.test(head)) {
      read = lines.slice(1).join(" ").trim();
    } else if (lines.length === 1 && head.length <= 80) {
      closing = head;                       // lone short line → optional Close
    }
  }
  if (!read && !stateWord) read = String(text).trim();   // legacy fallback
  return { stateWord, stateMetrics, read, closing };
}

async function renderTodaysRead() {
  const ts = document.getElementById("read-ts");
  const body = document.getElementById("read-body");
  const word = document.getElementById("read-recovery-word");
  const metrics = document.getElementById("read-metrics");
  const closing = document.getElementById("read-closing");
  const readLabel = document.getElementById("read-label");
  if (!body) return;
  try {
    const s = await fetchJSON("polar/summary.json");
    const simple = s.simple || null;
    const raw = (simple && (simple.reading || simple.performance)) || s.summary || "";
    const p = parseCurrents(raw);
    // State word — color-coded by the recovery verdict word.
    if (word) {
      const w = (p.stateWord || (simple && simple.recovery) || "").trim();
      word.textContent = w || "—";
      const c = READ_WORD_COLOR[w.toLowerCase()] || "#E9EDF5";
      word.style.color = w ? c : "#E9EDF5";
      word.style.textShadow = w ? `0 0 12px ${c}` : "none";
    }
    if (metrics) metrics.textContent = p.stateMetrics || "";
    // Read — single synthesized paragraph.
    body.textContent = p.read || "First read drops at 9:05 AM";
    if (readLabel) readLabel.style.display = p.read ? "" : "none";
    // Optional Close posture line.
    if (closing) {
      if (p.closing) { closing.textContent = p.closing; closing.classList.remove("hidden"); }
      else { closing.textContent = ""; closing.classList.add("hidden"); }
    }
    if (ts && s.generated_at) {
      const t = new Date(s.generated_at);
      ts.textContent = "updated " + t.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
    }
  } catch (e) {
    body.textContent = "First read drops at 9:05 AM";   // file missing / file://
    if (word) word.textContent = "—";
    if (metrics) metrics.textContent = "";
    if (closing) closing.classList.add("hidden");
    if (ts) ts.textContent = "";
  }
}

// ---------- Currents auto-refresh (60s poll on data_hash) ----------
// Currents must stay live as new data lands (nutrition / activity / recovery / sleep /
// scale syncs) and as summary.py fires through the day. summary.json carries a
// `data_hash` fingerprint of its inputs; we poll every 60s and, when it changes, re-
// render Currents AND the hero/cards/physiology so every number stays consistent. Pure
// local re-read — no LLM call, no cost. First poll seeds the signature so it only fires
// on a real change after load.
let _lastSummarySig = null;
async function pollCurrents() {
  try {
    const s = await fetchJSON("polar/summary.json");
    const sig = s.data_hash || s.generated_at || null;
    if (sig && sig !== _lastSummarySig) {
      _lastSummarySig = sig;
      renderTodaysRead();
      renderRings();          // recovery/sleep/strain numbers + recovery window
      renderSupportCards();   // nutrition / scale / activity tiles
      renderPhysiology();     // HRV / RHR / Resp strip
      renderNutritionNudge();
    }
  } catch (e) { /* offline / file missing → keep last render */ }
}
function startCurrentsPolling() {
  fetchJSON("polar/summary.json")
    .then(s => { _lastSummarySig = s.data_hash || s.generated_at || null; })
    .catch(() => {});
  setInterval(pollCurrents, 60000);
  // Keep the Last Synced relative stamp ticking even between data-hash changes, so
  // "synced N min ago" ages live and flips green→yellow→red on schedule.
  setInterval(renderLastSynced, 60000);
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
// LSI band scale — mirrors polar/lunar_stress.py BANDS (score 0-100 → 5 bands).
// The X/10 is the band's POSITION on a 10-point scale (rank×2), so the band word
// and the number always agree: Stable Control→2, Mild→4, Moderate→6, Elevated→8,
// High Nervous Load→10. This is the derivation that makes "Moderate" read "6/10"
// exactly as in the source mockup (vs the old score/95 that pinned everything ≈1).
const LSI_BANDS = [
  { hi: 25,  rank: 1, name: "Stable Control",      short: "Stable"   },
  { hi: 45,  rank: 2, name: "Mild Compression",    short: "Mild"     },
  { hi: 65,  rank: 3, name: "Moderate Compression", short: "Moderate" },
  { hi: 85,  rank: 4, name: "Elevated Reactivity", short: "Elevated" },
  { hi: 100, rank: 5, name: "High Nervous Load",   short: "High"     },
];
// Band → 2-line plain-English read of what that band means functionally. Keyed by
// the full band name. Replaces the old recommendation prose + score on the default
// view: band word + these two lines lead the card, with the detail rows (sign ·
// degree · phase, ingress, trigger, updated stamp) rendered inline below them.
const LSI_BAND_READ = {
  "Stable Control":       ["Low environmental friction.", "Good output conditions."],
  "Mild Compression":     ["Slight environmental friction.", "Output requires more focus."],
  "Moderate Compression": ["Noticeable environmental friction.", "Recover more, push less."],
  "Elevated Reactivity":  ["High environmental friction.", "Conserve effort today."],
  "High Nervous Load":    ["Strong environmental friction.", "Rest and protect sleep."],
};
function lsiBandFor(score) {
  if (score == null) return null;
  return LSI_BANDS.find(b => score <= b.hi) || LSI_BANDS[LSI_BANDS.length - 1];
}
function lsiIndex10(d) {
  const b = lsiBandFor(d && d.score);
  return b ? b.rank * 2 : null;
}
function scoreToIndex10(score) { const b = lsiBandFor(score); return b ? b.rank * 2 : null; }
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

  // --- Band word (short, large) + a 2-line plain-English read of the band ---
  // Score ("{idx} / 10") is dropped from the default view; the band word + functional
  // read carry the signal more cleanly. The raw idx still computes for the sparkline.
  const band = lsiBandFor(d.score);
  const bandEl = document.getElementById("lsi-band");
  if (bandEl) bandEl.textContent = band ? band.short : (d.band || "—");
  const readEl = document.getElementById("lsi-read");
  if (readEl) {
    const lines = (band && LSI_BAND_READ[band.name]) || [];
    readEl.innerHTML = lines.map(l => `<div>${l}</div>`).join("");
  }
  const trigEl = document.getElementById("lsi-trigger");
  if (trigEl) trigEl.textContent = d.trigger || "";

  // --- Mini sparkline — last 7 days of LSI score → index (polar/lunar_daily/*.json) ---
  const sparkEl = document.getElementById("lsi-spark");
  if (sparkEl) {
    const days = lastN(7);
    const arr = await Promise.all(days.map(dd => fetchJSON(`polar/lunar_daily/${dd}.json`).catch(() => null)));
    const series = arr.map(a => a && a.score != null ? scoreToIndex10(a.score) : null).filter(v => v != null);
    sparkEl.innerHTML = series.length >= 2 ? sparkline(series) : "";
  }

  // --- Moon context (the lunar readout moved out of the hero) ---
  // Compact: "Sign · degree · phase", next ingress, then VoC / retrograde flags
  // in amber when active. Lives in the card body so the hero stays text-empty.
  const SIGN_TO_NATAL_HOUSE = {
    Capricorn: 1,
    Aquarius: 2,
    Pisces: 3,
    Aries: 4,
    Taurus: 5,
    Gemini: 6,
    Cancer: 7,
    Leo: 8,
    Virgo: 9,
    Libra: 10,
    Scorpio: 11,
    Sagittarius: 12
  };
  const moonCtx = document.getElementById("lsi-moon-context");
  if (moonCtx) {
    const parts = [];
    const house = L.sign ? SIGN_TO_NATAL_HOUSE[L.sign] : null;
    if (house) parts.push(`<div class="text-neutral-200 font-medium">Moon is currently in your ${house}H (${L.sign})</div>`);
    const head = [L.sign, L.degree, L.phase].filter(Boolean).join(" · ");
    if (head) parts.push(`<div class="text-neutral-200 font-medium">${head}</div>`);
    const next = L.next_sign_change && L.next_sign_change.display;
    if (next) parts.push(`<div class="text-muted">→ ${next}</div>`);
    if (voc && voc.active)
      parts.push(`<div class="text-warn font-medium">Void of course · until ${voc.until_display || "next ingress"}</div>`);
    transits.filter(isRetro).forEach(t => parts.push(`<div class="text-warn font-medium">${t}</div>`));
    moonCtx.innerHTML = parts.join("");
  }

  // (Recommendation prose retired — the band → 2-line read in lsi-read replaces it.
  //  d.recommendation still computes in lunar_stress.json for the daily pattern log.)

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
    fillBodyHero(s); // Body-tab prominent latest reading
  } catch (e) {
    showEmpty(); // file missing / file://
  }
}

// Body-tab hero — prominent latest scale reading. Reuses vesync/snapshot.json
// already loaded by renderScaleSnapshot (carries bmi + weight_change_lb directly,
// so nothing is computed/fabricated). Weight loss reads green, gain reads coral.
function fillBodyHero(s) {
  const set = (id, txt) => { const el = document.getElementById(id); if (el) el.textContent = txt; };
  set("bh-weight", s.weight_lb != null ? fmt(s.weight_lb, 1) : "—");
  set("bh-bf", s.body_fat_pct != null ? fmt(s.body_fat_pct, 1) + "%" : "—");
  set("bh-muscle", s.muscle_mass_lb != null ? fmt(s.muscle_mass_lb, 1) : "—");
  set("bh-bmi", s.bmi != null ? fmt(s.bmi, 1) : "—");
  set("bh-stamp", s.captured_at ? formatSnapshotTS(s.captured_at) : "");
  const dEl = document.getElementById("bh-delta");
  if (dEl) {
    const d = s.weight_change_lb;
    if (d == null || d === 0) { dEl.textContent = ""; }
    else {
      dEl.textContent = `${d > 0 ? "+" : "−"}${Math.abs(d).toFixed(1)} lb`;
      dEl.style.color = d < 0 ? "#39D98A" : "#FF8A3D"; // down = progress (green)
    }
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
  if (mins >= 120) return { text: "updated 2h+ ago", stale: true };
  if (mins >= 60)  return { text: `updated ${Math.floor(mins / 60)} hr ago`, stale: false };
  if (mins >= 1)   return { text: `updated ${mins} min ago`, stale: false };
  return { text: "updated just now", stale: false };
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
    // "vs typical" deltas from polar/baseline.json (graceful: null baseline → no sub-line).
    const baseline = await loadBaseline();
    const pctVsTyp = (val, avg) => (val != null && avg) ? Math.round((val / avg - 1) * 100) : null;
    const vsTyp = d => d == null ? "" : `${d >= 0 ? "+" : ""}${d}% vs typical`;
    const stepsDelta = pctVsTyp(steps != null ? Number(steps) : null, baseline?.activity?.steps_avg);
    const calDelta   = pctVsTyp(cal != null ? Number(cal) : null, baseline?.activity?.calories_avg);
    const tiles = [
      { label: "steps",       value: steps != null ? Number(steps).toLocaleString() : "—", sub: vsTyp(stepsDelta) },
      { label: "active time", value: activeHM || "—", sub: "" },
      { label: "calories",    value: cal != null ? Number(cal).toLocaleString() : "—", sub: vsTyp(calDelta) },
    ];
    document.getElementById("activity-tiles").innerHTML = tiles.map(t => `
      <div class="bg-bg rounded-lg p-3 border border-line min-w-0">
        <div class="text-2xl font-semibold stat-num leading-tight truncate">${t.value}</div>
        <div class="text-xs text-muted mt-1">${t.label}</div>
        ${t.sub ? `<div class="text-[9px] text-muted mt-0.5 stat-num whitespace-nowrap">${t.sub}</div>` : ""}
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

// ---------- Pattern Engine · Lunar Phase ----------
// Reads polar/patterns.json (built by polar/pattern_engine.py). Shows, for the
// CURRENT moon phase, how Alfie's sleep / recovery / strain on those phase-days
// compares to his overall average — as signed deltas. Historical card family
// (quieter, no glow). Honest about sample size: below 3 phase-days it shows the
// count + "Not enough data yet" and renders "—" instead of noisy deltas.
const PE_GREEN = "#10B981", PE_CORAL = "#FF6B6B", PE_AMBER = "#FBBF24";
const PE_MIN_SAMPLE = 3;

// Sign-based color: positive → green, negative → coral, within ±neutral → gray.
function peDeltaColor(d, neutral) {
  if (d == null || Math.abs(d) <= neutral) return null;   // null → muted/neutral
  return d > 0 ? PE_GREEN : PE_CORAL;
}
// One-line plain-English read of the dominant signal. Phase name substituted in.
// Priority order matches the spec: near-zero → recovery → sleep → strain → mixed.
function peSummary(phase, sd, rd, st) {
  const s = sd ?? 0, r = rd ?? 0, t = st ?? 0;
  if (Math.abs(s) <= 0.3 && Math.abs(r) <= 5 && Math.abs(t) <= 5)
    return "On baseline — this phase has no notable effect yet.";
  if (r >= 10) return `Recovery runs strong this phase — system tends to favor ${phase} nights.`;
  if (r <= -10) return `Recovery dips this phase — system runs lower in ${phase}.`;
  if (s <= -0.5 && r > 0) return "Sleep runs short but recovery holds — efficient phase.";
  if (s >= 0.5) return "You sleep longer this phase — more time in bed.";
  if (t >= 10) return "Strain capacity runs higher this phase — you handle more load.";
  if (t <= -10) return "Strain capacity dips this phase — body absorbs less load.";
  return "Mixed pattern — early read, watch how this evolves.";
}
function peRow(label, valueText, color) {
  const style = color ? ` style="color:${color}"` : "";
  const cls = color ? "text-sm font-semibold stat-num" : "text-sm font-semibold stat-num text-muted";
  return `<div class="flex items-center justify-between">
    <span class="text-sm text-neutral-300">${label}</span>
    <span class="${cls}"${style}>${valueText}</span>
  </div>`;
}

async function renderPatternEngine() {
  const card = document.getElementById("pattern-engine");
  if (!card) return;
  try {
    const data = await fetchJSON("polar/patterns.json");
    const phase = data.current_phase || "—";
    const phaseLc = phase === "—" ? phase : phase.toLowerCase();   // lowercase throughout this card
    const ps = (data.phase_stats || {})[phase] || null;
    const n = ps?.sample_size ?? 0;

    // Option B framing: "When moon is {lowercase phase}".
    document.getElementById("pe-phase").textContent = `When moon is ${phaseLc}`;

    const rowsEl = document.getElementById("pe-rows");
    const sampleEl = document.getElementById("pe-sample");
    const summaryEl = document.getElementById("pe-summary");

    if (!ps || n < PE_MIN_SAMPLE) {
      if (summaryEl) summaryEl.textContent = "Building baseline — need more nights this phase.";
      // Too thin to claim a delta — show structure with em-dashes, honest caveat.
      rowsEl.innerHTML = [
        peRow("Sleep:", "—", null),
        peRow("Recovery:", "—", null),
        peRow("Strain:", "—", null),
      ].join("");
      sampleEl.textContent = n > 0
        ? `Based on ${n} night${n === 1 ? "" : "s"} · not enough data yet`
        : "Building baseline · need ~30+ nights of data";
      sampleEl.className = "text-xs mt-3";
      sampleEl.style.color = PE_AMBER;
      card.classList.remove("hidden");
      return;
    }

    const sd = ps.sleep_delta_h, rd = ps.recovery_delta_pct, st = ps.strain_delta_pct;
    if (summaryEl) summaryEl.textContent = peSummary(phaseLc, sd, rd, st);   // lowercase phase in summary too
    const fmtH = d => d == null ? "—" : `${d > 0 ? "+" : ""}${d.toFixed(1)}h`;
    const fmtPct = d => d == null ? "—" : `${d > 0 ? "+" : ""}${d}%`;
    rowsEl.innerHTML = [
      peRow("Sleep:", fmtH(sd), peDeltaColor(sd, 0.1)),
      peRow("Recovery:", fmtPct(rd), peDeltaColor(rd, 1)),
      peRow("Strain:", fmtPct(st), peDeltaColor(st, 1)),
    ].join("");
    sampleEl.textContent = `Based on ${n} night${n === 1 ? "" : "s"}`;
    sampleEl.className = "text-xs mt-3 text-muted";
    sampleEl.style.color = "";
    card.classList.remove("hidden");
  } catch (e) {
    // no patterns.json yet / file:// → hide ONLY the lunar sub-block; the May
    // retrospective may have opened #pattern-engine on its own.
    document.getElementById("pe-lunar")?.classList.add("hidden");
  }
}

// ───────────────────────── COACH — trainer read ─────────────────────────
// Rule-based personal-trainer card. Three trainer-grade metrics derived purely
// from data we already sync (no new sources, no LLM, zero ongoing cost) plus one
// synthesized Coach's Note picked from ~8 contextual templates by today's real
// data state. All fetches fail gracefully → the default note still renders.
const CG_GREEN = ["#9BE6BE", "rgba(57,217,138,0.15)"];   // healthy / holding
const CG_AMBER = ["#FFD27A", "rgba(255,176,32,0.16)"];   // watch / cooling
const CG_RED   = ["#FF7A7D", "rgba(255,94,98,0.16)"];    // problem / debt
const CG_NEU   = ["#C2C8D4", "rgba(255,255,255,0.07)"];  // neutral
// signed number with a real minus glyph: −1.8, +24.7, 0.0
function coachSign(n, unit = "", dp = 1) {
  if (n == null || isNaN(n)) return "—";
  return (n > 0 ? "+" : n < 0 ? "−" : "") + Math.abs(n).toFixed(dp) + unit;
}
function coachTag(el, text, pair) {
  if (!el) return;
  if (!text || !pair) { el.style.display = "none"; el.textContent = ""; return; }
  el.style.display = "inline-block";
  el.textContent = text;
  el.style.color = pair[0];
  el.style.background = pair[1];
}

async function renderCoach() {
  const noteEl = document.getElementById("coach-note");
  if (!noteEl) return;
  const tsEl = document.getElementById("coach-ts");

  // state bag — every field optional; missing data leaves it null (graceful)
  const S = { w7: null, m7: null, w30: null, m30: null,
              sleepDebtH: null, lastNightMin: null,
              reserve14: null, negStreak: 0, todayAns: null,
              proteinG: null, proteinGoal: null, activeCal: null };

  // ── RECOMP — weight vs muscle deltas (vesync/history.json, newest-first array).
  // Weigh-ins are sparse, so match the reading nearest to the 7d / 30d target. ──
  try {
    const hist = await fetchJSON("vesync/history.json");
    const rows = (hist || []).filter(r => r && r.date && r.weight_lb != null)
      .sort((a, b) => a.date < b.date ? 1 : -1); // newest first
    if (rows.length >= 2) {
      const latest = rows[0];
      const dayNum = d => Math.round(new Date(d + "T00:00:00").getTime() / 864e5);
      const t0 = dayNum(latest.date);
      const nearest = back => {
        let best = null, bestDist = Infinity;
        for (const r of rows.slice(1)) {
          const dist = Math.abs((t0 - dayNum(r.date)) - back);
          if (dist < bestDist) { bestDist = dist; best = r; }
        }
        return best;
      };
      const delta = (a, b, k) => (a[k] != null && b[k] != null) ? +(a[k] - b[k]).toFixed(1) : null;
      const r7 = nearest(7), r30 = nearest(30);
      if (r7)  { S.w7  = delta(latest, r7,  "weight_lb"); S.m7  = delta(latest, r7,  "muscle_mass_lb"); }
      if (r30) { S.w30 = delta(latest, r30, "weight_lb"); S.m30 = delta(latest, r30, "muscle_mass_lb"); }
    }
  } catch {}

  // ── SLEEP DEBT — sum of nightly shortfalls vs 420 min (7h) over last 7 nights.
  // Total sleep = light+deep+rem (seconds → min); shortfall-only, never credited. ──
  try {
    const dates = lastN(7); // oldest → newest
    const files = await Promise.all(dates.map(d => fetchJSON(`polar/sleep/${d}.json`).catch(() => null)));
    let debtMin = 0, have = 0, lastMin = null;
    files.forEach(f => {
      if (!f) return;
      const tot = ((f.light_sleep || 0) + (f.deep_sleep || 0) + (f.rem_sleep || 0)) / 60;
      if (tot <= 0) return;
      debtMin += Math.max(0, 420 - tot);
      have++; lastMin = tot; // last non-empty = most recent night
    });
    if (have) { S.sleepDebtH = +(debtMin / 60).toFixed(1); S.lastNightMin = Math.round(lastMin); }
  } catch {}

  // ── RECOVERY RESERVE — 14d sum of ANS Charge + consecutive net-negative streak. ──
  try {
    const dates = lastN(14);
    const files = await Promise.all(dates.map(d => fetchJSON(`polar/recharge/${d}.json`).catch(() => null)));
    const vals = [];
    files.forEach(f => { if (f && f.ans_charge != null) vals.push(f.ans_charge); });
    if (vals.length) {
      S.reserve14 = +vals.reduce((a, b) => a + b, 0).toFixed(1);
      S.todayAns = vals[vals.length - 1];
      let streak = 0;
      for (let i = vals.length - 1; i >= 0; i--) { if (vals[i] < 0) streak++; else break; }
      S.negStreak = streak;
    }
  } catch {}

  // ── today's protein (nutrition) + active calories (Polar) — for note templates ──
  try {
    for (const day of lastN(3).slice().reverse()) {
      try {
        const n = await fetchJSON(`nutrition/daily/${day}.json`);
        const t = n.totals || {}, g = n.goals || {};
        if (t.protein_g != null) {
          S.proteinG = Math.round(t.protein_g);
          S.proteinGoal = g.protein_g != null ? Math.round(g.protein_g) : null;
          break;
        }
      } catch {}
    }
  } catch {}
  try {
    for (const day of lastN(2).slice().reverse()) {
      try {
        const a = await fetchJSON(`polar/daily_activity/${day}.json`);
        if (a["active-calories"] != null) { S.activeCal = Math.round(a["active-calories"]); break; }
      } catch {}
    }
  } catch {}

  // ── paint the three metric tiles ──
  const $ = id => document.getElementById(id);
  // RECOMP
  const rv = $("coach-recomp-val"), rs = $("coach-recomp-sub"), rt = $("coach-recomp-tag");
  if (rv) {
    if (S.w7 != null) {
      rv.textContent = coachSign(S.w7, " lb");
      if (rs) rs.textContent = S.m7 != null ? `muscle ${coachSign(S.m7, " lb")}` : "muscle —";
      if (S.w30 != null) rv.title = `30d: weight ${coachSign(S.w30, " lb")}${S.m30 != null ? ` · muscle ${coachSign(S.m30, " lb")}` : ""}`;
      let tag, pair;
      if (S.w7 < 0 && (S.m7 == null || S.m7 >= -0.3))                                  { tag = "recomp win";  pair = CG_GREEN; }
      else if (S.m7 != null && S.m7 < 0 && Math.abs(S.m7) >= Math.abs(S.w7))           { tag = "losing muscle"; pair = CG_RED; }
      else if (S.w7 > 0 && S.m7 != null && S.m7 > 0)                                    { tag = "gaining";     pair = CG_NEU; }
      else                                                                             { tag = "mixed";       pair = CG_AMBER; }
      coachTag(rt, tag, pair);
    } else { rv.textContent = "—"; if (rs) rs.textContent = "need 2 weigh-ins"; coachTag(rt, "", null); }
  }
  // SLEEP DEBT
  const sv = $("coach-sleep-val"), stag = $("coach-sleep-tag");
  if (sv) {
    if (S.sleepDebtH != null) {
      sv.textContent = "−" + S.sleepDebtH.toFixed(1) + " h";
      let pair = CG_GREEN, lbl = "on target";
      if (S.sleepDebtH > 3)      { pair = CG_RED;   lbl = "deep debt"; }
      else if (S.sleepDebtH > 1) { pair = CG_AMBER; lbl = "behind"; }
      sv.style.color = pair[0];
      coachTag(stag, lbl, pair);
    } else { sv.textContent = "—"; coachTag(stag, "", null); }
  }
  // RECOVERY RESERVE
  const cv = $("coach-reserve-val"), csub = $("coach-reserve-sub"), ctag = $("coach-reserve-tag");
  if (cv) {
    if (S.reserve14 != null) {
      cv.textContent = coachSign(S.reserve14, " ANS");
      let pair, lbl, sub = "ANS reserve";
      if (S.negStreak >= 5)      { pair = CG_RED;   lbl = "deload near";  sub = `${S.negStreak}d slide`; }
      else if (S.negStreak >= 3) { pair = CG_AMBER; lbl = "cooling fast"; sub = `${S.negStreak}d slide`; }
      else if (S.reserve14 < 0)  { pair = CG_AMBER; lbl = "running low"; }
      else                       { pair = CG_GREEN; lbl = "banked"; }
      cv.style.color = pair[0];
      coachTag(ctag, lbl, pair);
      if (csub) csub.textContent = sub;
    } else { cv.textContent = "—"; coachTag(ctag, "", null); }
  }

  // ── Coach's Note — one template, chosen by priority cascade over today's state ──
  const f1 = n => Math.abs(n).toFixed(1);
  const ansStr = S.todayAns != null ? coachSign(S.todayAns) : null;
  const note = (() => {
    // 1 · under-recovery — the cardinal trainer rule
    if (S.sleepDebtH != null && S.sleepDebtH > 2 && S.todayAns != null && S.todayAns < 0)
      return `ANS is at ${ansStr} and you're ${f1(S.sleepDebtH)}h down on sleep this week. You can't out-train under-recovery — tonight, 9 PM wind-down, no exceptions.`;
    // 2 · heavy load on a flat nervous system
    if (S.activeCal != null && S.activeCal >= 1000 && S.todayAns != null && S.todayAns < 0)
      return `Today's load ran hot (${S.activeCal.toLocaleString()} active kcal) and ANS is flat at ${ansStr}. Tomorrow: Z2 only or a pure walk — no intensity.`;
    // 3 · reserve sliding
    if (S.negStreak >= 3)
      return `ANS has slid ${S.negStreak} days straight. The reserve's still there but you're spending it fast — bank one real recovery day before the next hard session.`;
    // 4 · losing muscle + protein under goal
    if (S.m7 != null && S.m7 < 0 && Math.abs(S.m7) >= Math.abs(S.w7 || 0) && S.proteinGoal != null && S.proteinG != null && S.proteinG < S.proteinGoal)
      return `Muscle's slipping (${coachSign(S.m7, " lb")}) and protein came in under goal. Hit ${S.proteinGoal}g+ tomorrow before anything else.`;
    // 5 · green light
    if (S.todayAns != null && S.todayAns > 0 && S.proteinGoal != null && S.proteinG != null && S.proteinG >= S.proteinGoal && S.sleepDebtH != null && S.sleepDebtH < 1)
      return `Reserve's healthy and fueling's clean (${S.proteinG}g protein). Tomorrow's a green-light day — go earn a hard session.`;
    // 6 · recomp win
    if (S.w7 != null && S.w7 < 0 && (S.m7 == null || S.m7 >= -0.3))
      return `Down ${f1(S.w7)}lb with muscle holding — that's textbook recomp. Keep protein high and don't chase the scale.`;
    // 7 · fueling locked, recovery is the bottleneck
    if (S.proteinGoal != null && S.proteinG != null && S.proteinG >= S.proteinGoal && ((S.sleepDebtH != null && S.sleepDebtH > 1) || (S.todayAns != null && S.todayAns < 1)))
      return `Fueling's locked (${S.proteinG}g protein) — recovery's the bottleneck now. Protect sleep tonight and the rest follows.`;
    // 8 · default
    return `Steady day. Hold the line — consistency is the whole game.`;
  })();
  noteEl.textContent = note;
  if (tsEl) tsEl.textContent = labelMD(lastN(1)[0]);
}

function renderAll() {
  renderCoach();      // async, trainer read: 3 metrics + synthesized Coach's Note
  renderTodaysRead(); // async, AI health summary
  renderMonthlyHistory(); // static monthly retrospective card (polar/history/2026-05.json)
  renderLunarStress(); // async, Lunar Stress Index (polar/lunar_stress.py)
  renderNutrition(); // async, today's macros from Calories Club
  renderNutritionNudge(); // async, single-line time-aware nutrition nudge (summary.json)
  renderHeader();
  renderProfileStrip();
  renderScaleSnapshot(); // async, VeSync screenshot OCR snapshot (manual via Penny)
  renderScaleHistory(); // async, VeSync scale history table (manual via Penny)
  renderRings(); // async, LPI hero: moon + 3 orbital rings + metric corners + recovery window
  renderPhysiology(); // async, Recovery Window physiology strip (HRV/RHR/Resp)
  renderSupportCards(); // async, Nutrition / Scale / Activity summary cards
  wireRings();   // tap-through scroll on metric corners + card links
  wireTabs();    // bottom tab bar: Active / Recovery / Body (sessionStorage-persisted)
  renderActivity(); // async, Polar Loop Gen 2 daily activity (steps / active time / calories)
  renderPolar(); // async, live Polar Loop data
  renderLastSynced(); // async, Last Synced freshness badge (manifest.synced_at)
  wireLastSynced();   // tap-to-refresh on the Last Synced badge (bound once)
  renderPatternEngine(); // async, lunar-phase correlations (polar/patterns.json)
  renderDayReview(); // async, nightly Day-in-Review freeze (polar/day_review.json)
}

renderAll();
startCurrentsPolling();   // Currents auto-refresh: 60s poll on summary.json data_hash
