/* timing_weather_render.js — v2.2 "Ambient Intelligence" renderer
 * Reads state.json (no-store), polls every 60s, re-renders only when updatedAt changes.
 * Bound to the v2.2 row-structure layout: header chrome (title + short date),
 * hero corner rings, photographic sun core, timeline proximity bars, compact
 * planet influences. Current Phase dropped (not in mockup). v2 engine/schema unchanged.
 * PVR: null fields degrade to "—" or an empty state — never fabricate values.
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

/* ── Header chrome — short date in the title bar ──────────────────────────────
   "Sun · Jun 7". Prefer state.currentDate (YYYY-MM-DD, parsed UTC-safe to dodge
   the timezone off-by-one); fall back to the client clock when the field is absent. */
const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

function formatHeaderDate(iso) {
  if (iso && /^\d{4}-\d{2}-\d{2}/.test(iso)) {
    const [y, m, day] = iso.slice(0, 10).split('-').map(Number);
    const d = new Date(Date.UTC(y, m - 1, day));
    return `${WEEKDAYS[d.getUTCDay()]} · ${MONTHS[d.getUTCMonth()]} ${d.getUTCDate()}`;
  }
  const d = new Date();
  return `${WEEKDAYS[d.getDay()]} · ${MONTHS[d.getMonth()]} ${d.getDate()}`;
}

function renderHeaderDate(s) {
  setText('header-date', formatHeaderDate(s && s.currentDate));
}

/* ── Hero corner rings ───────────────────────────────────────────────────────
   CSS expects .corner-value wrapped in a .corner-ring whose --ring-pct (0–100)
   drives the conic arc. Per-corner hue is set in CSS, so we only set the pct. */
function ensureRing(valueEl) {
  if (!valueEl) return null;
  let ring = valueEl.closest('.corner-ring');
  if (!ring) {
    ring = document.createElement('div');
    ring.className = 'corner-ring';
    valueEl.parentNode.insertBefore(ring, valueEl);
    ring.appendChild(valueEl);
  }
  return ring;
}

function bindCornerRing(key, value, tag) {
  const idMap = {
    opportunity: 'hero-opportunity',
    pressure: 'hero-pressure',
    momentum: 'hero-momentum',
    'next-event': 'hero-next-event-days'
  };
  const tagMap = {
    opportunity: 'hero-opportunity-tag',
    pressure: 'hero-pressure-tag',
    momentum: 'hero-momentum-tag',
    'next-event': 'hero-next-event-label'
  };
  const valueEl = $(idMap[key]);
  setText(idMap[key], value);
  const ring = ensureRing(valueEl);
  if (ring) {
    if (value == null) {
      ring.style.setProperty('--ring-pct', 0);
    } else {
      let pct = value;
      // Next-event inverts: 0 days = full ring, 365 days = empty.
      if (key === 'next-event') pct = 100 - (value * 100 / 365);
      ring.style.setProperty('--ring-pct', clamp(pct));
    }
  }
  if (tagMap[key]) setText(tagMap[key], tag);
}

function deriveTag(val) {
  if (val == null) return '—';
  if (val >= 75) return 'High';
  if (val >= 50) return 'Moderate';
  return 'Low';
}
function derivePressureTag(val) {
  if (val == null) return '—';
  if (val >= 70) return 'High';
  if (val >= 40) return 'Medium';
  return 'Low';
}
function deriveMomentumTag(s) {
  const dir = s.nowBar && s.nowBar.momentumDirection;
  if (!dir) return '—';
  const arrow = dir.includes('Ris') ? '↗' : dir.includes('Fall') ? '↘' : '→';
  return `${arrow} ${dir}`;
}

function renderHero(s) {
  setText('forecast-title', s.forecast);
  setText('forecast-subtitle', s.subtitle);
  bindCornerRing('opportunity', s.opportunity, deriveTag(s.opportunity));
  bindCornerRing('pressure', s.pressure, derivePressureTag(s.pressure));
  bindCornerRing('momentum', s.momentum, deriveMomentumTag(s));
  bindCornerRing('next-event', (s.nowBar && s.nowBar.nextEventDays != null) ? s.nowBar.nextEventDays : null, 'Days');
}

