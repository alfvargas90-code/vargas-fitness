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
  { name: "Moderate", min: 400, max: 799,      dot: "#22d3ee" }, // cyan-400
  { name: "Heavy",    min: 800, max: Infinity, dot: "#fbbf24" }, // amber-400
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

// ---------- Today's recovery (overnight, static) ----------
// Loop Gen 2 has no continuous daytime HR via AccessLink — so there's no honest
// way to model intraday decay. We compute one starting recovery score from last
// night's metrics and show it, unchanged, all day.
function energyColor(v) {
  return v >= 80 ? "#34d399"   // green — strong
       : v >= 60 ? "#22d3ee"   // cyan — decent
       : v >= 40 ? "#fbbf24"   // amber — light
       :           "#f87171";  // red — rest
}

function recoveryTagline(v) {
  return v >= 80 ? "Strong — bounced back well."
       : v >= 60 ? "Decent recovery."
       : v >= 40 ? "Light recovery — take it easier."
       :           "Prioritize rest today.";
}

// ---------- Reserve bar (depletes through the day with REAL activity) ----------
// The morning recovery number is the baseline (last night's overnight charge).
// The Reserve bar shows how much of that charge today's accumulated active-calories
// have spent — grounded in actual Polar data, NOT a fake time-decay. 800 active cal
// fully depletes it, tying to the LOAD_BANDS thresholds (Heavy = 800+ = empty).
//   0 cal → 100% · 400 cal → 50% · 800+ cal → 0% (capped)
const RESERVE_DEPLETION_CAL = 800;
// Color shifts as the reserve drains (independent of the recovery-score chip color).
function reserveColor(pct) {
  return pct >= 80 ? "#34d399"   // emerald — full
       : pct >= 60 ? "#22d3ee"   // cyan
       : pct >= 40 ? "#fbbf24"   // amber
       :             "#f87171";  // red — spent
}
// Build the 10-segment monospace bar HTML (mirrors the LSI contribution bars).
// opts: { restDay, stale } toggle the locked / fallback states.
function renderReserveBar(activeCal, opts = {}) {
  const SEG = 10;
  if (opts.restDay) {
    const full = "█".repeat(SEG);
    return `Reserve: <span class="tracking-tight" style="color:#34d399">[${full}]</span> Locked · Rest`;
  }
  if (opts.stale) {
    return `Reserve: <span class="text-muted">— (no fresh activity)</span>`;
  }
  const c = (activeCal == null || isNaN(activeCal)) ? 0 : Number(activeCal);
  const pct = Math.max(0, Math.round(100 - (c / RESERVE_DEPLETION_CAL) * 100));
  const filledSeg = Math.round(pct / 10);
  const filled = "█".repeat(Math.max(0, filledSeg));
  const empty = "░".repeat(Math.max(0, SEG - filledSeg));
  const col = reserveColor(pct);
  return `Reserve: <span class="tracking-tight">[` +
         `<span style="color:${col}">${filled}</span><span class="text-line">${empty}</span>` +
         `]</span> ${pct}%`;
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
    const start = Math.round(Math.min(rechargePart + sleepPart + hrvPart, 100));

    // No decay model — this is the morning number, shown unchanged all day.
    const col = energyColor(start);
    const numEl = document.getElementById("energy-num");
    numEl.textContent = `${start}`;
    numEl.style.color = col;
    const chip = document.getElementById("energy-chip");
    if (chip) chip.style.background = col;
    document.getElementById("energy-tagline").textContent = recoveryTagline(start);
    document.getElementById("energy-sub").innerHTML = freshnessHTML(latestDate, "wear the watch");

    // Reserve bar — how much of the morning charge today's movement has spent.
    // Reads the SAME daily_activity file as the Activity card; depletion is keyed
    // to the SAME 800-cal Heavy threshold (LOAD_BANDS), so it can never contradict.
    const reserveEl = document.getElementById("energy-reserve");
    if (reserveEl) {
      let activeCal = 0, activityDate = null;
      try {
        const am = await fetchJSON("polar/manifest.json");
        const adates = ((am.categories || {}).daily_activity || []).slice().sort();
        if (adates.length) {
          activityDate = adates.at(-1);
          const a = await fetchJSON(`polar/daily_activity/${activityDate}.json`).catch(() => null);
          if (a && a["active-calories"] != null) activeCal = Number(a["active-calories"]);
        }
      } catch { /* no activity synced yet → full reserve */ }
      // Rest day flagged → locked, no depletion (Penny manages polar/rest_days.json).
      let restDay = false;
      try {
        const rd = await fetchJSON("polar/rest_days.json");
        restDay = activityDate ? (rd?.rest_days || []).includes(activityDate) : false;
      } catch { /* no rest-day file → not a rest day */ }
      // Stale activity (>1 day old) → can't trust depletion; show fallback.
      const actAge = daysSinceDate(activityDate);
      const stale = activityDate != null && actAge != null && actAge > 1;
      reserveEl.innerHTML = renderReserveBar(activeCal, { restDay, stale });
    }

    empty.classList.add("hidden");
    content.classList.remove("hidden");
  } catch (e) {
    showEmpty(); // file:// or no sync yet
  }
}

