---
name: timing-weather-roadmap
description: "Phased roadmap for Timing Weather. v1 + v1.1 + v1.2 (Daily Horoscope) shipped; v1.3 + v3 + v4 explicitly deferred. Locked by Alfie 2026-06-06."
---

# Timing Weather — Phased Roadmap

**Locked 2026-06-06.** Phases are strict — do not pull v1.3/v3/v4 work forward without explicit unlock.

## v1 — Foundation ✅ SHIPPED

### Timing Weather Engine v1
- `engine.py` reads natal_context.md + deep research MDs + council convergence report + live ephemeris (pyephem)
- Computes: dominant planet, forecast label, weather metrics (Opportunity / Pressure / Volatility / Momentum), active council window, narrative
- Outputs: `state.json` (single source of truth for the UI)
- Codex-authored narrative via `~/bin/llm --lane reasoning --model codex`
- No rule-of-three (Alfie stripped May 21)

### Forecast Screen v1
- Mobile-first, vanilla HTML/JS + Tailwind CDN
- Hero Sun (5 dominant-planet states: Jupiter/Saturn/Pluto/Uranus/Venus → EXPANSION/CONSOLIDATION/TRANSFORMATION/DISRUPTION/ATTRACTION)
- Forecast Card (Forecast / Dominant / Supporting / Pressure source / Confidence / Duration)
- 4 Weather Metric cards in 2x2 grid (0-100% each)
- Narrative paragraph (plain English, no astrology jargon)
- 60s polling against state.json

Live URL: `https://alfvargas90-code.github.io/vargas-fitness/timing-weather/`

## v1.1 — Audit + Depth ✅ SHIPPED (2026-06-06)

Engine refactored to the camelCase contract (clean break from v1 snake_case); UI
expanded to the locked 12-section page order. 6 new sections, all engine-backed
(PVR law — no hardcoded values, null → graceful fallback):

- ✅ **Current Phase** (Section 2) — named phase (Preparation/Activation/Expansion/
  Transition/Consolidation/Recovery) + date span, from active council window + forecast classifier
- ✅ **Active Sky** (Section 4) — Dominant / Supporting / Pressure / Volatility planet (added explicit `volatilityPlanet`)
- ✅ **Top Drivers** (Section 5) — top-3 human-readable contributors with +score
- ✅ **Forecast Trend** (Section 6) — RETROACTIVE engine runs at today−27/17/5/0 via
  pyswisseph past-date ephemeris; cached to `polar/cache/trend_*.json`; `trendDirection` from label ordinal
- ✅ **Next Major Window** (Section 7) — derived from the council convergence MD +
  ephemeris (strength ÷ √days). Not hardcoded. Today: Jupiter Return, Jul 12, 36d, 9.2/10, Expansion
- ✅ **Recommended Actions** (Section 9) — Codex-authored 4 do's + 3 avoidances (`~/bin/llm --model codex`, Cowork-safe bypass)
- ✅ **Why This Forecast** (Section 10) — collapsible `<details>`; top-5 `evidence[]` contributors (+/-) sorted by magnitude
- ✅ **Confidence** now emits `null` → UI "Not Rated" (never a fabricated grade)

## v1.1 — Visual Redesign ✅ SHIPPED (2026-06-06)

Supersedes the prior "additive only" v1.1 framing. Full visual redesign per
Alfie's approved two-panel mockup. Engine kept; UI rebuilt from scratch.

- Two-column desktop / stacked mobile
- Glassmorphism cards, gold radial gradient hero
- New planet color coding (Jupiter purple, Venus green, Saturn orange, Uranus cyan)
- Bottom navigation rendered with Home active, Timeline/Reports/Profile decorative
  (deferred-screens compliance noted — they exist visually but are no-op until
  v2/v3 ships)
- File structure: index.html + assets/css/ + assets/js/ (engine + render split)
- Engine adds `subtitle` field, `evidence` becomes nested, `forecastTrend` uses
  `state` instead of `label`

## v1.2 — Daily Horoscope ✅ SHIPPED (2026-06-06)

Two daily reading cards in the right panel, between Weather Metrics and
Recommended Actions (same slot in the stacked mobile order). Same glass + gold
aesthetic; plain-English body (~80-120 words), no astrology jargon in the visible
text (PVR law — `key_factors` may carry technical terms for audit only).

- ✅ **Tropical Horoscope** — `tropicalHoroscope` field. Factors from the engine's
  live geocentric ephemeris (same Swiss Ephemeris the morning iMessage transit
  snapshot uses); today's persisted snapshot, if present, only enriches the Codex
  prompt — never required. Subtitle "Today's transits".
- ✅ **Vedic Horoscope** — `vedicHoroscope` field. New sidereal (Lahiri) engine:
  natal sidereal = tropical − ayanamsha@birth; live `FLG_SIDEREAL` transits;
  current Vimshottari sub-period (Moon–Venus–<sub> from the deep-research KP timing
  table), Sade Sati (Small Panoti), transit-Moon nakshatra, tightest sidereal
  aspects to Lagna/Moon/Sun. Subtitle "Today's sidereal picture · Moon–Venus–…".
