// ---------- Storage ----------
const KEY_SCANS   = "fd.scans.v1";
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

let scans  = load(KEY_SCANS,  SEED_DEXA);
let weight = load(KEY_WEIGHT, SEED_WEIGHT);
let goals  = load(KEY_GOALS,  SEED_GOALS);
let scale  = load(KEY_SCALE,  SEED_SCALE);

// ---------- Helpers ----------
const fmt = (n, d = 1) => (n == null || isNaN(n) ? "—" : Number(n).toFixed(d));
const byDate = (a, b) => a.date.localeCompare(b.date);
const latestScan = () => [...scans].sort(byDate).at(-1);
const earliestScan = () => [...scans].sort(byDate).at(0);
const latestScale = () => [...scale].sort(byDate).at(-1);

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
  sub.textContent = new Date().toLocaleDateString("en-US", {
    weekday: "long", year: "numeric", month: "long", day: "numeric",
  });
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

function renderKPIs() {
  // KPI tiles show ONLY the latest DEXA scan — current values, units only,
  // no historical deltas, percentile bands, or cross-source weight.
  const s = latestScan();
  if (!s) return;
  document.getElementById("kpi-bf").textContent      = fmt(s.body_fat_pct, 1) + "%";
  document.getElementById("kpi-bf-sub").textContent  = "%";
  document.getElementById("kpi-lean").textContent    = fmt(s.lean_mass_lbs, 1);
  document.getElementById("kpi-fat").textContent     = fmt(s.fat_mass_lbs, 1);
  document.getElementById("kpi-weight").textContent  = fmt(s.weight_lbs, 1);
  document.getElementById("kpi-weight-sub").textContent = "lbs";
  document.getElementById("kpi-rmr").textContent     = fmt(s.rmr_cal, 0);
}