function renderNowBar(s) {
  const nb = s.nowBar || {};
  setText('now-forecast', nb.forecast || s.forecast);
  setText('now-pressure', nb.pressureLevel);
  setText('now-momentum', nb.momentumDirection);
  setText('now-next-event', nb.nextEventDays != null ? `${nb.nextEventDays} Days` : null);
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
    if (r.val == null) {
      return `<div class="changed-row"><span class="changed-label">${r.label}</span><span class="changed-delta neutral">—</span></div>`;
    }
    const sign = r.val > 0 ? '+' : '';
    const cls = r.val > 0 ? 'positive' : (r.val < 0 ? 'negative' : 'neutral');
    return `<div class="changed-row"><span class="changed-label">${r.label}</span><span class="changed-delta ${cls}">${sign}${r.val}</span></div>`;
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

/* ── Upcoming Conditions — gold proximity bars (longer = sooner) ───────────── */
function renderTimeline(s) {
  const ul = $('timeline-list');
  if (!ul) return;

  let events = [];
  if (s.upcomingEvents && s.upcomingEvents.length) {
    events = s.upcomingEvents.slice();
  } else if (s.eventRadar) {
    ['near', 'mid', 'long'].forEach(bucket => {
      (s.eventRadar[bucket] || []).slice(0, 1).forEach(e => events.push(e));
    });
  }

  const top3 = events.slice(0, 3);
  if (!top3.length) { ul.innerHTML = '<li class="timeline-empty">No upcoming events</li>'; return; }

  const dayOf = e => (e.daysRemaining != null ? e.daysRemaining : (e.days != null ? e.days : 365));
  const maxDays = Math.max(...top3.map(dayOf)) || 1;

  ul.innerHTML = top3.map(e => {
    const days = dayOf(e);
    const length = Math.max(15, 100 - (days / maxDays * 80)); // closer = fuller
    const title = e.title || e.name || '—';
    return `
      <li class="timeline-row">
        <div class="timeline-days">${days}<span class="unit">Days</span></div>
        <div class="timeline-main">
          <div class="timeline-event">${title}</div>
          <div class="timeline-bar" style="--bar-length: ${length}%"></div>
        </div>
      </li>`;
  }).join('');
}

/* Current Phase section removed in v2.2 (not in mockup). The engine still emits
   currentPhase / currentPhaseStart / currentPhaseEnd in state.json — intentionally
   unread here; the DOM hooks (phase-name/range/progress/days) no longer exist. */

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
      <span class="sky-name">${m.label}</span>
      <div class="sky-bar"><div class="sky-fill sky-fill--${m.color}" style="width:${clamp(m.val ?? 0)}%"></div></div>
      <span class="sky-value">${m.val != null ? m.val + '%' : '—'}</span>
    </div>`).join('');
}

/* ── Planet Influences — compact rows (glyph · name · role · score) ─────────── */
function renderInfluences(s) {
  const ul = $('influences-grid');
  if (!ul) return;
  const items = s.planetInfluences || [];
  if (!items.length) { ul.innerHTML = '<li class="influence-row">No active influences</li>'; return; }
  const glyphMap = {
    Jupiter: '♃', Venus: '♀', Saturn: '♄', Mars: '♂', Mercury: '☿',
    Sun: '☉', Moon: '☽', Uranus: '♅', Neptune: '♆', Pluto: '♇'
  };
  ul.innerHTML = items.slice(0, 4).map(p => {
    const sign = p.influence > 0 ? '+' : '';
    const cls = p.influence > 0 ? 'positive' : (p.influence < 0 ? 'negative' : '');
    return `
      <li class="influence-row">
        <span class="influence-glyph">${glyphMap[p.planet] || '★'}</span>
        <span class="influence-name">${p.planet || '—'}</span>
        <span class="influence-role">${p.role || ''}</span>
        <span class="influence-score ${cls}">${sign}${p.influence ?? '—'}</span>
      </li>`;
  }).join('');
}

function renderDrivers(s) {
  const ol = $('drivers-list');
  if (!ol) return;
  const items = (s.drivers || s.topDrivers || []).slice(0, 3);
  ol.innerHTML = items.map(d => {
    const sign = d.score > 0 ? '+' : '';
    return `<li><span class="driver-name">${d.name || '—'}</span><span class="driver-score" style="float:right;color:var(--gold);font-weight:700;font-variant-numeric:tabular-nums">${sign}${d.score ?? '—'}</span></li>`;
  }).join('');
}

function renderWhy(s) {
  const ev = s.evidence || {};
  setText('expansion-score', ev.expansionScore);
  // Inline-not-collapsed: open the <details> by default (per v2.1 spec).
  const details = document.querySelector('.why-card');
  if (details && details.tagName === 'DETAILS') details.setAttribute('open', '');

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
    `<div class="why-row why-row--${r.kind}"><span>${r.name}</span><span class="why-weight">${r.score > 0 ? '+' : ''}${r.score}</span></div>`
  ).join('');
}

function renderAll(s) {
  renderHeaderDate(s);
  renderHero(s);
  renderNowBar(s);
  renderDailyReading(s);
  renderWhatChanged(s);
  renderTodaysInsight(s);
  renderRecommended(s);
  renderTimeline(s);
  renderSkyConditions(s);
  renderInfluences(s);
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
