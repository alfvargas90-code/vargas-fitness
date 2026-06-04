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
  { name: "Light",    min: 50,  max: 399,      dot: "#cbd5e1" }, // slate-300
  { name: "Moderate", min: 400, max: 799,      dot: "#3b5bff" }, // electric — engaged
  { name: "Heavy",    min: 800, max: Infinity, dot: "#ffba00" }, // gold — real load
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

// Concept 03 state-color bands — read on a COOL→WARM axis, not separate
// semantic hues. Cool (electric/cobalt) = calm/restored/recovery; warm
// (gold/coral) = output/effort/strain; maroon = depleted/off. Values are
// luminance-lifted from the pure anchors so they stay legible (and glow well)
// as arcs on OLED black. The soft glow is applied uniformly in orbitGroup().
function sleepColor(v) {              // Sleep — cool when restful, maroon when starved
  return v >= 90 ? "#3b5bff"   // electric — good/performance-level sleep
       : v >= 50 ? "#5b6fd6"   // muted cobalt — mid
       : v >= 30 ? "#9c4a55"   // lifted maroon — low
       :           "#7a2f3a";  // deep maroon — chronic-low
}
function energyColor(v) {             // Recovery — cobalt bright down to coral
  return v >= 90 ? "#4f74ff"   // cobalt bright — excellent
       : v >= 50 ? "#3b5bff"   // electric — good
       : v >= 30 ? "#d9706e"   // desaturated coral — low
       :           "#ff6260";  // coral — poor
}
function strainColor(pct) {           // Strain — warm axis, more load → hotter
  return pct < 15 ? "#7d84a8"   // muted blue-gray — nothing meaningful yet (calm)
       : pct < 50 ? "#cda33f"   // desaturated gold — light load
       : pct < 80 ? "#ffba00"   // gold — real load
       : pct < 95 ? "#ff6260"   // coral — heavy
       :            "#ff5350";  // saturated coral — max / red zone
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

const ORBIT = {
  cx: 150, cy: 150,          // viewBox center (viewBox is 0 0 300 300)
  tilt: 35, flatten: 0.55,   // 35° disk; ry = rx * 0.55
  moonR: 30,                 // inner orbit clears the moon by ~14px at its narrowest
  rings: {                   // inside → out
    recovery: { rx: 80 },
    sleep:    { rx: 104 },
    strain:   { rx: 128 },
  },
  base: "#3a3a3a",           // faint orbit stroke (muted gray — metadata)
  arcW: 6, baseW: 2,
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

// Monochrome phase-accurate moon: full lit disk + a shadow path. Waning = lit on
// the left, shadow growing from the right (current state). The terminator is a
// half-ellipse whose horizontal semi-axis = r·|1-2·illum|; its bulge direction
// flips at the quarter so gibbous shows a thin shadow sliver and crescent a fat one.
function moonSVG(r, illum, waning) {
  const rxT = +(r * Math.abs(1 - 2 * illum)).toFixed(2); // terminator semi-axis
  const limbSweep = waning ? 1 : 0;                       // outer semicircle on the shadow side
  const termSweep = waning ? (illum >= 0.5 ? 0 : 1) : (illum >= 0.5 ? 1 : 0);
  const shadow = `M 0 ${-r} A ${r} ${r} 0 0 ${limbSweep} 0 ${r} A ${rxT} ${r} 0 0 ${termSweep} 0 ${-r} Z`;
  const dim = illum > 0.99; // full moon → no shadow path
  return `<circle cx="0" cy="0" r="${r}" fill="#d4d4d4"/>
    ${dim ? "" : `<path d="${shadow}" fill="#262626"/>`}
    <circle cx="0" cy="0" r="${r}" fill="none" stroke="#52525b" stroke-width="1"/>`;
}

// Assemble the composite SVG and inject; null pct → empty orbit (faint only).
function renderOrbit({ recovery, sleep, strain, moon }) {
  const host = document.getElementById("rings-orbit-svg");
  if (!host) return;
  const { cx, cy, moonR } = ORBIT;
  const m = moon || { illum: 0.5, waning: true, degree: "" };
  const signLbl = m.degree
    ? `<text x="0" y="${moonR + 13}" text-anchor="middle" fill="#9ca3af" font-size="9"
             font-family="-apple-system, system-ui, sans-serif" class="stat-num">${m.degree}</text>`
    : "";
  host.innerHTML = `<svg viewBox="0 0 300 300" width="100%" height="100%" class="block"
       preserveAspectRatio="xMidYMid meet" aria-label="Orbit rings around moon">
    <g transform="translate(${cx} ${cy})">
      ${orbitGroup(ORBIT.rings.strain.rx,   strain?.pct,   strain?.color   || ORBIT.base)}
      ${orbitGroup(ORBIT.rings.sleep.rx,    sleep?.pct,    sleep?.color    || ORBIT.base)}
      ${orbitGroup(ORBIT.rings.recovery.rx, recovery?.pct, recovery?.color || ORBIT.base)}
      ${moonSVG(moonR, m.illum, m.waning)}
      ${signLbl}
    </g>
  </svg>`;
}

// Update a floating corner label's value + color (index.html owns the markup).
function setRingLabel(id, text, color) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = text;
  el.style.color = color;
  // Same-hue glow at the card-corner anchor when a live value is present;
  // cleared for the faint default so "—" stays calm.
  el.style.textShadow = color && color !== ORBIT.base ? `0 0 8px ${color}` : "none";
}

async function renderRings() {
  const host = document.getElementById("rings-orbit-svg");
  if (!host) return;

  // Defaults — faint orbits + a half-lit moon so something renders on file:// / no sync.
  let recovery = null, sleep = null, strain = null;
  let moon = { illum: 0.5, waning: true, degree: "" };

  try {
    const lunar = await fetchJSON("polar/lunar_stress.json").catch(() => null);
    if (lunar?.lunar) {
      const { illum, waning } = phaseToIllum(lunar.lunar.phase);
      moon = { illum, waning, degree: lunar.lunar.degree || "" };
    }

    const cats = (await fetchJSON("polar/manifest.json")).categories || {};
    const recDates   = (cats.recharge || []).slice().sort();
    const sleepDates = (cats.sleep || []).slice().sort();
    const actDates   = (cats.daily_activity || []).slice().sort();

    // --- SLEEP — most recent sleep_score, only if fresh (≤1 day old) ---
    const sleepDate = sleepDates.at(-1) || null;
    const sleepFresh = sleepDate && (daysSinceDate(sleepDate) ?? 99) <= 1;
    const sleepData = sleepDate ? await fetchJSON(`polar/sleep/${sleepDate}.json`).catch(() => null) : null;
    if (sleepFresh && sleepData?.sleep_score != null) {
      const s = Math.round(sleepData.sleep_score);
      sleep = { pct: s, label: `${s}`, color: sleepColor(s) };
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
      const score = computeRecoveryScore(rec, sleepData, hrvBaseline);
      recovery = { pct: score, label: `${score}`, color: energyColor(score) };
    }

    // --- STRAIN — inverse of the old Reserve bar (depletion % of 800 cal) ---
    const actDate = actDates.at(-1) || null;
    const actFresh = actDate && (daysSinceDate(actDate) ?? 99) <= 1;
    const act = actDate ? await fetchJSON(`polar/daily_activity/${actDate}.json`).catch(() => null) : null;
    if (actFresh && act && act["active-calories"] != null) {
      const pct = Math.min(100, (Number(act["active-calories"]) / RESERVE_DEPLETION_CAL) * 100);
      strain = { pct, label: `${Math.round(pct)}%`, color: strainColor(pct) };
    }
  } catch (e) { /* file:// or no sync yet → orbits stay faint, labels "—" */ }

  renderOrbit({ recovery, sleep, strain, moon });
  setRingLabel("lbl-recovery-val", recovery?.label ?? "—", recovery?.color ?? ORBIT.base);
  setRingLabel("lbl-sleep-val",    sleep?.label    ?? "—", sleep?.color    ?? ORBIT.base);
  setRingLabel("lbl-strain-val",   strain?.label   ?? "—", strain?.color   ?? ORBIT.base);
}

// Tap-through: each floating corner label scrolls to its detail card.
function wireRings() {
  document.querySelectorAll("#glance-rings button[data-target]").forEach(btn => {
    btn.addEventListener("click", () => {
      const t = document.getElementById(btn.dataset.target);
      if (t) t.scrollIntoView({ behavior: "smooth", block: "start" });
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
      ? `<span class="inline-block w-3 h-3 rounded-full" style="background:#3b5bff"></span>`
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
      <div style="width:${pct(deep)};background:#4f74ff" title="Deep ${secsToHM(deep)}"></div>
      <div style="width:${pct(light)};background:#3b5bff" title="Light ${secsToHM(light)}"></div>
      <div style="width:${pct(rem)};background:#8fa3ff" title="REM ${secsToHM(rem)}"></div>
    </div>
    <div class="flex flex-wrap gap-4 text-xs text-muted mt-2">
      <span><span class="inline-block w-2 h-2 rounded-full align-middle" style="background:#4f74ff"></span> Deep ${secsToHM(deep)}</span>
      <span><span class="inline-block w-2 h-2 rounded-full align-middle" style="background:#3b5bff"></span> Light ${secsToHM(light)}</span>
      <span><span class="inline-block w-2 h-2 rounded-full align-middle" style="background:#8fa3ff"></span> REM ${secsToHM(rem)}</span>
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
// Concept 03 cool→warm mapping + same-hue glow.
const RECOVERY_COLORS = {
  poor: "text-coral glow-coral",       // coral — depleted
  average: "text-gold glow-gold",      // gold — caution
  good: "text-electric glow-electric", // electric — restored
  excellent: "text-cobalt glow-cobalt",// cobalt bright — peak recovery
};
// "Wind down" / "Rest day" are evening / off verdicts (sleep prep / day's-done
// framing — metadata, not a performance state); the others are daytime training
// calls. All are bolded by renderTodaysRead(), and the verdict word itself is
// colored by meaning: green = push/improve, cyan = recovery-is-good, amber =
// caution, gray = neutral non-state. Longer phrases first so startsWith() wins.
const PERF_VERDICTS = ["Push hard", "Train normally", "Moderate effort", "Prioritize recovery", "Wind down", "Rest day"];
// Concept 03 cool→warm verdict palette (warm = push for output, cool = recover,
// maroon = off). Each carries a same-hue glow.
const PERF_VERDICT_COLORS = {
  "Push hard":          "text-coral glow-coral",       // coral — peak output
  "Train normally":     "text-electric glow-electric", // electric — recovery is good
  "Moderate effort":    "text-gold glow-gold",         // gold — caution
  "Prioritize recovery":"text-muted",                  // muted blue-gray — ease off
  "Wind down":          "text-muted",                  // muted blue-gray — evening
  "Rest day":           "text-maroon glow-maroon",     // deep maroon — day's done
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

  const row = (label, value, amber) => {
    if (!value) return "";
    return `<div class="flex gap-2 text-sm leading-relaxed">` +
      `<span class="text-muted w-28 shrink-0">${label}</span>` +
      `<span class="${amber ? "text-warn font-medium" : "text-neutral-200"}">${value}</span></div>`;
  };

  // Headline: Moon sign + degree (e.g. "Moon in Capricorn · 23° Cap 36'").
  const head = L.sign
    ? `Moon in ${L.sign}${L.degree ? ` · <span class="text-muted font-normal">${L.degree}</span>` : ""}`
    : "—";

  let html = `<div class="text-lg font-semibold text-cobalt mb-3">${head}</div>`;
  html += `<div class="space-y-1.5">`;
  html += row("Phase", L.phase);
  html += row("Next sign", L.next_sign_change && L.next_sign_change.display);
  if (voc && voc.active) {
    html += row("Void of Course", `now through ${voc.until_display || "next ingress"}`, true);
  }
  if (transits.length) {
    html += transits.map((t, i) => row(i === 0 ? "Transits" : "", t, isRetro(t))).join("");
  } else {
    html += row("Transits", "none active");
  }
  html += `</div>`;
  content.innerHTML = html;

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
  easy:  { label: "Easy day",  cls: "text-electric bg-electric/15" },  // electric — recovered
  solid: { label: "Solid day", cls: "text-electric bg-electric/15" },  // electric — good
  great: { label: "Great day", cls: "text-coral bg-coral/15" },        // coral — peak output
  big:   { label: "Big day",   cls: "text-gold bg-gold/15" },          // gold — heavy load
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
  renderRings(); // async, Whoop-style Sleep / Recovery / Strain glance rings
  wireRings();   // tap-through scroll on each ring
  renderActivity(); // async, Polar Loop Gen 2 daily activity (steps / active time / calories)
  renderPolar(); // async, live Polar Loop data
  renderDayReview(); // async, nightly Day-in-Review freeze (polar/day_review.json)
}

renderAll();
