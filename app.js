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
  const s = latestScan();
  const sub = document.getElementById("header-sub");
  if (!s) { sub.textContent = "No scans yet."; return; }
  sub.textContent = `Latest: ${s.source} on ${s.date} · Height ${s.height_in}" · Age at scan: ${ageOn(s.date)}`;
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
  const s = latestScan();
  if (!s) return;
  document.getElementById("kpi-bf").textContent      = fmt(s.body_fat_pct, 1) + "%";
  document.getElementById("kpi-bf-sub").textContent  = bfPercentileBand(ageOn(s.date), s.body_fat_pct);
  document.getElementById("kpi-lean").textContent    = fmt(s.lean_mass_lbs, 1);
  document.getElementById("kpi-fat").textContent     = fmt(s.fat_mass_lbs, 1);

  const latestWeight = [...weight].sort(byDate).at(-1);
  document.getElementById("kpi-weight").textContent  = fmt(latestWeight?.weight_lbs ?? s.weight_lbs, 1);
  document.getElementById("kpi-weight-sub").textContent = latestWeight ? `lbs · logged ${latestWeight.date}` : "lbs";
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
  sub.textContent = `${s.source} · ${s.date}${changeStr}`;

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

function renderHistory() {
  const sorted = [...scans].sort(byDate).reverse();
  document.getElementById("scan-history").innerHTML = sorted.map(s => `
    <tr class="border-b border-line/50">
      <td class="py-2 pr-4">${s.date}</td>
      <td class="py-2 pr-4 text-right stat-num">${fmt(s.weight_lbs,1)}</td>
      <td class="py-2 pr-4 text-right stat-num">${fmt(s.body_fat_pct,1)}%</td>
      <td class="py-2 pr-4 text-right stat-num">${fmt(s.fat_mass_lbs,1)}</td>
      <td class="py-2 pr-4 text-right stat-num">${fmt(s.lean_mass_lbs,1)}</td>
      <td class="py-2 pr-4 text-right stat-num">${fmt(s.vat_lbs,2)}</td>
      <td class="py-2 text-right text-muted">${s.source}</td>
    </tr>
  `).join("") || `<tr><td class="py-3 text-muted" colspan="7">No scans yet.</td></tr>`;
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

function renderRegionalChart() {
  const s = latestScan();
  if (!s) return;
  const labels = ["Arms", "Legs", "Trunk", "Android", "Gynoid"];
  const data   = [s.regions.arms.fat_pct, s.regions.legs.fat_pct, s.regions.trunk.fat_pct, s.regions.android.fat_pct, s.regions.gynoid.fat_pct];
  charts.regional?.destroy();
  charts.regional = new Chart(document.getElementById("chart-regional"), {
    type: "bar",
    data: {
      labels,
      datasets: [{ label: "Fat %", data, backgroundColor: "#22d3ee" }],
    },
    options: { ...baseChartOpts, plugins: { legend: { display: false } } },
  });
}

function renderBalanceChart() {
  const s = latestScan();
  if (!s) return;
  charts.balance?.destroy();
  charts.balance = new Chart(document.getElementById("chart-balance"), {
    type: "bar",
    data: {
      labels: ["Arms", "Legs"],
      datasets: [
        { label: "Right", data: [s.balance.right_arm_lbs, s.balance.right_leg_lbs], backgroundColor: "#22d3ee" },
        { label: "Left",  data: [s.balance.left_arm_lbs,  s.balance.left_leg_lbs],  backgroundColor: "#a78bfa" },
      ],
    },
    options: baseChartOpts,
  });
}

// ---------- Training / Recovery / Activity / Nutrition ----------
function renderProfileStrip() {
  const p = typeof SEED_PROFILE !== "undefined" ? SEED_PROFILE : null;
  const el = document.getElementById("profile-strip");
  if (!el || !p) return;
  el.textContent = `Polar profile · ${p.height_in}" · ${p.profile_weight_lbs} lb · Max HR ${p.max_hr} · Resting HR ${p.resting_hr} · Sleep goal ${p.sleep_goal_h}h`;
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

    document.getElementById("polar-sub").textContent = "Latest: " + (recDates.at(-1) || sleepDates.at(-1) || "—");
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

function renderAll() {
  renderHeader();
  renderProfileStrip();
  renderKPIs();
  renderScale();
  renderHistory();
  renderRegionalChart();
  renderBalanceChart();
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

document.getElementById("btn-add-weight").onclick = () => {
  openModal("Log a weight", `
    <form id="weight-form" class="space-y-4">
      <div><label class="${labelCls}">Date</label><input class="${inputCls}" name="date" type="date" value="${today()}" required></div>
      <div><label class="${labelCls}">Weight (lbs)</label><input class="${inputCls}" name="weight" type="number" step="0.1" min="50" max="500" required></div>
      <div><label class="${labelCls}">Note (optional)</label><input class="${inputCls}" name="note" type="text"></div>
      <div class="flex justify-end gap-2 pt-2">
        <button type="button" id="cancel-weight" class="px-4 py-2 text-sm text-muted">Cancel</button>
        <button class="bg-accent text-ink font-medium px-4 py-2 rounded-lg text-sm">Save</button>
      </div>
    </form>
  `);
  document.getElementById("cancel-weight").onclick = closeModal;
  document.getElementById("weight-form").onsubmit = (e) => {
    e.preventDefault();
    const f = e.target;
    weight = weight.filter(w => w.date !== f.date.value);
    weight.push({ date: f.date.value, weight_lbs: parseFloat(f.weight.value), note: f.note.value });
    save(KEY_WEIGHT, weight);
    closeModal();
    renderAll();
  };
};

document.getElementById("btn-add-scan").onclick = () => {
  openModal("Add DEXA scan", `
    <form id="scan-form" class="space-y-4">
      <div class="grid grid-cols-2 gap-3">
        <div><label class="${labelCls}">Date</label><input class="${inputCls}" name="date" type="date" value="${today()}" required></div>
        <div><label class="${labelCls}">Source</label><input class="${inputCls}" name="source" type="text" value="BodySpec"></div>
        <div><label class="${labelCls}">Weight (lbs)</label><input class="${inputCls}" name="weight" type="number" step="0.1" required></div>
        <div><label class="${labelCls}">Body fat %</label><input class="${inputCls}" name="bf" type="number" step="0.1" required></div>
        <div><label class="${labelCls}">Fat mass (lbs)</label><input class="${inputCls}" name="fat" type="number" step="0.1" required></div>
        <div><label class="${labelCls}">Lean mass (lbs)</label><input class="${inputCls}" name="lean" type="number" step="0.1" required></div>
        <div><label class="${labelCls}">VAT (lbs)</label><input class="${inputCls}" name="vat" type="number" step="0.01" value="0"></div>
        <div><label class="${labelCls}">RMR (cal)</label><input class="${inputCls}" name="rmr" type="number"></div>
      </div>
      <p class="text-xs text-muted">Regional/balance data carries over from your previous scan; you can edit per-scan later by editing localStorage if needed.</p>
      <div class="flex justify-end gap-2 pt-2">
        <button type="button" id="cancel-scan" class="px-4 py-2 text-sm text-muted">Cancel</button>
        <button class="bg-accent text-ink font-medium px-4 py-2 rounded-lg text-sm">Save scan</button>
      </div>
    </form>
  `);
  document.getElementById("cancel-scan").onclick = closeModal;
  document.getElementById("scan-form").onsubmit = (e) => {
    e.preventDefault();
    const f = e.target;
    const prev = latestScan() || {};
    scans.push({
      date: f.date.value,
      source: f.source.value || "Manual",
      height_in: prev.height_in ?? 67.0,
      weight_lbs: parseFloat(f.weight.value),
      body_fat_pct: parseFloat(f.bf.value),
      fat_mass_lbs: parseFloat(f.fat.value),
      lean_mass_lbs: parseFloat(f.lean.value),
      bmc_lbs: prev.bmc_lbs ?? 7.3,
      rmr_cal: parseInt(f.rmr.value || prev.rmr_cal || 1600, 10),
      vat_lbs: parseFloat(f.vat.value || 0),
      ag_ratio: prev.ag_ratio ?? 1.0,
      bone_t_score: prev.bone_t_score ?? 0,
      bone_z_score: prev.bone_z_score ?? 0,
      regions: prev.regions ?? SEED_DEXA[0].regions,
      balance: prev.balance ?? SEED_DEXA[0].balance,
    });
    save(KEY_SCANS, scans);
    weight = weight.filter(w => w.date !== f.date.value);
    weight.push({ date: f.date.value, weight_lbs: parseFloat(f.weight.value), note: "DEXA scan day" });
    save(KEY_WEIGHT, weight);
    closeModal();
    renderAll();
  };
};

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
