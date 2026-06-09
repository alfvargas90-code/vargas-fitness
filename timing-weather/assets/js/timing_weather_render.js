/* timing_weather_render.js — v3.0 "Ambient Intelligence OS" renderer
 * Reads state.json (no-store + ?t cache-bust), polls every 60s, re-renders only
 * when updatedAt changes. Bound to the v3.0 DOM:
 *   Hero → Consensus → Snapshots → Drawers → What Changed → Today's Insight →
 *   Recommended → Upcoming → Sky → Planet → Drivers → Why → Confidence → Footer.
 * The long-form essays moved from visible page sections into the Modern +
 * Traditional Analysis Drawers (Today + Month tabs; Quarter + Year are placeholder
 * "Coming Soon" tabs wired in v3.1). Vedic still emits in state.json but is not
 * surfaced on Home (v3.2 Reports tab consumes it).
 * PVR: null fields degrade to "—" or an empty state — never fabricate values.
 */

const State = { lastHash: null, polling: false };

async function loadState() {
  // Hard cache-bust — a home-screen PWA must never pin a stale state.json.
  const r = await fetch(`state.json?t=${Date.now()}`, { cache: 'no-store' });
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

/* Live Moon position as a compact hero subtitle line.
   Format: "Moon · Pisces 25° · 2H trop / 4H ved · Purva Bhadrapada".
   PVR: moonNow === null → empty content → CSS `.hero-moon:empty` hides it. */
function renderMoonNow(s) {
  const el = $('hero-moon');
  if (!el) return;
  const mn = s.moonNow;
  if (!mn) { el.textContent = ''; return; }
  const trop = mn.tropical || {};
  const ved = mn.vedic || {};
  const tropSign = trop.sign || '—';
  const tropDeg = trop.degree != null ? Math.round(trop.degree) : '—';
  const tropHouse = trop.house != null ? trop.house : '—';
  const vedHouse = ved.house != null ? ved.house : '—';
  const nak = ved.nakshatra || '—';
  el.textContent =
    `Moon · ${tropSign} ${tropDeg}° · ${tropHouse}H trop / ${vedHouse}H ved · ${nak}`;
}

/* ── 2 · System Consensus — Modern | agreement% | Traditional + action ────────
   data-status drives the pill color (CSS: .consensus-status[data-status=...]). */
function renderConsensus(s) {
  const c = s.consensus || {};
  setText('consensus-modern-state', c.modernState);
  setText('consensus-traditional-state', c.traditionalState);
  setText('consensus-pct', c.agreementPct != null ? `${c.agreementPct}%` : null);
  setText('consensus-action', c.primaryAction);

  const pill = $('consensus-status');
  if (pill) {
    const status = c.status || '';
    pill.textContent = status ? status.toUpperCase() : '—';
    if (status) pill.setAttribute('data-status', status);
    else pill.removeAttribute('data-status');
  }
}

/* ── 3 · Intelligence Snapshots — Modern + Traditional compact <dl> rows ──────
   PVR: any null field renders "—". */
function renderSnapshots(s) {
  const snaps = s.snapshots || {};
  ['modern', 'traditional'].forEach(sys => {
    const snap = snaps[sys] || {};
    setText(`snap-${sys}-theme`, snap.theme);
    setText(`snap-${sys}-driver`, snap.driver);
    setText(`snap-${sys}-opportunity`, snap.opportunity);
    setText(`snap-${sys}-pressure`, snap.pressure);
    setText(`snap-${sys}-action`, snap.action);
  });
}

/* ── 4 · Analysis Drawer panels ───────────────────────────────────────────────
   Modern ← tropical{Reading,Monthly}; Traditional ← traditional{Reading,Monthly}.
   PVR: a missing reading shows "—" for both state + body. */
function applyDrawerPanel(reading, stateId, bodyId, fallbackState) {
  const r = reading || {};
  const stateVal = r.state ? String(r.state).toUpperCase() : (fallbackState ? String(fallbackState).toUpperCase() : null);
  setText(stateId, stateVal);
  setText(bodyId, r.body || r.read);
}

function renderDrawerContent(s) {
  applyDrawerPanel(s.tropicalReading,    'drawer-modern-today-state',      'drawer-modern-today-body',      s.forecast);
  applyDrawerPanel(s.tropicalMonthly,    'drawer-modern-month-state',      'drawer-modern-month-body',      s.forecast);
  applyDrawerPanel(s.traditionalReading, 'drawer-traditional-today-state', 'drawer-traditional-today-body', s.forecast);
  applyDrawerPanel(s.traditionalMonthly, 'drawer-traditional-month-state', 'drawer-traditional-month-body', s.forecast);
}

/* ── 5 · What Changed — delta rows ──────────────────────────────────────────── */
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
    // The +/- sign is supplied by CSS ::before on .positive/.negative — emit the magnitude only.
    const cls = r.val > 0 ? 'positive' : (r.val < 0 ? 'negative' : 'neutral');
    const mag = r.val === 0 ? '0' : Math.abs(r.val);
    return `<div class="changed-row"><span class="changed-label">${r.label}</span><span class="changed-delta ${cls}">${mag}</span></div>`;
  }).join('') + (compared ? `<div class="changed-footer">Updated vs ${String(compared).slice(0, 10)}</div>` : '');
}