// Block A — vertical stack of 6-dot Nightly Recharge rows (newest on top).
// `days` is pre-filtered to nights with data, so every row renders dots.
function renderRechargeStack(days, recMap) {
  const title = document.getElementById("polar-recharge-title");
  if (title) title.textContent = `Nightly Recharge · last ${days.length} night${days.length === 1 ? "" : "s"} with data`;
  const rows = days.slice().reverse().map(d => {
    const st = recMap[d]?.ans_charge_status ?? 0;
    const cells = Array.from({ length: 6 }, (_, i) => i < st
      ? `<span class="inline-block w-3 h-3 rounded-full" style="background:#22d3ee"></span>`
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
    <h3 class="text-sm font-medium text-purple-300/80 mb-2">Sleep stages · ${labelMD(sleep.date)}</h3>
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

// Plain-English Today's read — renders the `simple` block from summary.py.
// No raw numbers, units, biometric labels, or astrology jargon (enforced in the
// prompt). Recovery is a color-coded single word; Transit Impact only shows when
// a real transit is hitting.
const RECOVERY_COLORS = {
  poor: "text-bad",       // red
  average: "text-warn",   // amber
  good: "text-accent",    // cyan
  excellent: "text-good", // green
};
// "Wind down" is the evening-only verdict (sleep prep / day's-done framing); the
// other four are daytime training calls. All are bolded by renderTodaysRead().
const PERF_VERDICTS = ["Push hard", "Train normally", "Moderate effort", "Prioritize recovery", "Wind down"];

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
  p.className = "text-base leading-relaxed text-slate-200";
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
        p.className = "text-base leading-relaxed text-slate-200";
        p.style.fontSize = "15px";
        const lead = document.createElement("strong");
        lead.className = "text-slate-100";
        lead.textContent = "Performance: ";
        p.appendChild(lead);
        const t = String(simple.performance).trim();
        const v = PERF_VERDICTS.find(v => t.toLowerCase().startsWith(v.toLowerCase()));
        if (v) {
          const strong = document.createElement("strong");
          strong.className = "text-slate-100";
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

// ---------- Lunar Stress Index (polar/lunar_stress.py) ----------
// Band -> color classes (score number text, chip bg/text, dot bg). Mirrors the
// spec bands: emerald / cyan / amber / orange / red.
const LSI_BANDS = [
  { max: 25,  name: "Stable Control",     num: "text-good",    chip: "bg-good/15 text-good",       dot: "bg-good" },
  { max: 45,  name: "Mild Compression",   num: "text-accent",  chip: "bg-accent/15 text-accent",   dot: "bg-accent" },
  { max: 65,  name: "Moderate Compression", num: "text-warn",  chip: "bg-warn/15 text-warn",       dot: "bg-warn" },
  { max: 85,  name: "Elevated Reactivity", num: "text-orange-400", chip: "bg-orange-400/15 text-orange-400", dot: "bg-orange-400" },
  { max: 100, name: "High Nervous Load",  num: "text-bad",     chip: "bg-bad/15 text-bad",         dot: "bg-bad" },
];
const lsiBand = score => LSI_BANDS.find(b => score <= b.max) || LSI_BANDS[LSI_BANDS.length - 1];

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

  // Band is the headline; the numeric score stays in lunar_stress.json (other
  // systems read it) but is no longer rendered on the card.
  const band = lsiBand(d.score);
  document.getElementById("lsi-band").textContent = d.band || band.name;
  document.getElementById("lsi-band-chip").className =
    `inline-flex items-center gap-2 px-2.5 py-1 rounded-full text-sm font-medium ${band.chip}`;
  document.getElementById("lsi-band-dot").className = `w-2 h-2 rounded-full ${band.dot}`;

  // Contribution bars — relative weight of transit vs body, precomputed in the
  // JSON (filled/total). Monospace + unicode blocks so the segments line up.
  const barsEl = document.getElementById("lsi-bars");
  if (barsEl) {
    const row = (label, b) => {
      if (!b || b.filled == null) return "";
      const filled = "█".repeat(Math.max(0, b.filled));
      const empty = "░".repeat(Math.max(0, (b.total || 10) - b.filled));
      return `<div class="flex items-center gap-2">` +
        `<span class="w-16 shrink-0 font-sans text-xs uppercase tracking-wide text-muted">${label}</span>` +
        `<span class="tracking-tight"><span class="${band.num}">${filled}</span><span class="text-line">${empty}</span></span>` +
        `</div>`;
    };
    const b = d.bars || {};
    barsEl.innerHTML = row("Transit", b.transit) + row("Body", b.body);
  }

  // Trigger + transit texture (sign · phase · house).
  const td = d.transit_detail || {};
  const bits = [];
  // Skip the "<Sign> Moon" texture when the trigger already names that sign.
  if (td.moon_sign && !(d.trigger || "").includes(td.moon_sign)) bits.push(`${td.moon_sign} Moon`);
  if (td.moon_phase) bits.push(td.moon_phase);
  if (td.moon_house_natal) bits.push(`natal ${ordinal(td.moon_house_natal)} house`);
  document.getElementById("lsi-trigger").innerHTML =
    `<span class="text-slate-100 font-medium">${d.trigger || "—"}</span>` +
    (bits.length ? ` · <span class="text-muted">${bits.join(" · ")}</span>` : "");

  // Physiology line.
  const p = d.physiology || {};
  const phys = [];
  if (p.hrv_pct_baseline != null) phys.push(`HRV ${p.hrv_pct_baseline > 0 ? "+" : ""}${p.hrv_pct_baseline}%`);
  if (p.rhr_delta_bpm != null) phys.push(`RHR ${p.rhr_delta_bpm > 0 ? "+" : ""}${p.rhr_delta_bpm} bpm`);
  if (p.sleep_score != null) phys.push(`Sleep ${p.sleep_score}`);
  document.getElementById("lsi-physiology").textContent = phys.length ? phys.join("  ·  ") : "—";

  // Workout row removed from the LSI card: it read as a recommendation but is
  // actually a load measurement, contradicting the Today's Read verdict. The
  // Recovery tile's Reserve bar owns today's-load display. The
  // workout_intensity field stays in lunar_stress.json — the scoring engine
  // still uses it for the +0/+3/+10 modifier.

  // Recommendation.
  document.getElementById("lsi-recommendation").textContent = d.recommendation || "";

  // Timestamp + stale warning (lunar position drifts; flag >2h old).
  const ts = document.getElementById("lsi-ts");
  const basis = document.getElementById("lsi-basis");
  if (d.generated_at) {
    const t = new Date(d.generated_at);
    const ageH = (Date.now() - t.getTime()) / 3600000;
    if (ts) ts.textContent = "updated " + t.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
    if (basis) {
      basis.innerHTML = ageH > 2
        ? `<span class="text-warn font-medium">⚠️ ${Math.round(ageH)}h old — Moon position may have drifted; refreshes on next Polar sync.</span>`
        : `<span class="text-muted">Behavioral calibration, not prediction · transit + Polar physiology.</span>`;
    }
  }
}

function ordinal(n) {
  const s = ["th", "st", "nd", "rd"], v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
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
  easy:  { label: "Easy day",  cls: "text-slate-300 bg-slate-800" },
  solid: { label: "Solid day", cls: "text-cyan-300 bg-cyan-900/40" },
  great: { label: "Great day", cls: "text-emerald-300 bg-emerald-900/40" },
  big:   { label: "Big day",   cls: "text-amber-300 bg-amber-900/40" },
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
  renderEnergy(); // async, static morning recovery score from overnight Polar metrics
  renderActivity(); // async, Polar Loop Gen 2 daily activity (steps / active time / calories)
  renderPolar(); // async, live Polar Loop data
  renderDayReview(); // async, nightly Day-in-Review freeze (polar/day_review.json)
}

renderAll();
