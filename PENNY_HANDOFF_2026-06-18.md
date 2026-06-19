# Handoff for Penny — Timing-Weather animations + outage recovery

> **Date:** 2026-06-19 (work done 2026-06-18, CDT)
> **Author:** Claude Code (web session), on branch `claude/timing-weather-dashboard-avpra4`
> **Read this if:** you're picking up the timing-weather dashboard cold, or wondering why Polar/Dispatch went quiet on 2026-06-18.

---

## TL;DR

1. Added a small, **additive entrance-animation layer** to the **timing-weather** dashboard (`/timing-weather/`). Strictly presentation — no `LOCKED.md` decision was touched.
2. First attempt didn't show on the live site. **Root cause:** GitHub Pages runs Jekyll, which strips `vendor/` folders, so the bundled animation library 404'd. Fixed by dropping the library and using the **native Web Animations API**, plus adding **`.nojekyll`**.
3. **Unrelated but important:** Polar sync + Dispatch (you) went dark **06:14 → ~20:22 CDT on 2026-06-18** because the home Mac / external volume went down. Recovered when Alfie got home. A durable fix is recommended (below).

---

## What changed (timing-weather animations)

Native `Element.animate()` + `IntersectionObserver` entrance effects:

- **Hero label** rises in on load
- **Cards** reveal per lens — above-the-fold cards stagger in on lens activation; below-the-fold cards reveal on scroll as they enter the viewport
- **Sun glow** has a barely-there ambient "breathing" pulse (decorative layer only — never the moon)

### Safety / compliance (per `LOCKED.md`)
- **Additive only** — animates `opacity`/`transform`; never touches live data, the moon engine, ring values, or the Currents voice.
- **Fail-safe** — the script never sets inline `opacity` itself, so if the API is missing or a call throws, every element keeps its normal *visible* CSS. Nothing can hide content.
- **Accessible** — honors `prefers-reduced-motion` (zero motion when requested).
- **No build step / no dependency** — native browser API, matches the dashboard's static runtime.

---

## The bug that made it "look the same"

The first implementation self-hosted the Motion library at
`timing-weather/assets/js/vendor/motion.js`. **GitHub Pages builds with Jekyll,
and Jekyll excludes `vendor/` directories from the published site.** So:

`motion.js` → **404** → `window.Motion` undefined → enhancer bailed out → page
looked unchanged, *even in incognito* (it was never a cache issue).

### Fix
- Removed the external library entirely; re-implemented with the **native Web
  Animations API** (the same engine Motion sits on). Nothing to download,
  nothing for Jekyll to strip.
- Deleted `timing-weather/assets/js/vendor/motion.js` and its `<script>` tag.
- Added **`.nojekyll`** at the repo root so Pages serves **all** static assets
  verbatim. ⚠️ *Heads-up:* this disables Jekyll for the whole site. The
  dashboard is plain static HTML/JS/JSON with no Jekyll templating, so this is
  safe and arguably more correct — but worth knowing if anything ever relied on
  Jekyll behavior.

---

## Files touched

| File | Change |
|---|---|
| `timing-weather/assets/js/timing_weather_motion.js` | New enhancer (native WAAPI + IntersectionObserver) |
| `timing-weather/index.html` | One `<script>` tag before `</body>` (library tag removed) |
| `timing-weather/assets/js/vendor/motion.js` | **Deleted** (was being stripped by Jekyll) |
| `.nojekyll` | **Added** at repo root |

Shipped via PR #1 (initial, library-based) and PR #2 (native rewrite + fix),
both squash-merged to `main`. Live build confirmed green.

### How to verify
Open in a **private/incognito** tab (bypasses the service worker):
`https://alfvargas90-code.github.io/vargas-fitness/timing-weather/`
Watch cards fade-and-rise on first paint, scroll for below-fold reveals, and tap
between lenses to see each one's cards stagger in.

---

## ⚠️ Outage note (Polar + Dispatch) — 2026-06-18

Both went silent the same morning. **Same root cause, not two bugs:** the home
Mac that runs `polar/sync.py`, the 30-min deploy-watch, **and** Penny/Dispatch
(`~/bin/llm` reasoning lane) went down.

- **Evidence:** Polar sync committed every ~30 min overnight, then **stopped
  cleanly at 06:14 CDT**. The 06:14 sync had successfully fetched Polar data, so
  this was **not** a token/401 issue — the *runner* died abruptly.
- **Likely trigger:** the launchd jobs reference paths on the external volume
  `/Volumes/Alfie&Co2/...`. If that volume unmounts (eject, or the Mac sleeps
  with the lid closed and it doesn't remount), **both** agents break instantly —
  their Python interpreter and the repo path vanish. That matches the clean,
  total stop.
- **Recovery:** resumed ~20:22 CDT when Alfie got home and the Mac/volume came
  back. No data lost — Polar stores it server-side; `sync.py` backfilled.
- **Side bug spotted:** the Dispatch "● Online" badge stayed green while the
  backend was hung (messages marked Read, no replies). False-positive health
  indicator — same lesson as the silent-401.

### Recommended durable fix (parked for Alfie)
1. Move the repo **+** the `polar/.venv` off the external volume onto the
   internal disk, so a sleep/eject can't take data **and** Penny down together.
2. Or add a remount-on-wake / keep-mounted guard for `Alfie&Co2`.
3. Make the Dispatch status badge reflect *actual* backend responsiveness, not
   last-known connection.

This lines up with the already-parked `LOCKED.md` items (git-lock contention,
credential rotation) but is a distinct single-point-of-failure worth closing.