- ✅ Both bodies Codex-authored (`~/bin/llm --model codex`, Cowork-safe bypass);
  `null` → UI "Horoscope not yet computed" placeholder (no fakes).

## v2 — Intelligence Dashboard ✅ SHIPPED (2026-06-07)

Full rebuild into a single-column, 15-section mobile intelligence dashboard.
Engine rewritten to a v2 schema (`engine.py`), `index.html` rebuilt to 15
`data-section` blocks, `timing_weather_render.js` rewritten as a self-contained
poller (fetch `state.json` `no-store`, 60s interval, re-render only on
`updatedAt` change). Daily state snapshots persist to `polar/state_history/` so
"Since Yesterday" deltas are real, not fabricated. Cache bumped to **v2.0.0**
(self-healing PWA buster nukes + reloads stale clients once).

The 15 sections (all engine-backed, PVR law — null → graceful "—"/empty state):

1. **Hero Solar Intelligence** — forecast title + subtitle + sun hero
2. **Now Bar** — Forecast / Pressure level / Momentum direction / Next event (days)
3. **Current Phase** — named phase + date span + progress bar + days remaining (computed client-side from start/end vs currentDate)
4. **Event Radar** — NEAR / MID / LONG buckets, top event + days each
5. **Planet Influences** — Dominant / Supporting / Pressure / Volatility cards with signed influence score
6. **Upcoming Events** — top-3 with theme + days
7. **Sky Conditions** — Expansion / Pressure / Volatility / Support bars (0-100%)
8. **Daily Reading** — state label + full prose read (the testable narrative)
9. **Since Yesterday** — Momentum/Opportunity/Pressure/Volatility deltas vs `comparedTo` date; first-day empty state until history exists
10. **Today's Insight** — single-line actionable insight
11. **Recommended Actions** — Do More Of (4) + Avoid (3)
12. **Top Drivers** — top-3 with +score
13. **Why This Forecast** — collapsible `<details>`; Expansion Score + top-5 evidence factors (contributors/reducers, `factor` field) by magnitude
14. **Confidence** — static "Not Rated" (engine emits `null`; never a fabricated grade)
15. **Footer Nav** — Home active; Timeline/Reports/Profile decorative

- **Daily Reading collapse** — the v1.2 dual Tropical/Vedic horoscope cards collapse into one engine-authored Daily Reading (`dailyReading.read`), removing jargon and the two-card split.
- **State persistence** — `state_history/<date>.json` written each run; `dailyChanges` computes deltas against the prior snapshot.
- Live verified: HTTP 200, 15 `data-section` markers, render.js + version.json + state.json v2 fields all live at `https://alfvargas90-code.github.io/vargas-fitness/timing-weather/`.

## v2.1 — Ambient Intelligence ✅ SHIPPED (2026-06-07)

Visual redesign of v2 based on Alfie's approved Apple Watch / Oura / Bloomberg
reference mockup. Same engine, same data schema; UI completely rebuilt.

Hero now has 4 corner ring progress arcs (Opportunity green / Pressure orange /
Momentum cyan / Next Event gold) around a photographic sun core with
EXPANSION title + subtitle.

Layout: 14 sections, multi-column desktop (3-col rows) + single-column mobile.

Key visual elements:
- Hero ring corners (conic-gradient progress arcs; render.js wraps `.corner-value`
  in `.corner-ring` and sets `--ring-pct`; Next Event inverts days→pct)
- Photographic sun (layered radial gradients + corona shadows + pulse)
- Upcoming Conditions = gold gradient horizontal bars (length = proximity),
  NO radar circles
- Planet Influences = compact list rows (glyph + name + role + score),
  NOT large cards
- Why This Forecast = inline open (no collapse; `<details open>`)
- Confidence = small standalone card with "Not Rated" + neutral ring

Cache bumped to v2.1.0. Engine + state.json + state_history unchanged.
Live verified: HTTP 200, 14 `data-section` markers, version.json shows v2.1.0.

## v2.2 — Mockup-faithful Row Structure ✅ SHIPPED (2026-06-07)

Structural rebuild after v2.1 failed visual comparison against Alfie's
reference mockup. HTML was 14 flat sections inside one shell — auto-flow grid
over flat sections couldn't reproduce the curated mockup composition.

- **Row containers** — 7 explicit `.row--*` wrappers replace flat shell layout.
  Row 0 Header chrome (new) · Row 1 Hero (bleed) · Row 2 Now Bar (strip) ·
  Row 3 Today composition (3-col grid w/ named areas
  `"reading changed rail" / "upcoming upcoming rail"`) · Row 4 Analytics
  (4-col) · Row 5 Confidence (meta) · Row 6 Footer Nav (bleed).
- **Header chrome added** — TIMING WEATHER title bar + date subtitle +
  hamburger + 3 status dots. Mockup-faithful. render.js wires `#header-date`
  to state.currentDate ("Sun · Jun 7", UTC-safe parse, client-clock fallback).
