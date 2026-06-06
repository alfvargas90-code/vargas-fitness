---
name: timing-weather-roadmap
description: "Phased roadmap for Timing Weather. v1 in flight, v2 + v3 explicitly deferred. Locked by Alfie 2026-06-06."
---

# Timing Weather — Phased Roadmap

**Locked 2026-06-06.** Phases are strict — do not pull v2/v3 work forward without explicit unlock.

## v1 — Foundation (in flight)

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
- pyephem for ephemeris
- Vanilla HTML/JS + Tailwind CDN for UI
- GitHub Pages deployment (same repo as fitness-dashboard)
- $0 ongoing (per Alfie's spend lock; ChatGPT Plus + Anthropic already cover Codex + Claude)

## Related

- [[claude-codex-playbook]] — role split that built this
- [[deploy-gate-rule]] — commit + push + verify before READY
- [[likes-chatgpt-output]] — Codex voice already validated
