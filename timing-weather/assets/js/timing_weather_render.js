/* Timing Weather — v1.1 render module.
 * PURE render functions only: each takes the engine state object and returns an
 * HTML string. No fetching, no polling, no DOM mutation, no business logic — the
 * engine wrapper (timing_weather_engine.js) owns all of that. Every value traces
 * back to a state.json field; missing/null degrades to "—" or a hidden block
 * (PVR law — never fabricate a value here).
 *
 * Exposed as window.TWRender = { ...cardFns, helpers }.
 */
(function () {
  "use strict";

  // ── helpers ──────────────────────────────────────────────────────────
  var dash = function (v) { return (v === null || v === undefined || v === "") ? "—" : v; };
  var esc = function (s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  };

  var PLANET_GLYPH = {
    Sun: "☉", Moon: "☽", Mercury: "☿", Venus: "♀", Mars: "♂",
    Jupiter: "♃", Saturn: "♄", Uranus: "♅", Neptune: "♆", Pluto: "♇"
  };
  // Spec color coding — only the 5 named planets get a class; others fall back to gold.
  var PLANET_CLASS = {
    Jupiter: "p-jupiter", Venus: "p-venus", Saturn: "p-saturn",
    Uranus: "p-uranus", Mars: "p-mars"
  };

  function planetBadge(name) {
    if (!name) return '<span class="muted">—</span>';
    var cls = PLANET_CLASS[name] || "gold";
    var g = PLANET_GLYPH[name] || "";
    return '<span class="planet-badge ' + cls + '">' + esc(name) +
           (g ? ' <span class="glyph">' + g + "</span>" : "") + "</span>";
  }

  function fmtDayMon(iso) {
    if (!iso) return "—";
    var d = new Date(iso + "T00:00:00");
    if (isNaN(d)) return "—";
    return d.toLocaleDateString([], { month: "short", day: "numeric" });
  }
  function fmtLongDate(iso) {
    if (!iso) return "—";
    var d = new Date(iso + "T00:00:00");
    if (isNaN(d)) return "—";
    return d.toLocaleDateString([], { year: "numeric", month: "long", day: "numeric" });
  }
  function fmtStamp(iso) {
    if (!iso) return "—";
    var d = new Date(iso);
    if (isNaN(d)) return "—";
    return d.toLocaleString([], { year: "numeric", month: "short", day: "numeric",
      hour: "numeric", minute: "2-digit" });
  }

  // ── Header + Hero + Forecast Title ───────────────────────────────────
  function header() {
    return '<div class="header-label">Timing Weather</div>';
  }
  function hero(s) {
    return '<div class="sun-hero" role="img" aria-label="Forecast: ' +
           esc(s.forecast || "") + '"></div>';
  }
  function forecastTitle(s) {
    return '<h1 class="forecast-title">' + esc(dash(s.forecast)) + "</h1>" +
           '<p class="forecast-subtitle">' + esc(s.subtitle || "") + "</p>";
  }

  // ── Current Phase ────────────────────────────────────────────────────
  function currentPhase(s) {
    var range = (s.currentPhaseStart || s.currentPhaseEnd)
      ? fmtLongShort(s.currentPhaseStart) + " – " + fmtLongShort(s.currentPhaseEnd)
      : "—";
    return '<div class="card">' +
      '<div class="section-heading">Current Phase</div>' +
      '<div class="phase-body">' +
        '<div class="phase-main">' +
          '<div class="phase-icon">◐</div>' +
          '<div>' +
            '<div class="phase-name">' + esc(dash(s.currentPhase)) + "</div>" +
            '<div class="phase-range">' + range + "</div>" +
          "</div>" +
        "</div>" +
        '<div class="cal-icon">📅</div>' +
      "</div>" +
    "</div>";
  }
  function fmtLongShort(iso) {
    if (!iso) return "—";
    var d = new Date(iso + "T00:00:00");
    if (isNaN(d)) return "—";
    return d.toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" });
  }

  // ── Forecast Card (6 rows) ───────────────────────────────────────────
  var CONF_CLASS = { High: "m-green", Medium: "m-orange", Low: "m-red" };
  function forecastCard(s) {
    var dur = s.durationDays == null ? "—"
      : s.durationDays + " day" + (s.durationDays === 1 ? "" : "s");
    var conf = s.confidence == null
      ? '<span class="muted">Not Rated</span>'
      : '<span class="' + (CONF_CLASS[s.confidence] || "") + '" style="font-weight:700">' +
        esc(s.confidence) + "</span>";
    var rows = [
      ["Forecast", '<span class="gold" style="font-weight:700">' + esc(dash(s.forecast)) + "</span>"],
      ["Dominant", planetBadge(s.dominantPlanet)],
      ["Supporting", planetBadge(s.supportingPlanet)],
      ["Pressure Source", planetBadge(s.pressurePlanet)],
      ["Confidence", conf],
      ["Duration", '<span class="tab-num">' + dur + "</span>"]
    ];
    return '<div class="card">' + rows.map(function (r) {
      return '<div class="tw-row"><span class="row-label">' + r[0] +
             '</span><span class="row-value">' + r[1] + "</span></div>";
    }).join("") + "</div>";
  }

  // ── Active Sky (4 mini-cards) ────────────────────────────────────────
  function activeSky(s) {
    var defs = [
      [s.dominantPlanet, "Dominant"],
      [s.supportingPlanet, "Supporting"],
      [s.pressurePlanet, "Pressure"],
      [s.volatilityPlanet, "Volatility"]
    ];
    var cards = defs.map(function (d) {
      var name = d[0], role = d[1];
      var cls = name ? (PLANET_CLASS[name] || "gold") : "muted";
      var g = name ? (PLANET_GLYPH[name] || "•") : "•";
      return '<div class="sky-mini">' +
        '<div class="sym ' + cls + '">' + g + "</div>" +
        '<div class="name ' + cls + '">' + esc(dash(name)) + "</div>" +
        '<div class="role">' + role + "</div>" +
      "</div>";
    }).join("");
    var foot = s.updatedAt ? "Updated " + fmtStamp(s.updatedAt) : "";
    return '<div class="card">' +
      '<div class="section-heading">Active Sky</div>' +
      '<div class="sky-grid">' + cards + "</div>" +
      (foot ? '<div class="sky-footer">' + esc(foot) + "</div>" : "") +
    "</div>";
  }

  // ── Top Drivers ──────────────────────────────────────────────────────
  function topDrivers(s) {
    var drivers = s.drivers || [];
    if (!drivers.length) return "";
    var rows = drivers.map(function (d, i) {
      return '<div class="driver-row">' +
        '<span class="driver-name"><span class="num tab-num">' + (i + 1) + ".</span>" +
          esc(dash(d.name)) + "</span>" +
        '<span class="driver-score tab-num">+' + esc(d.score) + "</span>" +
      "</div>";
    }).join("");
    return '<div class="card">' +
      '<div class="section-heading">Top Drivers</div>' + rows +
      '<div class="drivers-footer"><span>View all drivers</span><span>›</span></div>' +
    "</div>";
  }

  // ── Forecast Trend ───────────────────────────────────────────────────
  var DIR = {
    Strengthening: { cls: "dir-up", arrow: "↗" },
    Stable:        { cls: "dir-flat", arrow: "→" },
    Weakening:     { cls: "dir-down", arrow: "↘" }
  };
  function trendChartSVG(pts) {
    // small polyline from opportunity-ordinal of each label state (0..4)
    var ORD = { NEUTRAL: 0, PRESSURE: 1, CONSOLIDATION: 2, TRANSITION: 2, TRANSFORMATION: 3, EXPANSION: 4 };
    var n = pts.length;
    if (n < 2) return "";
    var W = 120, H = 64, pad = 6;
    var coords = pts.map(function (p, i) {
      var o = ORD[p.state] != null ? ORD[p.state] : 0;
      var x = pad + (W - 2 * pad) * (i / (n - 1));
      var y = H - pad - (H - 2 * pad) * (o / 4);
      return x.toFixed(1) + "," + y.toFixed(1);
    });
    var last = coords[coords.length - 1].split(",");
    return '<svg viewBox="0 0 ' + W + " " + H + '" preserveAspectRatio="none" aria-hidden="true">' +
      '<polyline fill="none" stroke="#D4AF37" stroke-width="2" stroke-linecap="round" ' +
      'stroke-linejoin="round" points="' + coords.join(" ") + '"/>' +
      '<circle cx="' + last[0] + '" cy="' + last[1] + '" r="3" fill="#F4C542"/>' +
    "</svg>";
  }
  function forecastTrend(s) {
    var pts = s.forecastTrend || [];
    if (pts.length < 2) return "";
    var list = pts.map(function (p) {
      return '<div class="trend-item"><span class="t-date tab-num">' + fmtDayMon(p.date) +
             '</span><span class="t-state">' + esc(dash(p.state)) + "</span></div>";
    }).join("");
    var d = DIR[s.trendDirection];
    var dirHTML = s.trendDirection
      ? 'Direction: <span class="dir-val ' + (d ? d.cls : "") + '">' +
        esc(s.trendDirection) + (d ? " " + d.arrow : "") + "</span>"
      : 'Direction: <span class="muted">—</span>';
    return '<div class="card">' +
      '<div class="section-heading">Forecast Trend</div>' +
      '<div class="trend-body">' +
        '<div class="trend-list">' + list + "</div>" +
        '<div class="trend-chart">' + trendChartSVG(pts) + "</div>" +
      "</div>" +
      '<div class="trend-direction">' + dirHTML + "</div>" +
    "</div>";
  }

  // ── Next Major Window ────────────────────────────────────────────────
  function nextMajorWindow(s) {
    var w = s.nextWindow;
    if (!w) return "";
    var strength = (w.strength == null) ? "" :
      '<span><b>' + w.strength.toFixed(1) + "</b> / 10</span>";
    var cat = w.category ? '<span>Category <b>' + esc(w.category) + "</b></span>" : "";
    var days = (w.daysRemaining == null) ? "—" : w.daysRemaining;
    return '<div class="card">' +
      '<div class="section-heading">Next Major Window</div>' +
      '<div class="nmw-top">' +
        '<div class="nmw-cal">📅</div>' +
        '<div>' +
          '<div class="nmw-title">' + esc(dash(w.title)) + "</div>" +
          '<div class="nmw-date">' + fmtLongDate(w.date) + "</div>" +
        "</div>" +
        '<div class="nmw-count"><div class="n tab-num">' + days +
          '</div><div class="lbl">Days Remaining</div></div>' +
      "</div>" +
      ((strength || cat) ? '<div class="nmw-footer">' + strength + cat + "</div>" : "") +
    "</div>";
  }

  // ── Weather Metrics ──────────────────────────────────────────────────
  var METRICS = [
    { key: "opportunity", label: "Opportunity", cls: "m-green", bar: "bar-green" },
    { key: "pressure",    label: "Pressure",    cls: "m-red",   bar: "bar-red" },
    { key: "volatility",  label: "Volatility",  cls: "m-orange",bar: "bar-orange" },
    { key: "momentum",    label: "Momentum",    cls: "m-blue",  bar: "bar-blue" }
  ];
  function weatherMetrics(s) {
    var cards = METRICS.map(function (m) {
      var v = s[m.key];
      var num = (v == null) ? "—" : v;
      var pct = (v == null) ? 0 : Math.max(0, Math.min(100, v));
      return '<div class="metric-mini">' +
        '<div class="m-label">' + m.label + "</div>" +
        '<div class="m-num tab-num ' + m.cls + '">' + num + "</div>" +
        '<div class="metric-bar"><span class="' + m.bar + '" style="width:' + pct + '%"></span></div>' +
      "</div>";
    }).join("");
    return '<div class="card">' +
      '<div class="section-heading">Weather Metrics</div>' +
      '<div class="metrics-grid">' + cards + "</div>" +
    "</div>";
  }

  // ── Recommended Actions ──────────────────────────────────────────────
  function recommendedActions(s) {
    var recs = s.recommendations || [];
    var avoid = s.avoidances || [];
    if (!recs.length && !avoid.length) return "";
    var doItems = recs.map(function (r) {
      return '<div class="action-item do"><span class="mark">✓</span><span>' + esc(r) + "</span></div>";
    }).join("");
    var avoidItems = avoid.map(function (a) {
      return '<div class="action-item avoid"><span class="mark">✕</span><span>' + esc(a) + "</span></div>";
    }).join("");
    return '<div class="card">' +
      '<div class="section-heading">Recommended Actions</div>' +
      (recs.length ? '<div class="actions-sub do">Do More Of</div>' + doItems : "") +
      (avoid.length ? '<div class="actions-sub avoid">Avoid</div>' + avoidItems : "") +
    "</div>";
  }

  // ── Why This Forecast (nested evidence contract) ─────────────────────
  function whyForecast(s) {
    var ev = s.evidence;
    if (!ev || typeof ev !== "object") return "";
    var contributors = ev.contributors || [];
    var reducers = ev.reducers || [];
    if (!contributors.length && !reducers.length) return "";
    function line(f, pos) {
      var sign = pos ? "+" : "−";
      return '<div class="why-line"><span>' + esc(dash(f.factor)) +
        '</span><span class="sc ' + (pos ? "pos" : "neg") + ' tab-num">' +
        sign + Math.abs(f.score) + "</span></div>";
    }
    var score = (ev.expansionScore == null) ? "—" : ev.expansionScore;
    return '<div class="card">' +
      '<div class="section-heading">Why This Forecast</div>' +
      '<div class="card-inner">' +
        '<div class="why-score"><span class="lbl">Expansion Score</span><span class="val tab-num">' +
          score + "</span></div>" +
        (contributors.length ? '<div class="why-block"><div class="why-h">Contributors</div>' +
          contributors.map(function (f) { return line(f, true); }).join("") + "</div>" : "") +
        (reducers.length ? '<div class="why-block"><div class="why-h">Reducers</div>' +
          reducers.map(function (f) { return line(f, false); }).join("") + "</div>" : "") +
      "</div>" +
    "</div>";
  }

  // ── Guidance (narrative) ─────────────────────────────────────────────
  function guidance(s) {
    var text = s.narrative || "Narrative computation pending.";
    return '<div class="card">' +
      '<div class="section-heading">Guidance</div>' +
      '<p class="guidance-text">' + esc(text) + "</p>" +
    "</div>";
  }

  // ── Timestamp footer ─────────────────────────────────────────────────
  function timestamp(s) {
    var src = s.sourceMode ? (s.sourceMode.charAt(0).toUpperCase() + s.sourceMode.slice(1)) : "Static";
    var when = s.updatedAt ? "Updated " + fmtStamp(s.updatedAt) : "—";
    return '<div class="timestamp-footer">' + esc(when) + " · Source: " + esc(src) + "</div>";
  }

  // ── Bottom nav (Home active; rest decorative no-ops) ─────────────────
  function bottomNav() {
    var items = [
      { icon: "⌂", label: "Home", active: true },
      { icon: "◷", label: "Timeline", active: false },
      { icon: "▤", label: "Reports", active: false },
      { icon: "○", label: "Profile", active: false }
    ];
    return items.map(function (it) {
      return '<button class="nav-item' + (it.active ? " active" : "") +
        '" type="button" aria-disabled="' + (it.active ? "false" : "true") + '" tabindex="-1">' +
        '<span class="nav-icon">' + it.icon + "</span><span>" + it.label + "</span></button>";
    }).join("");
  }

  window.TWRender = {
    header: header,
    hero: hero,
    forecastTitle: forecastTitle,
    currentPhase: currentPhase,
    forecastCard: forecastCard,
    activeSky: activeSky,
    topDrivers: topDrivers,
    forecastTrend: forecastTrend,
    nextMajorWindow: nextMajorWindow,
    weatherMetrics: weatherMetrics,
    recommendedActions: recommendedActions,
    whyForecast: whyForecast,
    guidance: guidance,
    timestamp: timestamp,
    bottomNav: bottomNav
  };
})();