function renderScale() {
  const s = latestScale();
  const sub = document.getElementById("scale-sub");
  const grid = document.getElementById("scale-grid");
  if (!s) { sub.textContent = "No readings yet."; grid.innerHTML = ""; return; }

  const change = s.weight_change_lbs;
  const changeStr = change == null ? "" :
    ` · ${change > 0 ? "▲" : change < 0 ? "▼" : ""} ${fmt(Math.abs(change), 1)} lbs since prior`;
  sub.innerHTML = `${s.source} · ` + freshnessHTML(s.date, "step on scale") + changeStr;

  const ratingColor = { Excellent: "text-good", Fitness: "text-good", Standard: "text-slate-100", High: "text-warn", Low: "text-warn" };
  const r = s.ratings || {};
  const items = [
    { label: "Weight",            value: `${fmt(s.weight_lbs, 1)} lbs`,               rating: null },
    { label: "BMI",               value: fmt(s.bmi, 1),                               rating: r.bmi },
    { label: "Body fat",          value: `${fmt(s.body_fat_pct, 1)}%`,                rating: r.body_fat_pct },
    { label: "Muscle mass",       value: `${fmt(s.muscle_mass_lbs, 1)} lbs`,          rating: r.muscle_mass_lbs },
    { label: "Fat-free weight",   value: `${fmt(s.fat_free_weight_lbs, 1)} lbs`,      rating: null },
    { label: "Skeletal muscles",  value: `${fmt(s.skeletal_muscles_pct, 1)}%`,        rating: r.skeletal_muscles_pct },
    { label: "Subcutaneous fat",  value: `${fmt(s.subcutaneous_fat_pct, 1)}%`,        rating: r.subcutaneous_fat_pct },
    { label: "Visceral fat",      value: `${fmt(s.visceral_fat_rating, 0)} (rating)`, rating: r.visceral_fat_rating },
    { label: "Body water",        value: `${fmt(s.body_water_pct, 1)}%`,              rating: r.body_water_pct },
    { label: "Protein",           value: `${fmt(s.protein_pct, 1)}%`,                rating: r.protein_pct },
    { label: "Bone mass",         value: `${fmt(s.bone_mass_lbs, 1)} lbs`,            rating: r.bone_mass_lbs },
    { label: "BMR",               value: `${fmt(s.bmr_kcal, 0)} kcal`,                rating: r.bmr_kcal },
    { label: "Metabolic age",     value: fmt(s.metabolic_age, 0),                     rating: r.metabolic_age },
  ];

  grid.innerHTML = items.map(it => `
    <div>
      <div class="text-xs uppercase tracking-wider text-muted">${it.label}</div>
      <div class="text-xl font-semibold stat-num mt-1">${it.value}</div>
      <div class="text-xs mt-1 ${it.rating ? (ratingColor[it.rating] ?? "text-muted") : "text-muted"}">${it.rating ?? "—"}</div>
    </div>
  `).join("");
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

    const window14 = lastN(14);
    renderRechargeStack(window14, recMap);
    renderRechargeTrend(window14, recMap);
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

// ---------- Energy throughout day (modeled) ----------
// Loop Gen 2 has no continuous daytime HR via AccessLink — so this is an HONEST
// model: starting energy at wake is derived from last night's recovery metrics,
// then decayed linearly across waking hours to viewing time.
const WAKE_HOUR = 6.5;          // 6:30 AM CST — Alfie's typical morning
const ENERGY_DECAY_FRAC = 0.06; // ~6% of starting energy lost per waking hour

function energyColor(v) {
  return v >= 70 ? "#34d399" : v >= 40 ? "#fbbf24" : "#f87171";
}

async function renderEnergy() {
  const empty = document.getElementById("energy-empty");
  const content = document.getElementById("energy-content");
  if (!empty || !content) return;
  const showEmpty = () => { empty.classList.remove("hidden"); content.classList.add("hidden"); };
  try {
    const manifest = await fetchJSON("polar/manifest.json");
    const cats = manifest.categories || {};
    const recDates = (cats.recharge || []).slice().sort();
    const sleepDates = (cats.sleep || []).slice().sort();
    const latestDate = [recDates.at(-1), sleepDates.at(-1)].filter(Boolean).sort().at(-1);
    // Stale (>1 day old) or no data → empty state.
    const age = daysSinceDate(latestDate);
    if (latestDate == null || age == null || age > 1) return showEmpty();

    const rec = await fetchJSON(`polar/recharge/${recDates.at(-1)}.json`).catch(() => null);
    const sleep = await fetchJSON(`polar/sleep/${sleepDates.at(-1)}.json`).catch(() => null);

    // HRV baseline = mean of available overnight HRV readings (adaptive, honest).
    const hrvs = (await Promise.all(recDates.map(d => fetchJSON(`polar/recharge/${d}.json`).catch(() => null))))
      .map(r => r?.heart_rate_variability_avg).filter(v => v != null);
    const hrvBaseline = hrvs.length ? hrvs.reduce((a, b) => a + b, 0) / hrvs.length : null;

    // Starting energy at wake from last night's recovery (each piece falls back if missing).
    const rechargePart = rec?.ans_charge_status != null ? (rec.ans_charge_status / 6) * 50 : 25;
    const sleepPart    = sleep?.sleep_score != null ? (sleep.sleep_score / 100) * 30 : 15;
    const hrvPart      = (rec?.heart_rate_variability_avg != null && hrvBaseline)
      ? Math.min(rec.heart_rate_variability_avg / hrvBaseline, 1) * 20 : 10;
    let start = Math.min(rechargePart + sleepPart + hrvPart, 100);

    // Decay across waking hours to now (local clock; Alfie is Central).
    const now = new Date();
    const nowHour = now.getHours() + now.getMinutes() / 60;
    const hoursSinceWake = Math.max(nowHour - WAKE_HOUR, 0);
    const ratePerHour = start * ENERGY_DECAY_FRAC;
    const current = Math.max(start - hoursSinceWake * ratePerHour, 10);

    // Curve from wake → now for the sparkline.
    const curve = [];
    for (let h = 0; h <= hoursSinceWake + 0.001; h += 1)
      curve.push(Math.max(start - h * ratePerHour, 10));
    curve.push(current);

    const col = energyColor(current);
    const numEl = document.getElementById("energy-num");
    numEl.textContent = `${Math.round(current)}%`;
    numEl.style.color = col;
    const bar = document.getElementById("energy-bar");
    bar.style.width = `${Math.round(current)}%`;
    bar.style.background = col;
    const spark = document.getElementById("energy-spark");
    spark.style.color = col;
    spark.innerHTML = curve.length >= 2 ? sparkline(curve) : "";
    document.getElementById("energy-detail").textContent =
      `Started: ${Math.round(start)} · Decayed to ${Math.round(current)} over ${hoursSinceWake.toFixed(1)}h`;
    document.getElementById("energy-sub").innerHTML = freshnessHTML(latestDate, "wear the watch");

    empty.classList.add("hidden");
    content.classList.remove("hidden");
  } catch (e) {
    showEmpty(); // file:// or no sync yet
  }
}

// Block A — 14-day vertical stack of 6-dot Nightly Recharge rows (newest on top).
function renderRechargeStack(days, recMap) {
  const rows = days.slice().reverse().map(d => {
    const st = recMap[d]?.ans_charge_status ?? null;
    let cells;
    if (st == null) {
      cells = Array.from({ length: 6 }, () => `<span class="inline-block w-3 text-center text-line leading-3">–</span>`).join("");
    } else {
      cells = Array.from({ length: 6 }, (_, i) => i < st
        ? `<span class="inline-block w-3 h-3 rounded-full" style="background:#22d3ee"></span>`
        : `<span class="inline-block w-3 h-3 rounded-full bg-card border border-line"></span>`).join("");
    }
    return `<div class="flex items-center gap-2">
      <span class="text-xs text-muted w-12 shrink-0">${labelMD(d)}</span>
      <span class="flex items-center gap-1">${cells}</span>
    </div>`;
  });
  document.getElementById("polar-recharge-stack").innerHTML = rows.join("");
}

// Least-squares trend of recharge status over the 14-day window's available points.
function renderRechargeTrend(days, recMap) {
  const el = document.getElementById("polar-recharge-trend");
  const pts = [];
  days.forEach((d, i) => { const st = recMap[d]?.ans_charge_status; if (st != null) pts.push([i, st]); });
  if (pts.length < 2) { el.textContent = ""; return; }
  const n = pts.length;
  const sx = pts.reduce((a, p) => a + p[0], 0), sy = pts.reduce((a, p) => a + p[1], 0);
  const sxx = pts.reduce((a, p) => a + p[0] * p[0], 0), sxy = pts.reduce((a, p) => a + p[0] * p[1], 0);
  const denom = n * sxx - sx * sx;
  if (!denom) { el.textContent = ""; return; }
  const slope = (n * sxy - sx * sy) / denom;
  // Change across the OBSERVED range, not extrapolated over empty days — keeps
  // it honest on a 1–6 scale when points cluster. Clamp to the scale span.
  const observed = pts.at(-1)[0] - pts[0][0];
  let change = Math.round(slope * observed);
  change = Math.max(-5, Math.min(5, change));
  const arrow = change > 0 ? "↑" : change < 0 ? "↓" : "→";
  el.textContent = `trending: ${arrow} ${change > 0 ? "+" : ""}${change} over 14 days`;
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
    <h3 class="text-sm font-medium text-muted mb-2">Sleep stages · ${labelMD(sleep.date)}</h3>
    <div class="stage-bar">
      <div style="width:${pct(deep)};background:#22d3ee" title="Deep ${secsToHM(deep)}"></div>
      <div style="width:${pct(light)};background:#60a5fa" title="Light ${secsToHM(light)}"></div>
      <div style="width:${pct(rem)};background:#a78bfa" title="REM ${secsToHM(rem)}"></div>
    </div>
    <div class="flex flex-wrap gap-4 text-xs text-muted mt-2">
      <span><span class="inline-block w-2 h-2 rounded-full align-middle" style="background:#22d3ee"></span> Deep ${secsToHM(deep)}</span>
      <span><span class="inline-block w-2 h-2 rounded-full align-middle" style="background:#60a5fa"></span> Light ${secsToHM(light)}</span>
      <span><span class="inline-block w-2 h-2 rounded-full align-middle" style="background:#a78bfa"></span> REM ${secsToHM(rem)}</span>
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

async function renderTodaysRead() {
  const ts = document.getElementById("read-ts");
  const body = document.getElementById("read-body");
  const basis = document.getElementById("read-basis");
  if (!body) return;
  try {
    const s = await fetchJSON("polar/summary.json");
    // Clear any accordion from a previous render.
    const prev = document.getElementById("read-sections");
    if (prev) prev.remove();
    if (Array.isArray(s.sections) && s.sections.length) {
      // Section 12 five-section shape — render as collapsible accordions.
      // <details> can't live inside the <p>, so build a sibling container.
      body.textContent = "";
      body.style.display = "none";
      const wrap = document.createElement("div");
      wrap.id = "read-sections";
      s.sections.forEach((sec, i) => {
        const d = document.createElement("details");
        d.className = "read-section";
        if (i === 0) d.open = true;            // first section expanded
        const sum = document.createElement("summary");
        sum.textContent = sec.label;
        const p = document.createElement("p");
        p.textContent = sec.text;
        d.appendChild(sum);
        d.appendChild(p);
        wrap.appendChild(d);
      });
      body.parentNode.insertBefore(wrap, body.nextSibling);
    } else {
      body.style.display = "";
      body.textContent = s.summary || "First read drops at 8:30 AM";
    }
    if (ts && s.generated_at) {
      const t = new Date(s.generated_at);
      ts.textContent = "updated " + t.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
    }
    if (basis) {
      const b = s.data_basis || {};
      const parts = [];
      if (b.recharge_today != null) parts.push(`recharge ${b.recharge_today}/6`);
      if (b.sleep_hours != null) parts.push(`sleep ${b.sleep_hours}h`);
      if (b.hrv_today != null) parts.push(`HRV ${b.hrv_today} ms`);
      const dataDate = (s.generated_at || "").slice(0, 10);
      const fresh = dataDate ? " · " + freshnessHTML(dataDate, "wear the watch") : "";
      basis.innerHTML = (parts.length ? "Based on: " + parts.join(", ") : "") + fresh;
    }
  } catch (e) {
    const prev = document.getElementById("read-sections");
    if (prev) prev.remove();
    body.style.display = "";
    body.textContent = "First read drops at 8:30 AM";   // file missing / file://
    if (ts) ts.textContent = "";
    if (basis) basis.textContent = "";
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
        ? `<div class="h-1.5 bg-line rounded-full mt-2 overflow-hidden"><div class="h-full bg-accent" style="width:${pct}%"></div></div>`
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
        <td class="py-2 pr-2 text-slate-200">${r.date}</td>
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

function renderAll() {
  renderTodaysRead(); // async, AI health summary
  renderNutrition(); // async, today's macros from Calories Club
  renderHeader();
  renderProfileStrip();
  renderKPIs();
  renderScaleSnapshot(); // async, VeSync screenshot OCR snapshot (manual via Penny)
  renderScaleHistory(); // async, VeSync scale history table (manual via Penny)
  renderScale();
  renderEnergy(); // async, modeled energy-throughout-day from overnight Polar recovery
  renderPolar(); // async, live Polar Loop data
}

// ---------- Modal ----------
const modal = document.getElementById("modal");
const modalBody = document.getElementById("modal-body");
const modalTitle = document.getElementById("modal-title");
function openModal(title, html) {
  modalTitle.textContent = title;
  modalBody.innerHTML = html;
  modal.classList.remove("hidden");
}
function closeModal() { modal.classList.add("hidden"); modalBody.innerHTML = ""; }
document.getElementById("modal-close").onclick = closeModal;
modal.onclick = (e) => { if (e.target === modal) closeModal(); };

// ---------- Forms ----------
const inputCls = "w-full bg-card border border-line rounded-md px-3 py-2 text-sm focus:outline-none focus:border-accent";
const labelCls = "block text-xs uppercase tracking-wider text-muted mb-1";
const today = () => new Date().toISOString().slice(0, 10);

// ---------- Scale entry form ----------
const RATING_OPTS = ["", "Excellent", "Fitness", "Standard", "High", "Low"];
const ratingSelect = (name, val = "") =>
  `<select class="${inputCls}" name="${name}">
    ${RATING_OPTS.map(o => `<option value="${o}" ${o === val ? "selected" : ""}>${o || "— rating —"}</option>`).join("")}
  </select>`;

document.getElementById("btn-add-scale").onclick = () => {
  const prev = latestScale() || {};
  openModal("Log scale reading", `
    <form id="scale-form" class="space-y-4">
      <div class="grid grid-cols-2 gap-3">
        <div><label class="${labelCls}">Date</label><input class="${inputCls}" name="date" type="date" value="${today()}" required></div>
        <div><label class="${labelCls}">Source</label><input class="${inputCls}" name="source" type="text" value="${prev.source ?? "Alfie scale"}"></div>
        <div><label class="${labelCls}">Weight (lbs)</label><input class="${inputCls}" name="weight_lbs" type="number" step="0.1" required></div>
        <div><label class="${labelCls}">BMI</label><input class="${inputCls}" name="bmi" type="number" step="0.1"></div>
        <div><label class="${labelCls}">Body fat %</label><input class="${inputCls}" name="body_fat_pct" type="number" step="0.1"></div>
        <div><label class="${labelCls}">BF rating</label>${ratingSelect("r_body_fat_pct")}</div>
        <div><label class="${labelCls}">Muscle mass (lbs)</label><input class="${inputCls}" name="muscle_mass_lbs" type="number" step="0.1"></div>
        <div><label class="${labelCls}">Muscle rating</label>${ratingSelect("r_muscle_mass_lbs")}</div>
        <div><label class="${labelCls}">Fat-free weight (lbs)</label><input class="${inputCls}" name="fat_free_weight_lbs" type="number" step="0.1"></div>
        <div><label class="${labelCls}">Skeletal muscles %</label><input class="${inputCls}" name="skeletal_muscles_pct" type="number" step="0.1"></div>
        <div><label class="${labelCls}">Subcutaneous fat %</label><input class="${inputCls}" name="subcutaneous_fat_pct" type="number" step="0.1"></div>
        <div><label class="${labelCls}">Visceral fat (rating 1–59)</label><input class="${inputCls}" name="visceral_fat_rating" type="number" step="1" min="1" max="59"></div>
        <div><label class="${labelCls}">Body water %</label><input class="${inputCls}" name="body_water_pct" type="number" step="0.1"></div>
        <div><label class="${labelCls}">Protein %</label><input class="${inputCls}" name="protein_pct" type="number" step="0.1"></div>
        <div><label class="${labelCls}">Bone mass (lbs)</label><input class="${inputCls}" name="bone_mass_lbs" type="number" step="0.1"></div>
        <div><label class="${labelCls}">BMR (kcal)</label><input class="${inputCls}" name="bmr_kcal" type="number"></div>
        <div><label class="${labelCls}">Metabolic age</label><input class="${inputCls}" name="metabolic_age" type="number"></div>
        <div><label class="${labelCls}">Protein rating</label>${ratingSelect("r_protein_pct")}</div>
      </div>
      <div class="flex justify-end gap-2 pt-2">
        <button type="button" id="cancel-scale" class="px-4 py-2 text-sm text-muted">Cancel</button>
        <button class="bg-accent text-ink font-medium px-4 py-2 rounded-lg text-sm">Save reading</button>
      </div>
    </form>
  `);
  document.getElementById("cancel-scale").onclick = closeModal;
  document.getElementById("scale-form").onsubmit = (e) => {
    e.preventDefault();
    const f = e.target;
    const n  = name => { const v = f[name]?.value; return v !== "" && v != null ? parseFloat(v) : null; };
    const ni = name => { const v = f[name]?.value; return v !== "" && v != null ? parseInt(v, 10) : null; };

    const prevScale = latestScale();
    const newWeight = n("weight_lbs");
    const weightChange = prevScale && newWeight != null ? +(newWeight - prevScale.weight_lbs).toFixed(1) : null;

    const entry = {
      date: f.date.value,
      source: f.source.value || "Manual",
      weight_lbs: newWeight,
      weight_change_lbs: weightChange,
      bmi: n("bmi"),
      body_fat_pct: n("body_fat_pct"),
      muscle_mass_lbs: n("muscle_mass_lbs"),
      fat_free_weight_lbs: n("fat_free_weight_lbs"),
      skeletal_muscles_pct: n("skeletal_muscles_pct"),
      subcutaneous_fat_pct: n("subcutaneous_fat_pct"),
      visceral_fat_rating: ni("visceral_fat_rating"),
      body_water_pct: n("body_water_pct"),
      protein_pct: n("protein_pct"),
      bone_mass_lbs: n("bone_mass_lbs"),
      bmr_kcal: ni("bmr_kcal"),
      metabolic_age: ni("metabolic_age"),
      ratings: {
        body_fat_pct:    f.r_body_fat_pct.value    || undefined,
        muscle_mass_lbs: f.r_muscle_mass_lbs.value || undefined,
        protein_pct:     f.r_protein_pct.value     || undefined,
      },
    };
    Object.keys(entry.ratings).forEach(k => entry.ratings[k] === undefined && delete entry.ratings[k]);

    scale = scale.filter(s => s.date !== entry.date);
    scale.push(entry);
    save(KEY_SCALE, scale);

    if (newWeight) {
      weight = weight.filter(w => w.date !== entry.date);
      weight.push({ date: entry.date, weight_lbs: newWeight, note: `${entry.source} scale` });
      save(KEY_WEIGHT, weight);
    }

    closeModal();
    renderAll();
  };
};

renderAll();