/* ── 6 · Today's Insight ─────────────────────────────────────────────────────── */
function renderTodaysInsight(s) {
  setText('insight-card', s.todaysInsight);
}

/* ── 7 · Recommended Actions — Do (max 4) / Avoid (max 3) ─────────────────────── */
function renderRecommended(s) {
  const dos = $('actions-do');
  const avoids = $('actions-avoid');
  if (dos) dos.innerHTML = (s.recommendations || []).slice(0, 4).map(a => `<li>${a}</li>`).join('');
  if (avoids) avoids.innerHTML = (s.avoidances || []).slice(0, 3).map(a => `<li>${a}</li>`).join('');
}

/* ── 8 · Upcoming Conditions — proximity bars + importance tier ────────────────
   Tier by rank: 1st = highest (gold), 2nd = medium (purple), 3rd = lower (blue). */
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
  const tiers = ['high', 'medium', 'low'];

  ul.innerHTML = top3.map((e, i) => {
    const days = dayOf(e);
    const length = Math.max(15, 100 - (days / maxDays * 80)); // closer = fuller
    const title = e.title || e.name || '—';
    const tier = tiers[i] || 'low';
    return `
      <li class="timeline-row">
        <div class="timeline-days">${days}<span class="unit">Days</span></div>
        <div class="timeline-main">
          <div class="timeline-event">${title}</div>
          <div class="timeline-bar timeline-bar--${tier}" style="--bar-length: ${length}%"></div>
        </div>
      </li>`;
  }).join('');
}

/* ── 9 · Sky Conditions — labeled horizontal bars ─────────────────────────────── */
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

/* ── 10 · Planet Influences — compact rows (glyph · name · role · score) ─────── */
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

/* ── 11 · Top Drivers — top 3 ──────────────────────────────────────────────────── */
function renderDrivers(s) {
  const ol = $('drivers-list');
  if (!ol) return;
  const items = (s.drivers || s.topDrivers || []).slice(0, 3);
  ol.innerHTML = items.map(d => {
    const sign = d.score > 0 ? '+' : '';
    return `<li><span class="driver-name">${d.name || '—'}</span><span class="driver-score" style="float:right;color:var(--color-gold);font-weight:700;font-variant-numeric:tabular-nums">${sign}${d.score ?? '—'}</span></li>`;
  }).join('');
}

