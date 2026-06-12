# Timing Weather — Astrology Design Exploration · Round 1 · 2026-06-12

Four layout directions for the **timing-weather astrology PWA**, all built in the canonical
**solar-intelligence aesthetic** from Alfredo's two reference dashboards: glowing gold sun
hero, near-black gradient, "EXPANSION" phase headline, four corner stat rings, dense glassy
cards (Sky Conditions bars, Planet Influences, What Changed, Recommended Actions, Confidence).
One aesthetic, four different hierarchies for surfacing the Modern · Traditional · Vedic ·
BaZi daily horoscopes.

> **Rebuilt 2026-06-12** against `design_references/timing-weather-ref-1.png` (sun-only hero)
> and `timing-weather-ref-2.png` (sun with orbital planets). The first pass used a moon/pink
> aesthetic and was corrected to this gold-sun direction.

## View it
- **Comparison gallery:** `index.html` (live iframes of all four + rationale + the pick)
- Live preview: `http://localhost:8766/design_exploration_2026-06-12/`
- GH Pages: `https://alfvargas90-code.github.io/vargas-fitness/timing-weather/design_exploration_2026-06-12/`

## The four directions
| # | Name | Modeled on | One-line | Best for |
|---|------|-----------|----------|----------|
| 1 ★ | **Expansion Hero** | ref-1 | Sun + 4 corner rings + auto-surfaced reading + dense cards | The morning glance — instant dashboard read, one committed call |
| 2 | **System Carousel** | solar skin | Sun + consensus, four swipeable system panels | Sitting inside one system at a time |
| 3 | **Orbital Sky** | ref-2 | Sun with labeled orbiting planets, full instrument panel | "Feel the whole sky at once" |
| 4 | **Narrative Day-Flow** | solar skin | Sun on a day-arc + morning→night timeline | The daily ritual |

> Filenames keep their original slugs (`direction-2-carousel`, `direction-3-sky-first`) so the
> deployed URLs stay stable; the displayed names are above.

## Claude's recommendation
**Direction 1 — Expansion Hero**, if shipping today. Closest match to the reference
dashboards; gives the full dashboard read at a glance, then commits to one auto-surfaced
reading instead of four to weigh — the right antidote to the overanalysis loop. **Close
second: Direction 3 — Orbital Sky**, the most visually striking (sun with labeled orbiting
planets); pick it for "feel the whole sky" over a single verdict.

(Not equal-weighted: 1 for converge-fast utility + closest aesthetic match, 3 for the
structure-lover who wants every influence, 4 for emotional daily ritual, 2 for the deliberate
explorer.)

## Aesthetic source-of-truth
- `design_references/timing-weather-ref-1.png` + `timing-weather-ref-2.png` — the canonical
  visual targets (gold sun hero, EXPANSION headline, corner rings, dense cards).
- Live `timing-weather/index.html` + CSS — the solar-intelligence design tokens.

## Personalization (today's real chart, Jun 12 2026)
12th-house Sagittarius profection (lord Jupiter) · Jupiter return ~Jul 12 · SA Jupiter→Virgo
Sun (exact Mar 2027) · Moon Mahadasha / Venus antardasha (first relationship-warm sub-period)
· Sade Sati on foundations · Ding Fire day master / Rabbit operating self · Bing-Wu peer-fire
visibility+burnout year · Capricorn/Saturn embodiment year opens Aug 30.

## Files
```
index.html                          comparison gallery
direction-1-hero-first.html         Expansion Hero      + _README.md
direction-2-carousel.html           System Carousel     + _README.md
direction-3-sky-first.html          Orbital Sky         + _README.md
direction-4-day-flow.html           Narrative Day-Flow  + _README.md
screenshots/*.png                   375x812 @2x
```

## Constraints honored
Mockups only — live `index.html` / `engine.py` / `render.js` / `state.json` untouched. No
deploy to the live PWA. New files in a new directory.
