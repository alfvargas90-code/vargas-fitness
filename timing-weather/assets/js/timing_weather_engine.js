/* Timing Weather — v1.1 thin client engine.
 * Owns all runtime behavior: fetch state.json, poll every 60s, and on change
 * paint the two panels by calling the pure TWRender card functions. The real
 * engine is engine.py (writes state.json); this is just the binding layer.
 * No values are computed here — only fetched and routed.
 */
(function () {
  "use strict";

  var R = window.TWRender;

  // Left panel = sections 1-8 (top to bottom). On mobile the panels stack, so
  // DOM order (left then right) IS the linear mobile order from the spec.
  function renderLeft(s) {
    return [
      R.header(),
      R.hero(s),
      R.forecastTitle(s),
      R.currentPhase(s),
      R.forecastCard(s),
      R.activeSky(s),
      R.topDrivers(s),
      R.forecastTrend(s)
    ].join("");
  }

  // Right panel = sections 1-6 (top to bottom).
  function renderRight(s) {
    return [
      R.nextMajorWindow(s),
      R.weatherMetrics(s),
      R.tropicalHoroscope(s),
      R.vedicHoroscope(s),
      R.recommendedActions(s),
      R.whyForecast(s),
      R.guidance(s),
      R.timestamp(s)
    ].join("");
  }

  function paint(s) {
    document.getElementById("tw-left").innerHTML = renderLeft(s);
    document.getElementById("tw-right").innerHTML = renderRight(s);
  }

  function paintError(msg) {
    var left = document.getElementById("tw-left");
    if (left && !left.dataset.painted) {
      left.innerHTML = R.header() +
        '<p class="forecast-subtitle">' + msg + "</p>";
    }
  }

  async function fetchState() {
    var r = await fetch("state.json", { cache: "no-store" });
    if (!r.ok) throw new Error("HTTP " + r.status);
    return r.json();
  }

  var lastSig = null;
  async function poll() {
    try {
      var s = await fetchState();
      var sig = s.updatedAt || JSON.stringify(s).length;
      if (sig !== lastSig) {
        lastSig = sig;
        paint(s);
        document.getElementById("tw-left").dataset.painted = "1";
      }
    } catch (e) {
      paintError(lastSig === null ? "Waiting for the engine's first read…" : "");
    }
  }

  function init() {
    // Bottom nav: Home is active; the rest are decorative dead taps (no routing —
    // Timeline/Reports/Profile screens don't exist yet per ROADMAP).
    var nav = document.getElementById("tw-nav");
    if (nav) {
      nav.innerHTML = R.bottomNav();
      nav.addEventListener("click", function (e) {
        var btn = e.target.closest(".nav-item");
        if (btn && !btn.classList.contains("active")) {
          e.preventDefault(); // no-op: deferred screens
        }
      });
    }
    poll();
    setInterval(poll, 60000);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
