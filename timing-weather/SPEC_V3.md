---
name: timing-weather-spec-v3
description: "Locked specification for Timing Weather v3.0 — Ambient Intelligence OS redesign. Authored 2026-06-08. Build starts 2026-06-09 morning."
---

# Timing Weather v3.0 — Locked Specification

**Authored:** 2026-06-08
**Build cycle:** 2026-06-09 (fresh morning, Mac available)
**Goal:** Transform Timing Weather from **Report Viewer** → **Ambient Intelligence Operating System**

## Design Lock

**Pattern:** Ambient Intelligence Operating System
**References:** Oura · WHOOP · Apple Weather · Arc Browser
**NOT:** Astrology App · Report Viewer · Analytics Dashboard

## Primary Goal

User understands within **5 seconds**:
1. What is happening
2. Why it is happening
3. What changed
4. What to do next

---

## Locked Decisions

### 1. Vedic — Hidden But Kept (option C)
- **Home consumes:** Modern + Traditional + Consensus
- **Reports consume:** Modern + Traditional + Vedic + Combined
- **Engine continues generating:** Modern + Traditional + Vedic + Combined
- Reason: removing Vedic destroys unique differentiator; three systems on Home creates clutter. Home answers "what's happening / what to do," not "which framework."

### 2. Drawer Tabs — Today + Month Active, Quarter + Year Placeholder (option B)
- Engine already supports Today + Month
- Quarter + Year ship as "Coming Soon" tabs in v3.0
- Activate in v3.1 after engine expansion

### 3. Navigation — Home Functional, Others Placeholder (option B)
- Home: fully functional
- Timeline / Reports / Profile: preview cards with "Coming Soon"
- v3.1 = Timeline · v3.2 = Reports · v3.3 = Profile

### 4. Build Timing — Tomorrow
- Lock spec tonight, spawn tomorrow morning
- Mac available for desktop-first review
- Avoids fatigue / scope drift

---

## Home Screen Architecture

### 1. Hero Solar Intelligence (full-width, top)
- **Upper Left:** Opportunity (e.g. `29` / `Low`)
- **Upper Right:** Pressure (e.g. `85` / `High`)
- **Lower Left:** Momentum (e.g. `48` / `Rising`)
- **Lower Right:** Next Event (e.g. `34 Days`)
- **Center:** Solar Core + Forecast title (`EXPANSION`) + subtitle (`Doors opening — build the pipeline`)
- **Visual:** Large solar object · dynamic glow · subtle pulse · dark background · gold forecast typography
- **Forbidden:** astrology wheel · zodiac chart

### 2. System Consensus (NEW — directly below hero)
- **Purpose:** Compare Modern vs Traditional. Instant agreement detection.
- **Display:** `Modern: Expansion` | **Agreement: 92%** | `Traditional: Expansion`
- **Primary Action line:** "Build leverage and avoid final commitments."
- **States:** Agreement / Partial Agreement / Disagreement
- **Color logic:** Green = agreement · Yellow = mixed · Red = conflict

### 3. Intelligence Snapshots (two-column)

**Modern Snapshot:**
- Theme · Driver · Opportunity · Pressure · Action
- Example: Theme=Expansion · Driver=Mercury · Opp=Low · Pressure=High · Action=Build leverage
- Footer: `View Analysis →` (opens Modern Drawer)

**Traditional Snapshot:**
- Theme · Driver · Opportunity · Pressure · Action
- Example: Theme=Expansion · Driver=Moon-Venus-Jupiter · Opp=Moderate · Pressure=High · Action=Prepare quietly
- Footer: `View Analysis →` (opens Traditional Drawer)

### 4. Analysis Drawers (replace visible essays)

**Modern Drawer tabs:** Today | Month | Quarter (Coming Soon) | Year (Coming Soon)
**Traditional Drawer tabs:** Today | Month | Quarter (Coming Soon) | Year (Coming Soon)

Long-form essays from v2.x move here. Nothing deleted — only relocated.

### 5. What Changed (immediately after Snapshots)
- **Purpose:** Highlight movement
- **Display:** Momentum / Opportunity / Pressure / Volatility deltas
- Example: Momentum +9 · Opportunity +1 · Pressure 0 · Volatility 0
- Footer: updated timestamp

### 6. Today's Insight
- **Purpose:** Single directive
- **Max:** 2 sentences
- **Visual:** Premium highlighted card · gold accent border
- Example: "Build leverage and price your work clearly. Fill the pipeline but do not lock final commitments yet."

### 7. Recommended Actions (two-column)

**Do More Of (max 4):** ✓ Build pipeline · ✓ Price contribution · ✓ Prepare property · ✓ Schedule authority meetings
**Avoid (max 3):** ✗ Final commitments · ✗ Salary dependency · ✗ Romance fixation

