/* timing_weather_render.js — v2 Intelligence Dashboard renderer
 * Reads state.json (no-store), polls every 60s, re-renders only when updatedAt changes.
 * Field paths mapped against the live v2 state.json schema (engine.py output).
 */

const State = { lastHash: null, polling: false };

async function loadState() {
  const r = await fetch('state.json', { cache: 'no-store' });
  if (!r.ok) return null;
  return await r.json();
}

function $(id) { return document.getElementById(id); }
function setText(id, val, fallback = '—') {
  const el = $(id);
  if (el) el.textContent = (val === null || val === undefined || val === '') ? fallback : val;
}
function clamp(n) { return Math.max(0, Math.min(100, n)); }

// Whole-day difference between two YYYY-MM-DD strings (b - a), UTC-safe.
function daysBetween(a, b) {
  const da = Date.parse(a + 'T00:00:00Z');
  const db = Date.parse(b + 'T00:00:00Z');
  if (isNaN(da) || isNaN(db)) return null;
  return Math.round((db - da) / 86400000);
}

function renderHero(s) {
  setText('forecast-title', s.forecast);
  setText('forecast-subtitle', s.subtitle);
}

function renderNowBar(s) {
  const nb = s.nowBar || {};
  setText('now-forecast', nb.forecast || s.forecast);
  setText('now-pressure', nb.pressureLevel);
  setText('now-momentum', nb.momentumDirection);
  setText('now-next-event', nb.nextEventDays != null ? `${nb.nextEventDays} Days` : null);
}

function renderPhase(s) {
  // currentPhase is a string; start/end live at the top level.
  setText('phase-name', s.currentPhase);
  const start = s.currentPhaseStart;
  const end = s.currentPhaseEnd;
  setText('phase-range', start && end ? `${start} – ${end}` : null);

  const today = s.currentDate;
  let daysRemaining = null, progress = null;
  if (start && end && today) {
    const total = daysBetween(start, end);
    const elapsed = daysBetween(start, today);
    daysRemaining = daysBetween(today, end);
    if (total && total > 0 && elapsed != null) progress = clamp((elapsed / total) * 100);
  }
  setText('phase-days', daysRemaining != null ? `${Math.max(0, daysRemaining)} Days Remaining` : null);
  const bar = $('phase-progress');
  if (bar) bar.style.width = progress != null ? `${progress}%` : '0%';
}

function renderEventRadar(s) {
  const rings = $('radar-rings');
  if (!rings) return;
  const er = s.eventRadar || {};
  const buckets = [
    { label: 'NEAR', items: er.near || [] },
    { label: 'MID', items: er.mid || [] },
    { label: 'LONG', items: er.long || [] }
  ];
  rings.innerHTML = buckets.map(b => {
    const top = b.items[0];
    return `
    <div class="radar-ring">
      <span class="radar-label">${b.label}</span>
      <span class="radar-value">${top ? `${top.days} Days` : '—'}</span>
      <span class="radar-event">${top ? top.title : ''}</span>
    </div>`;
  }).join('');
}

function renderPlanetInfluences(s) {
  const grid = $('influences-grid');
  if (!grid) return;
  const items = s.planetInfluences || [];
  if (!items.length) { grid.innerHTML = '<div class="card empty">No active influences</div>'; return; }
  grid.innerHTML = items.map(p => `
    <div class="card influence-card influence--${(p.role || '').toLowerCase()}">
      <div class="influence-name">${p.planet || '—'}</div>
      <div class="influence-role">${p.role || ''}</div>
      <div class="influence-score">${p.influence > 0 ? '+' : ''}${p.influence ?? '—'}</div>
      <div class="influence-summary">${p.summary || ''}</div>
    </div>`).join('');
}

function renderUpcomingEvents(s) {
  const ul = $('events-list');
  if (!ul) return;
  const items = (s.upcomingEvents || []).slice(0, 3);
  ul.innerHTML = items.map(e => `
    <li class="event-row">
      <span class="event-title">${e.title}</span>
      <span class="event-theme">${e.theme || ''}</span>
      <span class="event-days">${(e.daysRemaining ?? e.days) ?? '—'} Days</span>
    </li>`).join('');
}

