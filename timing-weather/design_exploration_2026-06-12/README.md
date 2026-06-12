# Timing Weather — Astrology Dashboard Exploration · 2026-06-12

Four layout directions for the **timing-weather astrology PWA**, all modeled on **both**
reference screenshots (`design_references/timing-weather-ref-1.png` + `-ref-2.png`) — the
dense, multi-column dashboard: glowing gold sun, corner gauges, NOW row, Sky Conditions bars,
Planet Influences, Event Radar. One visual world, four different hierarchies. Built for
iPad/desktop width (the references are 1024px).

> The key correction (round 4): the references are **dense single-screen dashboards**, not
> phone scrolls. Earlier rounds built tall single-column mobile layouts — same components,
> wrong canvas. These four match the references' density and section composition.

## View it
- **Comparison gallery:** `index.html` (all four + full-page screenshots)
- GH Pages: `https://alfvargas90-code.github.io/vargas-fitness/timing-weather/design_exploration_2026-06-12/`

## The four directions
| # | Name | Hero | Best for |
|---|------|------|----------|
| 1 ★ | **Solar Dashboard** (ref-1) | Sun + 4 corner gauges | Metrics-forward read; closest to ref-1 |
| 2 | **Reading-Led Dashboard** | Compact sun + gauge chips | The four horoscopes as the centerpiece (2×2 cards) |
| 3 | **Orbital Dashboard** (ref-2) | Sun + orbiting planets + radar | "See the whole sky"; closest to ref-2 |
| 4 | **Command Center** | Gauges **and** orbit fused | Maximalist single-screen "mission control" |

> Filenames keep their original slugs (`direction-2-carousel`, `direction-3-sky-first`,
> `direction-4-day-flow`) so deployed URLs stay stable; displayed names are above.

## Claude's recommendation
**Direction 1 — Solar Dashboard**, if shipping today: the cleanest, closest match to
reference 1, and the easiest to wire to your real `state.json`. **Direction 2 — Reading-Led**
is the one I'd push for if the daily *use* is reading horoscopes rather than scanning metrics,
since it puts the four systems' prose front and center. 3 and 4 are the orbital and maximalist
options.

## Aesthetic source-of-truth
Both reference screenshots (dense multi-column dashboard · gold sun hero · corner gauges ·
orbital planets · Sky Conditions bars · Planet Influences · Event Radar) + the live
timing-weather solar design tokens.

## Personalization (today's real chart, Jun 12 2026)
12th-house Sagittarius profection (lord Jupiter) · Jupiter return ~Jul 12 · SA Jupiter→Virgo
Sun (exact Mar 2027) · Moon Mahadasha / Venus antardasha · Sade Sati · Ding Fire / Rabbit ·
Bing-Wu peer-fire year · Capricorn/Saturn embodiment year opens Aug 30.

## Files
```
index.html                          comparison gallery
direction-1-hero-first.html         Solar Dashboard (ref-1)   + _README.md
direction-2-carousel.html           Reading-Led Dashboard     + _README.md
direction-3-sky-first.html          Orbital Dashboard (ref-2) + _README.md
direction-4-day-flow.html           Command Center            + _README.md
dashboard.css                       verbatim copy of the live timing-weather.css (tokens)
screenshots/*.png                   full-page @2x
```

## Constraints honored
Mockups only — live `index.html` / `engine.py` / `render.js` / `state.json` untouched. No
deploy to the live PWA. New files in a new directory.
