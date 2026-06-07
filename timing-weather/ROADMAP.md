---
name: timing-weather-roadmap
description: "Phased roadmap for Timing Weather. v1 + v1.1 shipped; v1.2 + v2 + v3 explicitly deferred. Locked by Alfie 2026-06-06."
---

# Timing Weather — Phased Roadmap

**Locked 2026-06-06.** Phases are strict — do not pull v1.2/v2/v3 work forward without explicit unlock.

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

## v1.2 — Metric Breakdowns (deferred)

- Opportunity breakdown by life domain (career / money / relationships / home)
- Pressure breakdown by source (Saturn / Sade Sati / admin load / eclipse proximity)
- Per-metric drill-down cards. **Do not pull forward without Alfie's unlock.**

## v2 — Transit Radar (deferred)

- Orbital rings around the Sun = live transit planet positions
- Each planet: symbol + degree + sign + influence score + color state
- Glow intensity reflects influence score
- Live ephemeris feeds the radar

## v3 — Historical Intelligence (deferred)

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