/* ── 12 · Why This Forecast — score + top 5 contributors/reducers by magnitude ── */
function renderWhy(s) {
  const ev = s.evidence || {};
  setText('expansion-score', ev.expansionScore);
  // Inline-not-collapsed: open the <details> by default (per spec).
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

/* ════════════════════════════════════════════════════════════════════════════
   DRAWER INTERACTIONS — open/close + tab switching + body scroll lock + a11y.
   The drawer is a modal: aria-modal="true" when open, focus moved inside, Tab is
   trapped, ESC + scrim-click + close-button all dismiss and restore opener focus.
   The scrim is a CSS ::before pseudo on the drawer, so an outside-click registers
   as a click whose target IS the drawer element itself (dialog-backdrop pattern).
   ════════════════════════════════════════════════════════════════════════════ */
const Drawer = { open: null, opener: null };

function focusables(root) {
  return Array.from(root.querySelectorAll(
    'button:not([disabled]), [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
  )).filter(el => el.offsetParent !== null || el === document.activeElement);
}

function openDrawer(name, opener) {
  const drawer = document.querySelector(`[data-drawer="${name}"]`);
  if (!drawer) return;
  if (Drawer.open && Drawer.open !== drawer) closeDrawer();
  drawer.hidden = false;
  drawer.setAttribute('aria-modal', 'true');
  document.body.style.overflow = 'hidden';
  Drawer.open = drawer;
  Drawer.opener = opener || null;
  const closeBtn = drawer.querySelector('[data-drawer-close]');
  if (closeBtn) closeBtn.focus();
}

function closeDrawer() {
  const drawer = Drawer.open;
  if (!drawer) return;
  drawer.hidden = true;
  drawer.setAttribute('aria-modal', 'false');
  document.body.style.overflow = '';
  const opener = Drawer.opener;
  Drawer.open = null;
  Drawer.opener = null;
  if (opener && typeof opener.focus === 'function') opener.focus();
}

function switchTab(drawer, tab) {
  if (!drawer || !tab || tab.disabled || tab.getAttribute('aria-selected') === 'true') return;
  const tablist = tab.closest('[role="tablist"]');
  if (tablist) {
    tablist.querySelectorAll('[role="tab"]').forEach(t =>
      t.setAttribute('aria-selected', t === tab ? 'true' : 'false'));
  }
  const target = tab.getAttribute('data-tab');
  drawer.querySelectorAll('[data-panel]').forEach(panel => {
    panel.hidden = panel.getAttribute('data-panel') !== target;
  });
}

function bindDrawerInteractions() {
  // Open
  document.querySelectorAll('[data-drawer-open]').forEach(btn => {
    btn.addEventListener('click', () => openDrawer(btn.getAttribute('data-drawer-open'), btn));
  });
  // Per-drawer: close button, scrim outside-click, tab switching
  document.querySelectorAll('[data-drawer]').forEach(drawer => {
    drawer.querySelectorAll('[data-drawer-close]').forEach(btn =>
      btn.addEventListener('click', closeDrawer));
    // Scrim is the drawer's own ::before — clicking it lands on the drawer element.
    drawer.addEventListener('click', e => { if (e.target === drawer) closeDrawer(); });
    drawer.querySelectorAll('[role="tab"]').forEach(tab =>
      tab.addEventListener('click', () => switchTab(drawer, tab)));
  });
  // Global key handling — ESC closes, Tab is trapped inside the open drawer.
  document.addEventListener('keydown', e => {
    if (!Drawer.open) return;
    if (e.key === 'Escape') { e.preventDefault(); closeDrawer(); return; }
    if (e.key === 'Tab') {
      const items = focusables(Drawer.open);
      if (!items.length) return;
      const first = items[0], last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
  });
}

/* ── Footer Coming-Soon nav — inert tap shows a 2s toast, no navigation ───────── */
let toastTimer = null;
function showToast(msg) {
  let toast = $('tw-toast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'tw-toast';
    toast.setAttribute('role', 'status');
    toast.style.cssText = [
      'position:fixed', 'left:50%', 'bottom:84px', 'transform:translateX(-50%)',
      'z-index:200', 'padding:10px 18px', 'border-radius:999px',
      'background:rgba(6,7,10,0.95)', 'border:1px solid rgba(212,168,87,0.35)',
      'color:#e8c573', 'font:600 13px/1.2 -apple-system,BlinkMacSystemFont,system-ui,sans-serif',
      'letter-spacing:0.02em', 'box-shadow:0 12px 40px rgba(0,0,0,0.5)',
      'opacity:0', 'transition:opacity 0.2s ease', 'pointer-events:none'
    ].join(';');
    document.body.appendChild(toast);
  }
  toast.textContent = msg;
  requestAnimationFrame(() => { toast.style.opacity = '1'; });
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { toast.style.opacity = '0'; }, 2000);
}

function bindFooterNav() {
  document.querySelectorAll('.nav-item--soon').forEach(item => {
    item.addEventListener('click', e => {
      e.preventDefault();
      const label = (item.textContent || 'This view').trim();
      showToast(`${label} · Coming in v3.1`);
    });
  });
}

/* ════════════════════════════════════════════════════════════════════════════
   RENDER + POLL
   ════════════════════════════════════════════════════════════════════════════ */
function renderAll(s) {
  renderHeaderDate(s);
  renderHero(s);
  renderMoonNow(s);
  renderConsensus(s);
  renderSnapshots(s);
  renderDrawerContent(s);
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

// One-time interaction wiring (independent of state polling).
bindDrawerInteractions();
bindFooterNav();

tick();
setInterval(tick, 60000);