- **Current Phase DROPPED** — not in the mockup. Section + bindings
  (`phase-name`/`range`/`progress`/`days`) removed from HTML and render.js.
  Engine field `currentPhase` left in state.json untouched (intentionally unread).
- **Mobile collapse** — `.row--today` areas dissolve to single column,
  `.rail` becomes `display:contents` so children spill in DOM order: Hero →
  Now → Reading → Changed → Insight → Actions → Upcoming → Sky → Planet →
  Drivers → Why → Confidence → Footer.
- Cache bust is handled by the deploy-watch gate, which stamps version.json with
  a fresh timestamp when index.html/app.js change (NOT a static semver — that
  file is gate-owned). This entry is the durable v2.2.0 release record.

## v2.2.1 — Moon Now subtitle ✅ SHIPPED (2026-06-08)

Live Moon position (tropical + vedic + nakshatra) surfaces as a compact
subtitle line under the Daily Reading body. Engine emits `moonNow` in
state.json (sign / degree / house in both systems + nakshatra + pada);
render formats it as `Moon · <trop sign> <deg>° · <H>H trop / <H>H ved ·
<nakshatra>`. PVR strict: null moonNow → empty line (CSS hides it).

## v2.2.2 — Split Daily Reading: Tropical + Vedic ✅ SHIPPED (2026-06-08)

Daily Reading card now contains TWO independent sub-sections (Tropical on
top, Vedic below) with a 1px divider. Engine runs two Codex passes per
run, each with its system's MDs only — frameworks don't blend. New
state.json fields `tropicalReading.{state,body}` and
`vedicReading.{state,body}`. Old `dailyReading` deprecated. Moon Now line
stays as shared footer (already spans both systems).

## v2.2.3 — Whole-Sign Traditional reading ✅ SHIPPED (2026-06-08)

Daily Reading card adds a third sub-section between Tropical Modern and
Vedic: TROPICAL · TRADITIONAL. Hellenistic whole-sign framework with
annual + monthly profection focus. Engine runs THREE Codex passes per run
now (Modern / Traditional / Vedic), each on its own MD context — no
blending. New `traditionalReading.{state, body}` field. Two dividers
between subs, each toggling independently based on adjacent-sub presence.
Moon Now footer unchanged.

## v2.3 — Astrology page sections + Monthly readings ✅ SHIPPED (2026-06-08)

Replaced the single combined Daily Reading card with three full-width
page sections (Traditional → Modern → Vedic), each containing a Daily
view (today) + Monthly view (this month). Engine now runs SIX Codex
passes per run — three daily (preserved) + three monthly (new). Each
system's monthly Codex prompt uses its native month framing: Modern =
Sun-sign transit, Traditional = Profection month (lord-of-month), Vedic
= Vimshottari sub-period + nakshatra cycle. State.json gains
`tropicalMonthly`, `traditionalMonthly`, `vedicMonthly` fields. Section
order reflects Alfie's "traditional first" preference. Moon Now footer
moves into Vedic section. Cross-contamination guardrails preserved
(programmatic scan).

## v1.3 — Metric Breakdowns (deferred)

- Opportunity breakdown by life domain (career / money / relationships / home)
- Pressure breakdown by source (Saturn / Sade Sati / admin load / eclipse proximity)
- Per-metric drill-down cards. **Do not pull forward without Alfie's unlock.**

## v3 — Transit Radar (deferred)

- Orbital rings around the Sun = live transit planet positions
- Each planet: symbol + degree + sign + influence score + color state
- Glow intensity reflects influence score
- Live ephemeris feeds the radar

## v4 — Historical Intelligence (deferred)

- Cycle comparison cards (1990, 2002, 2014) — same Jupiter return cycle, last 3 returns
- Each card: growth score + major themes + notable events + cycle similarity %
- Best Timing Window card (date range + strength + drivers + confidence)
- Planet Intelligence carousel (each planet gets its own deep-dive card)
- Current Focus card (life domain emphasis with prose)

## Out of scope (across all phases)

- Next.js, Vercel, Framer Motion, Recharts, Zustand, React Query — vanilla only
- Bottom navigation (deferred until 3+ screens exist)
- Rule of Three / convergence gate / falsifiability discipline (stripped 2026-05-21 — re-enable only by explicit Alfie unlock; see memory `astrology_prediction_calibration`)

## Stack lock

- Python 3.12 (python.org build, NOT CommandLineTools — per [[fitness-dashboard-syncs-autonomous]])
- pyswisseph for ephemeris (proven autonomous-safe `polar/.venv`; handles past dates natively for Forecast Trend)
- Vanilla HTML/JS + Tailwind CDN for UI
- GitHub Pages deployment (same repo as fitness-dashboard)
- $0 ongoing (per Alfie's spend lock; ChatGPT Plus + Anthropic already cover Codex + Claude)

## Related

- [[claude-codex-playbook]] — role split that built this
- [[deploy-gate-rule]] — commit + push + verify before READY
- [[likes-chatgpt-output]] — Codex voice already validated
