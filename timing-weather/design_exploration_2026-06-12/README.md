# Timing Weather — Astrology Design Exploration · Round 1 · 2026-06-12

Four fresh layout directions for the **timing-weather astrology PWA**, all built to stay
*inside* Alfredo's existing visual world (the fitness Round 1 was rejected for drifting too
far). One aesthetic, four different hierarchies for surfacing the Modern · Traditional ·
Vedic · BaZi daily horoscopes.

## View it
- **Comparison gallery:** `index.html` (live iframes of all four + rationale + the pick)
- Live preview path: `http://localhost:8766/design_exploration_2026-06-12/`
- GH Pages: `https://alfvargas90-code.github.io/vargas-fitness/timing-weather/design_exploration_2026-06-12/`

## The four directions
| # | Name | One-line | Best for |
|---|------|----------|----------|
| 1 ★ | **Hero-First Reading** | Engine auto-surfaces the single strongest signal as a giant top card; others collapse below | The morning glance — one answer, one move |
| 2 | **System Carousel** | Vedic/Modern/Traditional/BaZi as full-width swipeable hero cards | Sitting inside one system at a time |
| 3 | **Sky-First** | Live transit wheel as the main object; readings beneath | "What's happening up there right now" |
| 4 | **Narrative Day-Flow** | Vertical timeline morning→night, time-of-day grounded | The daily ritual |

## Claude's recommendation
**Direction 1 — Hero-First**, if shipping today. It answers *"what matters today"* in one
glance and surfaces one call instead of four readings to weigh — the right antidote to the
overanalysis loop, while keeping the moon orbital hero front and center. **Close second:
Direction 4 — Day-Flow**, the most emotionally on-brand for "timing *weather*"; pick it if
the goal is daily ritual over quick check-in.

(Not equal-weighted: 1 for converge-fast utility, 4 for emotional stickiness, 3 for the
structure-lover, 2 for the deliberate explorer.)

## Aesthetic source-of-truth
- Current `timing-weather/index.html` + `render.js` — dark gradient, glassy cards,
  pink/coral italic prose, moon hero.
- `01_Kids/kids-astro-dashboard.html` — Sun/Moon/Rising card layout, daily horoscope with
  pill, live sky strip.

## Personalization (today's real chart, Jun 12 2026)
12th-house Sagittarius profection (lord Jupiter) · Jupiter return ~Jul 12 · SA Jupiter→Virgo
Sun (exact Mar 2027) · Moon Mahadasha / Venus antardasha (first relationship-warm sub-period)
· Sade Sati on foundations · Ding Fire day master / Rabbit operating self · Bing-Wu peer-fire
visibility+burnout year · Capricorn/Saturn embodiment year opens Aug 30.

## Files
```
index.html                          comparison gallery
direction-1-hero-first.html         + _README.md
direction-2-carousel.html           + _README.md
direction-3-sky-first.html          + _README.md
direction-4-day-flow.html           + _README.md
screenshots/*.png                   375x812 @2x
```

## Constraints honored
Mockups only — live `index.html` / `engine.py` / `render.js` / `state.json` untouched. No
deploy to the live PWA. New files in a new directory; no backups needed.