function renderSkyConditions(s) {
  const card = $('sky-card');
  if (!card) return;
  const sk = s.skyConditions || {};
  const metrics = [
    { label: 'Expansion', val: sk.expansion ?? s.opportunity, color: 'positive' },
    { label: 'Pressure', val: sk.pressure ?? s.pressure, color: 'warning' },
    { label: 'Volatility', val: sk.volatility ?? s.volatility, color: 'danger' },
    { label: 'Support', val: sk.support ?? s.momentum, color: 'info' }
  ];
  card.innerHTML = metrics.map(m => `
    <div class="sky-row">
      <span class="sky-label">${m.label}</span>
      <div class="sky-bar"><div class="sky-fill sky-fill--${m.color}" style="width:${clamp(m.val ?? 0)}%"></div></div>
      <span class="sky-value">${m.val != null ? m.val + '%' : '—'}</span>
    </div>`).join('');
}

function renderDailyReading(s) {
  const dr = s.dailyReading || {};
  setText('reading-state', (dr.state || s.forecast || '').toUpperCase());
  setText('reading-body', dr.read || dr.body);
}

function renderWhatChanged(s) {
  const card = $('changed-card');
  if (!card) return;
  const dc = s.dailyChanges;
  if (!dc) {
    card.innerHTML = '<div class="changed-empty">Tracking begins today — deltas appear tomorrow.</div>';
    return;
  }
  const rows = [
    { label: 'Momentum', val: dc.momentum },
    { label: 'Opportunity', val: dc.opportunity },
    { label: 'Pressure', val: dc.pressure },
    { label: 'Volatility', val: dc.volatility }
  ];
  const compared = dc.comparedTo || dc.lastComparedAt;
  card.innerHTML = rows.map(r => {
    if (r.val == null) return `<div class="changed-row"><span class="changed-label">${r.label}</span><span class="changed-val">—</span></div>`;
    const sign = r.val > 0 ? '+' : '';
    const cls = r.val > 0 ? 'changed-pos' : (r.val < 0 ? 'changed-neg' : 'changed-flat');
    return `<div class="changed-row"><span class="changed-label">${r.label}</span><span class="changed-val ${cls}">${sign}${r.val}</span></div>`;
  }).join('') + (compared ? `<div class="changed-footer">Updated vs ${String(compared).slice(0, 10)}</div>` : '');
}

function renderTodaysInsight(s) {
  setText('insight-card', s.todaysInsight);
}

function renderRecommended(s) {
  const dos = $('actions-do');
  const avoids = $('actions-avoid');
  if (dos) dos.innerHTML = (s.recommendations || []).slice(0, 4).map(a => `<li>${a}</li>`).join('');
  if (avoids) avoids.innerHTML = (s.avoidances || []).slice(0, 3).map(a => `<li>${a}</li>`).join('');
}

function renderDrivers(s) {
  const ol = $('drivers-list');
  if (!ol) return;
  const items = (s.drivers || s.topDrivers || []).slice(0, 3);
  ol.innerHTML = items.map(d =>
    `<li class="driver-row"><span class="driver-name">${d.name}</span><span class="driver-score">${d.score > 0 ? '+' : ''}${d.score}</span></li>`
  ).join('');
}

function renderWhy(s) {
  const ev = s.evidence || {};
  setText('expansion-score', ev.expansionScore);
  const rows = $('why-rows');
  if (!rows) return;
  // contributors/reducers use `factor` (not `name`); reducer scores are already negative.
  const pick = (x) => ({ name: x.name ?? x.factor ?? '—', score: x.score });
  const contributors = (ev.contributors || []).map(c => ({ ...pick(c), kind: 'pos' }));
  const reducers = (ev.reducers || []).map(r => ({ ...pick(r), kind: 'neg' }));
  const all = [...contributors, ...reducers]
    .sort((a, b) => Math.abs(b.score) - Math.abs(a.score))
    .slice(0, 5);
  rows.innerHTML = all.map(r =>
    `<div class="why-row why-row--${r.kind}"><span>${r.name}</span><span>${r.score > 0 ? '+' : ''}${r.score}</span></div>`
  ).join('');
}

function renderAll(s) {
  renderHero(s);
  renderNowBar(s);
  renderPhase(s);
  renderEventRadar(s);
  renderPlanetInfluences(s);
  renderUpcomingEvents(s);
  renderSkyConditions(s);
  renderDailyReading(s);
  renderWhatChanged(s);
  renderTodaysInsight(s);
  renderRecommended(s);
  renderDrivers(s);
  renderWhy(s);
  // Confidence stays "Not Rated" — static in HTML/CSS; no JS bind required.
}

async function tick() {
  if (State.polling) return;
  State.polling = true;
  try {
    const s = await loadState();
    if (!s) return;
    const hash = JSON.stringify({ u: s.updatedAt, h: s.data_hash });
    if (hash === State.lastHash) return;
    State.lastHash = hash;
    renderAll(s);
  } finally { State.polling = false; }
}

tick();
setInterval(tick, 60000);