### 8. Upcoming Conditions (timeline visualization — replaces radar circles)
- **Display:** Days · Event · Visual importance bar
- Example rows:
  - `34 Days` Jupiter Return — Highest Priority
  - `65 Days` Saturn Year Begins — Medium Priority
  - `121 Days` Jupiter-Venus Benefic — Lower Priority
- **Visual:** Colored timeline bars (purple / gold / blue)

### 9. Sky Conditions
- **Metrics (horizontal bars):** Expansion · Pressure · Volatility · Support
- Example: Expansion 29% · Pressure 85% · Volatility 78% · Support 48%
- **Visual:** color-coded horizontal bars

### 10. Planet Influences
- **Compact list (single card, no scrolling card stack)**
- Example rows: Jupiter Dominant +19 · Venus Supporting +10 · Saturn Pressure -50 · Uranus Volatility -66

### 11. Top Drivers
- **Top 3 only**
- Example: 1) Jupiter Lord of Year +15 · 2) Venus Antardasha +10 · 3) Approaching Jupiter Return +4

### 12. Why This Forecast
- **Display:** Expansion Score + Positive contributors (max 5) + Negative contributors (max 5)
- Example: Score 29 · Positives: Jupiter LoY +15, Venus AD +10, Jupiter Return approaching +4 · Negatives: Saturn pressure -50, Uranus volatility -66

### 13. Confidence
- **Current State:** Not Rated
- **Reason:** No validated confidence model
- **Display:** Neutral ring · muted styling · text `Not Rated` / `Gathering Data`
- **Forbidden:** percentage · fabricated precision

---

## Other Tabs (placeholders for v3.0)

### Timeline Tab (v3.1)
**Sections:** Upcoming Conditions · Monthly Forecasts · Quarter Forecasts · Major Windows · Historical Windows

### Reports Tab (v3.2)
**Reports:** Modern · Traditional · Vedic · Combined · Monthly · Quarterly · Yearly
**Export:** PDF · Markdown

### Profile Tab (v3.3)
**Settings:** Birth Data · Location · Forecast Preferences · Theme · Data Sources · Report Settings

---

## Design System

**Typography:** Large Forecast Titles · Gold Headlines · High contrast
**Spacing:** Generous · card-driven · airy
**Colors:**
- Gold = Forecast
- Green = Opportunity
- Orange = Pressure
- Blue = Support
- Red = Volatility
- Purple = Jupiter Events

## Forbidden Patterns

- ❌ Giant visible essays
- ❌ Astrology wheels
- ❌ Radar circles
- ❌ Stacked report cards
- ❌ PowerBI / enterprise dashboard layouts
- ❌ Paragraph-heavy home screen

## Success Criteria

Home screen communicates within 5 seconds:
- Forecast
- Pressure
- Opportunity
- Momentum
- Next Event
- Recommended Action
- System Agreement
- Recent Changes

Detailed astrology remains available through expandable Analysis Drawers — not occupying primary interface.

---

## Engine Schema Impact

**Preserve (no breaking changes):**
- `tropicalReading.{state, body}` daily
- `traditionalReading.{state, body}` daily
- `vedicReading.{state, body}` daily
- `tropicalMonthly.{state, body}`
- `traditionalMonthly.{state, body}`
- `vedicMonthly.{state, body}`
- `moonNow` (existing structure)

**Add:**
- `consensus.{agreement_pct, primaryAction, modernState, traditionalState, status}` — derived field
- `snapshots.modern.{theme, driver, opportunity, pressure, action}` — compact summary derived from full readings
- `snapshots.traditional.{theme, driver, opportunity, pressure, action}` — same
- Quarter + Year drawer fields stub as `null` for v3.0; populate in v3.1

## Compliance

Build must respect:
- **POP** (Project Operating Principles)
- **PVR** (Production Readiness Verification) — null → graceful empty state, no fabrication
- **READY = VERIFIED** — deploy gate rule applies
- Roadmap integrity (preserve v2.x history, add v3.0 entry)

## Build Order (Tomorrow)

1. **Chunk 1:** Engine schema additions (consensus + snapshots derivation) — no UI yet
2. **Chunk 2:** New index.html structure (rows: Hero → Consensus → Snapshots → Drawers → What Changed → Today's Insight → Recommended → Upcoming → Sky → Planet → Drivers → Why → Confidence → Coming-Soon tabs)
3. **Chunk 3:** CSS rebuild for Ambient Intelligence OS aesthetic
4. **Chunk 4:** render.js wiring + drawer interactions + commit + push + verify

Each chunk reviewed before next. Desktop-first review.

---

**Status:** SPECIFICATION LOCKED 2026-06-08 evening. BUILD STARTS 2026-06-09 morning.
