# SHARED DESIGN KIT — round 2 (match the LIVE dashboard exactly)

Every mockup MUST use these exact tokens. Do NOT invent new colors, fonts, or card
styles. The whole point of round 2 is staying inside Alfredo's existing visual world
and only changing LAYOUT + INFO HIERARCHY.

## Font
`font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", system-ui, sans-serif;`
Base text color `#F2F5FA`. Tabular numerals: `font-variant-numeric: tabular-nums;` on all numbers.

## Body background (paste verbatim onto the page/body)
```css
background:
  radial-gradient(118% 60% at 50% 28%, rgba(88,62,205,.40), transparent 62%),
  radial-gradient(circle at 2% 42%, rgba(0,200,255,.10), transparent 46%),
  radial-gradient(circle at 98% 42%, rgba(255,94,98,.10), transparent 46%),
  radial-gradient(circle at 86% 70%, rgba(255,138,61,.09), transparent 46%),
  radial-gradient(circle at 14% 72%, rgba(138,92,255,.12), transparent 46%),
  linear-gradient(180deg, #03050F 0%, #04061a 50%, #03040E 100%);
background-color: #03050F;
```

## Palette (semantic)
- Base/ink: `#03050F`  ·  panel `#080B1C`  ·  surface `#10183A`
- Recovery / cyan: `#00C8FF`  (bright text `#E9F7FF`)
- Sleep / purple: `#8A5CFF`  (display variant `#9A6BFF`, light `#C9B8FF`)
- Strain / coral: `#FF5E62`
- Activity / orange: `#FF8A3D`
- Nutrition / green: `#39D98A`
- Recovery-tab pink: `#FF5E8A`  (light `#FFB3C8`)
- Body-tab violet: `#9B5CFF`
- Muted label: `#8A90A6`
- Coach gold (only for trainer voice): `#FFB020`

## Glass card (use for ALL cards — paste verbatim)
```css
.glass {
  background:
    linear-gradient(180deg, rgba(255,255,255,0.045), rgba(255,255,255,0) 42%),
    rgba(20,26,54,0.68);
  border: 1px solid rgba(255,255,255,0.11);
  -webkit-backdrop-filter: blur(24px) saturate(1.24);
  backdrop-filter: blur(24px) saturate(1.24);
  border-radius: 22px;
  box-shadow: inset 0 1px 0 rgba(255,255,255,.16), inset 0 -1px 0 rgba(0,0,0,.35), 0 22px 50px rgba(0,0,0,.5);
}
```

## Semantic glows (text-shadow on colored numbers)
- cyan: `text-shadow: 0 0 17px rgba(0,200,255,0.78);`
- purple: `text-shadow: 0 0 17px rgba(138,92,255,0.78);`
- coral: `text-shadow: 0 0 18px rgba(255,94,98,0.85);`
- orange: `text-shadow: 0 0 11px rgba(255,138,61,0.55);`
- green: `text-shadow: 0 0 11px rgba(57,217,138,0.55);`

## Pill label (eyebrow / chips)
Section eyebrow: `font-size:11px; text-transform:uppercase; letter-spacing:2px; font-weight:700;` colored per section, `opacity:.85`.
Chip pill: `border-radius:999px; padding:2px 9px; font-size:9-10px; font-weight:700;` background `rgba(<accent>,0.12)`, border `1px solid rgba(<accent>,0.30)`, text in the accent.

## Pink/coral italic prose (narrative voice — like the kids astro page)
```css
.prose {
  font-style: italic; font-size: 13.5px; line-height: 1.75; color: #E9EDF5;
}
.prose-closing {
  font-style: italic; font-weight: 600; color: #FF7FA0;
  text-shadow: 0 0 12px rgba(255,94,138,0.45);
}
```
Use a warm coral/pink (`#FF7FA0` / `#FFB3C8`) for the narrative + closing line. Keep it
emotional but precise. This is how today's "read" / story copy should feel.

## Moon hero (THE signature element — use the REAL one)
A file `_moon_hero.svg` sits in this same folder: it is the EXACT moon + 3 orbital rings
SVG pulled from the live dashboard (viewBox 0 0 260 260, self-contained, references
`../assets/moon-lro.webp` for the lunar texture). To use it, READ `_moon_hero.svg` and
paste its full `<svg>…</svg>` markup inline into a centered container, e.g.:
```html
<div style="position:relative;width:260px;height:260px;margin:0 auto;filter:saturate(1.12) contrast(1.04)">
  <!-- paste _moon_hero.svg contents here -->
</div>
```
The three rings are: outer = Strain (coral), middle = Recovery (cyan), inner = Sleep (purple).
Around the moon, the live app floats 3 metric corners — Recovery (cyan, top-left),
Sleep (purple, top-right), Strain (coral, bottom-right) — using:
```css
.metric-cap{font-size:11px;font-weight:700;letter-spacing:1.4px;text-transform:uppercase}
.metric-num{font-size:34px;font-weight:800;line-height:1;font-variant-numeric:tabular-nums}
.metric-word{font-size:13px;font-weight:700;margin-top:2px}
.metric-detail{font-size:11px;color:#8A90A6;margin-top:2px;font-weight:600}
```
You may keep, shrink, or relocate the moon per your layout direction — but when you show
it, use this real SVG, not a hand-drawn substitute. If a direction de-emphasizes the moon,
you can scale the container down (e.g. 150px) and still embed the same SVG.

## MOCK DATA — Thursday, June 12, 2026 (use these exact numbers)
- Weight: **167.5 lb**  (▼0.3 vs yesterday, ▼1.8 over 7 days)
- Body fat: **18.2%**  ·  Muscle/Lean: **137.0 lb**  ·  BMI **23.4**
- Sleep last night: **6h 46m** (target 8h)  ·  Sleep score **72/100**
- ANS Charge: **−4.2**  → status **Compromised** (below baseline)
- HRV: **62 ms** (7-day avg 68)
- Resting HR: **54 bpm**
- Nightly Recharge: **Compromised**
- Recovery score (for cyan ring/corner): **41 · Compromised**
- Active calories today: **612 kcal**  ·  Total burn **2,340 kcal**  ·  Steps **7,840** (goal 10,000)
- Strain/exertion (for coral ring): **11.4**
- Nutrition today: **1,850 kcal** eaten of **2,100** target (250 left)
  · Protein **142 / 180 g**  · Carbs **168 g**  · Fat **61 g**
- Sync stamps: Polar **06:40**, VeSync **07:05**, Nutrition **12:30**
- Narrative read of the day (compromised recovery): something like —
  *"Your nervous system slipped below baseline overnight. The numbers aren't asking for
  effort today — they're asking for restraint. Move easy, eat enough, and let the charge
  come back on its own."*

## Hard constraints
- Single self-contained HTML file, inline `<style>`, no external JS/CSS frameworks
  (you MAY keep the moon's `../assets/moon-lro.webp` reference — that's a local asset).
- Fixed 375px-wide column, designed for a 375×812 mobile viewport, no horizontal scroll.
- Match the dark glassy aesthetic above EXACTLY. Only the layout/hierarchy is yours to reinvent.
