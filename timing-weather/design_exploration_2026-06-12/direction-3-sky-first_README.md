# Direction 3 — Sky-First

**File:** `direction-3-sky-first.html`

## The user moment it serves
The **"what's happening up there right now"** feel. Instead of leading with prose, this
layout leads with the *picture*: a live transit wheel — transiting planets laid over
Alfredo's natal ring, today's hottest aspect drawn as a line (Jupiter applying to his
8th-house Virgo Sun), the moon rendered at the center. The four system readings sit
underneath, as interpretation of what the wheel already showed.

## Why it fits Alfredo specifically
- He's a **System Architect** who thinks in structure and mechanism. The wheel shows the
  *machinery* — the actual geometry driving the day — before the narrative. He'll trust a
  reading more when he can see the transit that generated it.
- Mirrors the **kids-astro dashboard's live-sky strip + wheel**, which he already built and
  loves — this is that idea promoted to the hero slot.
- The "applying · 1.4°" precision tag rewards his demand that numbers be real.

## The wheel (mock but structurally honest)
SVG zodiac ring with Capricorn rising on the ascendant, 12 sign glyphs, transiting Sun /
Moon / Mercury / Venus / Mars / Jupiter / Saturn placed by ecliptic longitude, a dashed
pink aspect line from transiting Jupiter to natal Sun, and a gradient moon disc at center
with phase label. In production this binds to the existing lunar/transit engine.

## Aesthetic notes
Deep blue/purple gradient, "LIVE SKY" pulse dot, glassy wheel card with radial core glow,
planet legend strip, pink "hot aspect" banner with coral italic prose, violet section
divider, per-system reading rows with state dots.

## Chart data surfaced
Live transit positions (mock for Jun 12) · applying Jupiter→Sun · Moon void-of-course note ·
the four systems' one-line reads beneath.

## Tradeoff
The wheel is gorgeous but information-dense — more to parse than a single headline. Best for
someone who *wants* the chart, not just the verdict. The most technically ambitious to wire
to real ephemeris data.
