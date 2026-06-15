#!/usr/bin/env python3
"""
Timing Weather — Intelligence Engine (v2.0 — Intelligence Dashboard).

Reads Alfie's authoritative natal chart + the overnight deep-research / council
convergence report, computes live geocentric tropical transits (Swiss Ephemeris),
classifies the current "operational weather" and writes state.json in the v2
camelCase contract.

v2.2.2 splits the Daily Reading into TWO independent Codex passes — tropicalReading
and vedicReading, each {state, body} — so the frameworks don't blend (each pass sees
only its own system's MDs). dailyReading is deprecated (emitted null).

v2 adds, on top of the v1.1 fields:
  - dailyReading {state, read}  — DEPRECATED in v2.2.2 (now null); was ONE unified
    Tropical+Vedic synthesis (collapsed the two horoscope cards)
  - dailyChanges {momentum, opportunity, pressure, volatility, comparedTo,
    lastComparedAt} or null — real day-over-day deltas from polar/state_history/
  - todaysInsight  — Codex one-liner (<=2 imperative sentences)
  - eventRadar {near, mid, long}  — council windows bucketed by days remaining
  - upcomingEvents [{title, theme, days}]  — top-3 future windows
  - nowBar {forecast, pressureLevel, momentumDirection, nextEventDays}
  - planetInfluences [{planet, role, influence, summary}]
  - confidence is now ALWAYS null (Confidence Engine deferred to v3 -> UI "Not Rated")

v1.1 adds: currentPhase, Active Sky (dominant/supporting/pressure/volatility
planet), Top Drivers, Forecast Trend (RETROACTIVE engine runs at past dates via
pyswisseph), Next Major Window (derived from the council convergence MD +
ephemeris, never hardcoded), Recommended Actions (Codex), Why-This-Forecast
evidence, and a confidence model that emits null (-> UI "Not Rated") rather than
fabricating a grade.

Engine-first, no fake data: any value that can't be honestly computed is null.

Stack note: the spec named pyephem, but this repo ships a proven, autonomous-safe
pyswisseph venv (polar/.venv, swisseph 2.10.03). Reusing it is the honest path —
Swiss Ephemeris is more accurate, handles past dates natively (needed for the
retroactive Forecast Trend), and already runs under launchd. Same natal constants
as polar/lunar_stress.py.

Sources (read each run):
  02_Astrology/Alfie/natal_context.md                  (YAML frontmatter = authoritative)
  02_Astrology/Alfie/deep_research_tropical_2026-2027.md
  02_Astrology/Alfie/deep_research_vedic_2026.md
  05_Council/octopus-debates/2026-06-06_predictive_convergence_review.md

Run:        polar/.venv/bin/python timing-weather/engine.py
Past date:  polar/.venv/bin/python timing-weather/engine.py --date 2026-05-10
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime, date, time, timedelta, timezone

import swisseph as swe

# --- paths ---------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))               # .../fitness-dashboard/timing-weather
DASH = os.path.dirname(HERE)                                     # .../fitness-dashboard
VAULT = os.path.dirname(os.path.dirname(DASH))                   # .../alfredo.v
ASTRO = os.path.join(VAULT, "02_Astrology", "Alfie")
COUNCIL = os.path.join(VAULT, "05_Council", "octopus-debates")
CACHE_DIR = os.path.join(DASH, "polar", "cache")                 # forecast-trend cache (idempotent)
HISTORY_DIR = os.path.join(DASH, "polar", "state_history")       # v2 daily snapshots (What Changed)

NATAL_MD = os.path.join(ASTRO, "natal_context.md")
TROPICAL_MD = os.path.join(ASTRO, "deep_research_tropical_2026-2027.md")
VEDIC_MD = os.path.join(ASTRO, "deep_research_vedic_2026.md")
COUNCIL_MD = os.path.join(COUNCIL, "2026-06-06_predictive_convergence_review.md")
OUT_PATH = os.path.join(HERE, "state.json")

# Dashboard-purpose-built astrology framework MDs (08_Drafts). These are HIGH-PRIORITY
# Codex narrative context — Alfie authored them specifically to drive THIS dashboard's
# tone, lifetime-arc framing, and which life domains surface. They outrank the
# deep-research reference docs when there is tension. Read in place (NOT moved — final
# placement undecided). Absolute paths into the vault root.
VEDIC_DASHBOARD_MD = os.path.join(VAULT, "08_Drafts", "2026-06-07_vedic_dashboard.md")
TROPICAL_DASHBOARD_MD = os.path.join(VAULT, "08_Drafts", "2026-06-07_tropical_dashboard.md")

# Lazy per-run cache for the two dashboard MDs (read once, reused by all three Codex
# prompt builders). Populated by load_astrology_dashboards().
ASTRO_CONTEXT = {}

SIGNS = ["Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
         "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"]
SIGN_IDX = {s: i for i, s in enumerate(SIGNS)}

# Major aspects: name -> exact angle.
ASPECTS = {"conjunction": 0, "sextile": 60, "square": 90, "trine": 120, "opposition": 180}
HARD = {"conjunction", "square", "opposition"}
SOFT = {"trine", "sextile"}

# Birth (UT): 16:22 CDT (UTC-5) -> 21:22 UT on 1990-08-30. Same as lunar_stress.py.
BIRTH = (1990, 8, 30, 21 + 22 / 60.0)
BIRTH_LAT, BIRTH_LON = 41.85, -87.65

# The five dominance-eligible planets and their forecast labels (v1.1 contract enum:
# EXPANSION|CONSOLIDATION|TRANSFORMATION|TRANSITION|PRESSURE|NEUTRAL). The Hero Sun
# visual keys on dominantPlanet (5 planet states); this maps the dominant planet to
# the contract's allowed forecast headline.
DOMINANT_LABEL = {
    "jupiter": "EXPANSION",
    "saturn": "CONSOLIDATION",
    "pluto": "TRANSFORMATION",
    "uranus": "TRANSITION",
    "venus": "EXPANSION",
}
# Static structural weight for "dominant" purposes (heavier = more structural).
STATIC_WEIGHT = {"pluto": 3.0, "saturn": 3.0, "uranus": 2.0, "jupiter": 2.0, "venus": 1.0}

SWE_BODY = {
    "sun": swe.SUN, "moon": swe.MOON, "mercury": swe.MERCURY, "venus": swe.VENUS,
    "mars": swe.MARS, "jupiter": swe.JUPITER, "saturn": swe.SATURN,
    "uranus": swe.URANUS, "neptune": swe.NEPTUNE, "pluto": swe.PLUTO,
}
TRANSIT_BODIES = list(SWE_BODY.keys())
FAST_BODIES = ["sun", "mercury", "venus", "mars"]

# --- structural facts sourced from the research + council ----------------
# Profection lord-of-year flip (deep_research_tropical: Capricorn/1st from birthday;
# Saturn becomes lord of year). Before -> Jupiter (Sagittarius/12th, age 35).
PROFECTION_FLIP = date(2026, 8, 30)
LORD_BEFORE_FLIP = "jupiter"
LORD_AFTER_FLIP = "saturn"

# --- Traditional / Hellenistic whole-sign profection facts (v2.2.3) ------
# Seven classical planets only. Domicile rulerships + exaltations drive the
# lord-of-year / lord-of-month time-lord logic and essential-dignity reads.
# (No modern rulers — Uranus/Neptune/Pluto are excluded from this framework.)
TRADITIONAL_RULERS = {
    "Aries": "Mars", "Taurus": "Venus", "Gemini": "Mercury", "Cancer": "Moon",
    "Leo": "Sun", "Virgo": "Mercury", "Libra": "Venus", "Scorpio": "Mars",
    "Sagittarius": "Jupiter", "Capricorn": "Saturn", "Aquarius": "Saturn",
    "Pisces": "Jupiter",
}
EXALTATION = {  # planet -> sign of exaltation (detriment/fall derive from the opposite sign)
    "Sun": "Aries", "Moon": "Taurus", "Mercury": "Virgo", "Venus": "Pisces",
    "Mars": "Capricorn", "Jupiter": "Cancer", "Saturn": "Libra",
}
ASC_SIGN = "Capricorn"          # 8°21' Capricorn = 1st whole-sign house (natal_context western.ascendant)
BIRTH_MONTH_DAY = (8, 30)       # solar return / birthday — anchors the monthly profection rotation
CHART_SECT = "diurnal"          # natal Sun above the horizon (8th house) → day chart
CLASSICAL_TRANSITS = ["sun", "moon", "mercury", "venus", "mars", "jupiter", "saturn"]

# Sade Sati Small Panoti active window (natal_context.md vedic.sade_sati).
SADE_SATI = (date(2025, 3, 30), date(2027, 6, 2))

# BaZi Da Yun shift (~Sep 2026, Output->payoff). natal_context.md bazi.da_yun.
BAZI_SHIFT = date(2026, 9, 15)

# Solar-arc directions perfecting in the 2026-27 window (exact dates from the natal
# convergence review / the daily-transit-snapshot SKILL's SA list). Principle #6:
# announced ONCE, on the exact day; the daily snapshot SKILL handles the orb-based
# approach separately. Past exacts (e.g. SA Jupiter cnj Sun, Feb 28 2026) are omitted.
SOLAR_ARC_EXACTS = [
    (date(2026, 7, 16), "Solar arc MC perfects square to natal Chiron today (exact) — angular and "
                        "structural; where competence and old sensitivity overlap peaks in the public role."),
    (date(2026, 10, 2), "Solar arc Saturn perfects sextile to the natal Ascendant today (exact) — a "
                        "structural support point on identity and form."),
    (date(2027, 1, 2),  "Solar arc Pluto perfects trine to natal Venus today (exact) — a long-arc shift "
                        "in how value and relationships consolidate."),
]

# Vedic Moon-Venus antardasha (relationship-positive) end (natal_context vedic.dashas).
VENUS_ANTARDASHA = (date(2025, 4, 1), date(2026, 12, 31))

# --- Vedic (sidereal Lahiri) horoscope facts -----------------------------
# Vimshottari pratyantardasha (sub-sub-period) windows inside the Moon mahadasha /
# Venus antardasha. These are FACTS lifted from deep_research_vedic_2026.md's KP
# timing table (Moon–Venus–Jupiter to early Aug, –Saturn to late Oct, –Mercury to
# early Dec, –Ketu to year-end), not computed from a dasha balance we don't hold.
# Looked up by date; outside the table we fall back to the Moon–Venus chain only.
VEDIC_MAHADASHA = "Moon"      # 2017-06-21 → 2027-06-21 (natal_context vedic.dashas)
VEDIC_ANTARDASHA = "Venus"    # 2025-04 → 2026-12 (first relationship-positive sub-period)
VEDIC_SUBPERIODS = [
    {"sub": "Jupiter", "start": date(2026, 4, 20), "end": date(2026, 8, 12)},
    {"sub": "Saturn",  "start": date(2026, 8, 12), "end": date(2026, 10, 29)},
    {"sub": "Mercury", "start": date(2026, 10, 29), "end": date(2026, 12, 7)},
    {"sub": "Ketu",    "start": date(2026, 12, 7),  "end": date(2026, 12, 31)},
]
# Sade Sati phase label (natal_context vedic.sade_sati). Window reuses SADE_SATI above.
SADE_SATI_PHASE = "Small Panoti"

# 27 nakshatras in sidereal order (each 13°20'). Used for the transit-Moon factor —
# a genuinely sidereal detail with no tropical analogue.
NAKSHATRAS = [
    "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra", "Punarvasu",
    "Pushya", "Ashlesha", "Magha", "Purva Phalguni", "Uttara Phalguni", "Hasta",
    "Chitra", "Swati", "Vishakha", "Anuradha", "Jyeshtha", "Mula", "Purva Ashadha",
    "Uttara Ashadha", "Shravana", "Dhanishta", "Shatabhisha", "Purva Bhadrapada",
    "Uttara Bhadrapada", "Revati",
]

# Council windows (from 2026-06-06 convergence review).
#   dominance_weight : feeds the dominant-planet competition (structurally strong only)
#   title            : short human label for the Next Major Window card
#   exact_degree     : a transit perfects to a natal degree inside the window (return / hard square)
#   doubled          : two time-lord systems converge on the same driver in the window
#   cross_system     : strength of tropical x Vedic convergence per the council MD
# These attributes are FACTS lifted from the council convergence review; the strength
# score is COMPUTED from them by window_strength() (no manual strength numbers).
COUNCIL_WINDOWS = [
    {"name": "Late May–early June clearing", "title": "Admin Clearing",
     "start": date(2026, 5, 28), "end": date(2026, 6, 8),
     "driver": "saturn", "polarity": "neutral", "dominance_weight": False,
     "exact_degree": False, "doubled": False, "cross_system": "weak"},
    {"name": "Jupiter return — chapter reset", "title": "Jupiter Return",
     "start": date(2026, 7, 12), "end": date(2026, 8, 1),
     "driver": "jupiter", "polarity": "positive", "dominance_weight": True,
     "exact_degree": True, "doubled": True, "cross_system": "weak"},
    {"name": "Embodiment pivot — Saturn year begins", "title": "Saturn Year Begins",
     "start": date(2026, 8, 12), "end": date(2026, 10, 8),
     "driver": "saturn", "polarity": "saturnian", "dominance_weight": True,
     "exact_degree": False, "doubled": False, "cross_system": "strong"},
    {"name": "Jupiter–Venus benefic window", "title": "Jupiter–Venus Benefic",
     "start": date(2026, 10, 7), "end": date(2026, 10, 8),
     "driver": "venus", "polarity": "positive", "dominance_weight": True,
     "exact_degree": True, "doubled": False, "cross_system": "moderate"},
    {"name": "Contract hinge", "title": "Contract Hinge",
     "start": date(2026, 10, 29), "end": date(2026, 12, 4),
     "driver": "venus", "polarity": "neutral", "dominance_weight": False,
     "exact_degree": False, "doubled": False, "cross_system": "moderate"},
    {"name": "Consolidation / Saturn-square-Saturn checkpoint", "title": "Saturn Checkpoint",
     "start": date(2027, 1, 8), "end": date(2027, 4, 20),
     "driver": "saturn", "polarity": "saturnian", "dominance_weight": True,
     "exact_degree": True, "doubled": False, "cross_system": "strong"},
]

# Strength driver weights (per-planet structural materializing power for window scoring).
STRENGTH_DRIVER_WEIGHT = {"jupiter": 2.2, "saturn": 2.5, "pluto": 2.5, "uranus": 2.0, "venus": 1.0}
CROSS_BONUS = {"weak": 0.0, "moderate": 0.5, "strong": 1.0, None: 0.0}

# 2026–2027 eclipses (approximate dates) for volatility proximity.
ECLIPSES = [date(2026, 2, 17), date(2026, 3, 3), date(2026, 8, 12), date(2026, 8, 28),
            date(2027, 2, 6), date(2027, 2, 20), date(2027, 7, 18), date(2027, 8, 2), date(2027, 8, 17)]

# Forecast-label ordinal for trendDirection (higher = more expansive/strengthening).
LABEL_ORDINAL = {"NEUTRAL": 0, "PRESSURE": 1, "CONSOLIDATION": 2, "TRANSITION": 2,
                 "TRANSFORMATION": 3, "EXPANSION": 4}

# v1.1 visual redesign — forecast-label taglines (design copy, not engine data).
# Maps 1:1 to the headline forecast; rendered under the hero. Covers every label
# the engine can emit (DOMINANT_LABEL set + quick_forecast PRESSURE/NEUTRAL +
# the design-spec DISRUPTION/ATTRACTION aliases).
SUBTITLE = {
    "EXPANSION":      "Doors opening — build the pipeline",
    "CONSOLIDATION":  "Make it concrete — formalize and commit",
    "TRANSFORMATION": "Deep restructuring underway",
    "TRANSITION":     "Things are shifting — stay adaptable",
    "DISRUPTION":     "Sudden shifts — stay adaptable",
    "ATTRACTION":     "Relationships and resources flow in",
    "PRESSURE":       "Under load — protect the essentials",
    "NEUTRAL":        "Quiet skies — steady as she goes",
}

# Section 5 (Planet Influences) one-line archetype summaries. DESIGN COPY (same
# class as SUBTITLE) — descriptive of each planet's standing function, NOT a
# fabricated metric. The signed influence number alongside each is engine-sourced.
PLANET_SUMMARY = {
    "Jupiter": "Opens doors and widens the pipeline",
    "Venus":   "Smooths relationships and resources",
    "Saturn":  "Adds weight, structure, and constraint",
    "Uranus":  "Injects sudden change and volatility",
    "Pluto":   "Forces deep, irreversible restructuring",
    "Mars":    "Raises friction and urgency",
    "Mercury": "Speeds communication and decisions",
    "Neptune": "Blurs signals — verify before acting",
    "Sun":     "Spotlights identity and recognition",
    "Moon":    "Colors mood and daily rhythm",
}

# Forecast-trend retroactive offsets in days (today minus N). Spec: ~27/17/5/0.
TREND_OFFSETS = [27, 17, 5, 0]


def log(msg):
    print(msg, flush=True)


def cap(s):
    return (s[:1].upper() + s[1:]) if s else None


def ordinal(n):
    """1 -> '1st', 2 -> '2nd', 12 -> '12th'. Used for whole-sign house labels."""
    suffix = "th" if 11 <= (n % 100) <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


# --- natal parse ---------------------------------------------------------
def to_lon(deg, minute, sign):
    return SIGN_IDX[sign] * 30 + deg + minute / 60.0


def parse_natal(path):
    """Parse authoritative natal longitudes from natal_context.md YAML frontmatter.
    Returns {body: abs_longitude} for the 10 planets + nodes/chiron/ASC/MC."""
    txt = open(path, encoding="utf-8").read()
    natal = {}
    # planet lines like:  sun: { pos: "7°14' Virgo", house: 8, ... }
    for m in re.finditer(r'(\w+):\s*\{\s*pos:\s*"(\d+)°(\d+)\'?\s*([A-Za-z]+)"', txt):
        body, d, mi, sign = m.group(1).lower(), int(m.group(2)), int(m.group(3)), m.group(4)
        if sign in SIGN_IDX:
            natal[body] = to_lon(d, mi, sign)
    # angles
    asc = re.search(r'ascendant:\s*"(\d+)°(\d+)\'?\s*([A-Za-z]+)"', txt)
    mc = re.search(r'midheaven:\s*"(\d+)°(\d+)\'?\s*([A-Za-z]+)"', txt)
    if asc and asc.group(3) in SIGN_IDX:
        natal["asc"] = to_lon(int(asc.group(1)), int(asc.group(2)), asc.group(3))
    if mc and mc.group(3) in SIGN_IDX:
        natal["mc"] = to_lon(int(mc.group(1)), int(mc.group(2)), mc.group(3))
    return natal


# --- astronomy helpers ---------------------------------------------------
def jd_now(now_utc):
    return swe.julday(now_utc.year, now_utc.month, now_utc.day,
                      now_utc.hour + now_utc.minute / 60.0 + now_utc.second / 3600.0)


def lon_of(jd, body):
    return swe.calc_ut(jd, body)[0][0]


def sign_of(lon):
    return SIGNS[int(lon // 30) % 12]


def angular_sep(a, b):
    return abs(((a - b + 180) % 360) - 180)


def closest_aspect(a, b, max_orb=6.0):
    """Closest major aspect between longitudes a,b within max_orb.
    Returns (aspect_name, orb) or (None, None)."""
    sep = angular_sep(a, b)
    best = None
    for name, exact in ASPECTS.items():
        orb = abs(sep - exact)
        if orb <= max_orb and (best is None or orb < best[1]):
            best = (name, orb)
    return best if best else (None, None)


def transit_aspects(transits, natal, max_orb=6.0):
    """All transit->natal major aspects within orb."""
    out = []
    for t, tl in transits.items():
        for n, nl in natal.items():
            asp, orb = closest_aspect(tl, nl, max_orb)
            if asp:
                out.append({"transit": t, "natal": n, "aspect": asp, "orb": round(orb, 2)})
    return out


def transits_at(when_utc):
    jd = jd_now(when_utc)
    out, missing = {}, []
    for name, body in SWE_BODY.items():
        try:
            out[name] = lon_of(jd, body)
        except Exception as e:
            missing.append(name)
            log(f"  transit compute failed for {name}: {e} — skipping")
    return out, missing


# --- scoring -------------------------------------------------------------
def active_windows(today):
    return [w for w in COUNCIL_WINDOWS if w["start"] <= today <= w["end"]]


def lord_of_year(today):
    return LORD_AFTER_FLIP if today >= PROFECTION_FLIP else LORD_BEFORE_FLIP


def score_dominance(today, transits, natal):
    """Score the five dominance-eligible planets. Returns (scores, components)."""
    lord = lord_of_year(today)
    acts = active_windows(today)
    scores, comps = {}, {}
    for p in DOMINANT_LABEL:
        static = STATIC_WEIGHT[p]
        lord_bump = 6.0 if p == lord else 0.0
        window_bump = 0.0
        for w in acts:
            if w["dominance_weight"] and w["driver"] == p:
                window_bump += 5.0
        tl = transits[p]
        best_orb, best_asp, best_nat = None, None, None
        for n, nl in natal.items():
            asp, orb = closest_aspect(tl, nl, 6.0)
            if asp and (best_orb is None or orb < best_orb):
                best_orb, best_asp, best_nat = orb, asp, n
        aspect_pts = round((6.0 - best_orb) / 6.0 * 5.0, 2) if best_orb is not None else 0.0
        total = static + lord_bump + window_bump + aspect_pts
        scores[p] = round(total, 2)
        comps[p] = {"static": static, "lord": lord_bump, "window": window_bump,
                    "aspect": aspect_pts, "aspect_to": best_nat, "aspect_name": best_asp,
                    "aspect_orb": best_orb}
    return scores, comps


def clamp(v):
    return max(0, min(100, int(round(v))))


# Each score_* returns (clamped_value, contribs) where contribs is a list of
# (factor_label, detail_string, points). factor_label is the short human-readable
# name used by drivers[] / evidence[]; detail is kept for the audit trail.
def score_opportunity(today, transits, natal, aspects):
    c = []
    benefics = {"sun", "venus", "jupiter"}
    for a in aspects:
        if a["transit"] == "jupiter" and a["natal"] in benefics and (a["aspect"] in SOFT or a["aspect"] == "conjunction"):
            c.append(("Jupiter Benefic Aspect", f"Jupiter {a['aspect']} natal {a['natal']} ({a['orb']}°)", 25))
        if a["transit"] == "venus" and a["natal"] in {"sun", "moon", "venus", "jupiter", "asc"} and (a["aspect"] in SOFT or a["aspect"] == "conjunction"):
            c.append(("Venus Support", f"Venus {a['aspect']} natal {a['natal']} ({a['orb']}°)", 10))
    if lord_of_year(today) == "jupiter":
        c.append(("Jupiter Lord of Year", "Jupiter is lord of the year (benefic regime)", 15))
    for w in active_windows(today):
        if w["polarity"] == "positive":
            c.append((f"Inside {w['title']}", f"inside positive council window: {w['name']}", 20))
    for w in COUNCIL_WINDOWS:
        if w["polarity"] != "positive" or not w["dominance_weight"]:
            continue
        days = (w["start"] - today).days
        if 0 < days <= 45:
            c.append((f"Approaching {w['title']}", f"approaching benefic window: {w['name']} ({days}d)",
                      int(round((45 - days) / 45 * 15))))
            break
    if VENUS_ANTARDASHA[0] <= today <= VENUS_ANTARDASHA[1]:
        c.append(("Venus Antardasha", "Vedic Moon–Venus antardasha (relationship-positive)", 10))
    if today >= PROFECTION_FLIP:
        c.append(("Favorable Year Chart", "Varshaphal Muntha in 9th (favorable)", 8))
    return clamp(sum(p for _, _, p in c)), c


def score_pressure(today, transits, natal, aspects):
    c = []
    pers = {"sun", "moon", "mercury", "venus", "mars", "asc", "saturn", "neptune"}
    for a in aspects:
        if a["transit"] == "saturn" and a["natal"] in pers and a["aspect"] in HARD:
            c.append(("Saturn Pressure", f"Saturn {a['aspect']} natal {a['natal']} ({a['orb']}°)", 25))
        if a["transit"] == "mars" and a["natal"] in {"sun", "moon", "mercury", "venus", "mars", "asc"} and a["aspect"] in HARD:
            c.append(("Mars Friction", f"Mars {a['aspect']} natal {a['natal']} ({a['orb']}°)", 12))
    if SADE_SATI[0] <= today <= SADE_SATI[1]:
        c.append(("Foundations Pressure", "Sade Sati (Small Panoti) — pressure on foundations", 15))
    for w in active_windows(today):
        if w["polarity"] == "saturnian":
            c.append((f"Inside {w['title']}", f"inside Saturnian council window: {w['name']}", 20))
        elif w["polarity"] == "neutral" and w["driver"] == "saturn":
            c.append(("Admin Load", f"inside admin/clearing window: {w['name']}", 8))
    return clamp(sum(p for _, _, p in c)), c


def score_volatility(today, transits, natal, aspects):
    c = []
    for a in aspects:
        if a["transit"] == "uranus":
            if a["aspect"] in HARD:
                c.append(("Uranus Volatility", f"Uranus {a['aspect']} natal {a['natal']} ({a['orb']}°)", 25))
            elif a["aspect"] in SOFT:
                c.append(("Uranus Volatility", f"Uranus {a['aspect']} natal {a['natal']} ({a['orb']}°)", 8))
        if a["natal"] in {"asc", "mc"} and a["orb"] <= 3.0 and a["transit"] in {"saturn", "uranus", "pluto", "mars", "jupiter"}:
            c.append(("Angular Hit", f"{a['transit']} {a['aspect']} natal {a['natal']} (angular, {a['orb']}°)", 12))
    near = min((abs((e - today).days) for e in ECLIPSES), default=999)
    if near <= 14:
        c.append(("Eclipse Window", f"eclipse within {near} days", 25))
    return clamp(sum(p for _, _, p in c)), c


def score_momentum(today, transits, natal, aspects):
    c = []
    fast = sum(1 for a in aspects if a["transit"] in FAST_BODIES and a["orb"] <= 3.0)
    if fast:
        c.append(("Fast Transits", f"{fast} fast transit(s) exact within 3°", 8 * fast))
    for w in COUNCIL_WINDOWS:
        if not w["dominance_weight"]:
            continue
        if w["start"] <= today <= w["end"]:
            c.append((f"Inside {w['title']}", f"inside strong window peak: {w['name']}", 25))
            break
        days = (w["start"] - today).days
        if 0 < days <= 45:
            c.append((f"Approaching {w['title']}", f"approaching {w['name']} ({days}d)",
                      int(round((45 - days) / 45 * 18))))
            break
    dy = abs((BAZI_SHIFT - today).days)
    if dy <= 120:
        c.append(("Cycle Shift", f"BaZi Da Yun shift within {dy} days", int(round((120 - dy) / 120 * 20))))
    return clamp(sum(p for _, _, p in c)), c


def aggregate(contribs):
    """Sum points by factor label, preserving first-seen order. Returns [(label, points)]."""
    agg = {}
    for label, _detail, pts in contribs:
        agg[label] = agg.get(label, 0) + pts
    return list(agg.items())


def build_drivers(opp_c):
    """Top 3 positive structural drivers of the current forecast (Section 5)."""
    ranked = sorted(aggregate(opp_c), key=lambda x: -x[1])
    return [{"name": n, "score": p} for n, p in ranked[:3] if p > 0]


def build_evidence(opp, opp_c, pre_c, vol_c):
    """Why-This-Forecast (Section 10), v1.1 nested contract:
        {expansionScore, contributors[{factor,score:+}], reducers[{factor,score:-}]}
    expansionScore is the headline opportunity score (0-100); contributors are the
    positive opportunity drivers, reducers the pressure/volatility detractors —
    each signed and sorted by magnitude. Coherent with the forecast headline."""
    contributors = sorted(({"factor": n, "score": p} for n, p in aggregate(opp_c) if p > 0),
                          key=lambda f: -f["score"])[:5]
    reducers = sorted(({"factor": n, "score": -p} for n, p in aggregate(pre_c) + aggregate(vol_c) if p > 0),
                      key=lambda f: f["score"])[:5]
    return {"expansionScore": opp, "contributors": contributors, "reducers": reducers}


def pick_supporting(today, aspects, dominant):
    cands = []
    for a in aspects:
        if a["transit"] in {"jupiter", "venus"} and a["transit"] != dominant and (a["aspect"] in SOFT or a["aspect"] == "conjunction"):
            cands.append((a["transit"], a["orb"]))
    if VENUS_ANTARDASHA[0] <= today <= VENUS_ANTARDASHA[1] and "venus" != dominant:
        cands.append(("venus", 3.0))
    if lord_of_year(today) == "jupiter" and dominant != "jupiter":
        cands.append(("jupiter", 2.0))
    if not cands:
        return None
    cands.sort(key=lambda x: x[1])
    return cands[0][0]


def pick_pressure(today, aspects, dominant):
    cands = []
    for a in aspects:
        if a["transit"] in {"saturn", "mars", "pluto"} and a["aspect"] in HARD:
            w = {"saturn": 3, "pluto": 2, "mars": 1}[a["transit"]]
            cands.append((a["transit"], w, a["orb"]))
    if not cands:
        if SADE_SATI[0] <= today <= SADE_SATI[1]:
            return "saturn"
        return None
    cands.sort(key=lambda x: (-x[1], x[2]))
    return cands[0][0]


def pick_volatility(aspects):
    """Strongest volatility planet — Uranus-related first, then angular disruptors."""
    cands = []
    for a in aspects:
        if a["transit"] == "uranus":
            cands.append(("uranus", 2 if a["aspect"] in HARD else 1, a["orb"]))
    if not cands:
        for a in aspects:
            if a["natal"] in {"asc", "mc"} and a["orb"] <= 3.0 and a["transit"] in {"pluto", "mars", "saturn"}:
                cands.append((a["transit"], 1, a["orb"]))
    if not cands:
        return None
    cands.sort(key=lambda x: (-x[1], x[2]))
    return cands[0][0]


def duration_days(today, dominant, comps, natal):
    """Days the current dominant 'weather' plausibly persists."""
    c = comps[dominant]
    driver = max(("lord", c["lord"]), ("window", c["window"]), ("aspect", c["aspect"]),
                 ("static", c["static"]), key=lambda x: x[1])[0]
    if driver == "lord" and today < PROFECTION_FLIP:
        return (PROFECTION_FLIP - today).days
    if driver == "window":
        for w in active_windows(today):
            if w["dominance_weight"] and w["driver"] == dominant:
                return max(1, (w["end"] - today).days)
    nat = c.get("aspect_to")
    if nat and nat in natal:
        nl = natal[nat]
        for d in range(0, 400):
            jd = jd_now((datetime.combine(today, datetime.min.time()) + timedelta(days=d)).replace(tzinfo=timezone.utc))
            asp, orb = closest_aspect(lon_of(jd, SWE_BODY[dominant]), nl, 30.0)
            if orb is None or orb > 3.0:
                return max(1, d)
    if today < PROFECTION_FLIP:
        return (PROFECTION_FLIP - today).days
    return 30


def confidence_for(dominant, texts):
    """Corroboration count of the dominant planet across the two research MDs + council.
    >=2 -> High, 1 -> Medium, 0 -> Low. Returns null if no source text could be read
    (then the UI shows 'Not Rated' rather than a fabricated grade)."""
    if not any(t.strip() for t in texts):
        return None
    n = sum(1 for t in texts if re.search(rf"\b{dominant}\b", t, re.I))
    return "High" if n >= 2 else "Medium" if n == 1 else "Low"


# --- Section 2: Current Phase --------------------------------------------
def classify_phase(today, forecast, next_days):
    """Map state -> a named phase + its date span. Returns (name, start, end) where
    start/end are dates or None (None -> caller fills today..today+duration)."""
    acts = active_windows(today)
    for w in acts:
        if w.get("dominance_weight"):
            pol = w["polarity"]
            name = ("Expansion Window" if pol == "positive"
                    else "Consolidation Window" if pol == "saturnian"
                    else "Activation Window")
            return name, w["start"], w["end"]
    if acts:
        # in a weak/admin window — clearing precedes activation -> Preparation
        w = acts[0]
        return "Preparation Window", w["start"], w["end"]
    # no active window: a major approaching soon -> Preparation; else by forecast
    if next_days is not None and 0 < next_days <= 30:
        return "Preparation Window", None, None
    name = {"EXPANSION": "Expansion Window", "CONSOLIDATION": "Consolidation Window",
            "TRANSFORMATION": "Transition Window", "TRANSITION": "Transition Window",
            "PRESSURE": "Recovery Window", "NEUTRAL": "Recovery Window"}.get(forecast, "Transition Window")
    return name, None, None


# --- Section 7: Next Major Window ----------------------------------------
def window_strength(w):
    """0-10 strength COMPUTED from the window's structural attributes (facts from the
    council MD). No manual strength numbers."""
    s = 2.0
    s += STRENGTH_DRIVER_WEIGHT.get(w["driver"], 1.0)
    if w["exact_degree"]:
        s += 3.0
    if w["doubled"]:
        s += 1.5
    s += CROSS_BONUS.get(w["cross_system"], 0.0)
    if w["polarity"] in ("positive", "saturnian"):
        s += 0.5
    return round(max(0.0, min(10.0, s)), 1)


def next_major_window(today):
    """Next major window = max(strength / sqrt(days)) over future windows — balances
    'highest strength' against 'closest in future' per spec. Derived from the council
    convergence MD + ephemeris; no hardcoded dates."""
    best, best_rank = None, None
    for w in COUNCIL_WINDOWS:
        days = (w["start"] - today).days
        if days <= 0:
            continue
        strength = window_strength(w)
        rank = strength / (days ** 0.5)
        if best_rank is None or rank > best_rank:
            best_rank, best = rank, (w, days, strength)
    if not best:
        return None
    w, days, strength = best
    return {
        "title": w["title"],
        "date": w["start"].isoformat(),
        "daysRemaining": days,
        "category": cap(DOMINANT_LABEL[w["driver"]].lower()),
        "strength": strength,
    }


# --- Section 6: Forecast Trend (retroactive engine runs) -----------------
def quick_forecast(target_date, natal):
    """Lightweight retroactive run: dominant planet -> forecast label + opportunity,
    using the real ephemeris for target_date. No narrative/Codex (trend is label-only)."""
    when = datetime.combine(target_date, time(12, 0)).replace(tzinfo=timezone.utc)
    transits, _ = transits_at(when)
    aspects = transit_aspects(transits, natal)
    scores, _ = score_dominance(target_date, transits, natal)
    dominant = max(scores, key=scores.get)
    label = DOMINANT_LABEL[dominant]
    opp, _ = score_opportunity(target_date, transits, natal, aspects)
    return label, opp


def trend_point(target_date, natal):
    """One {date,label} trend point, cached idempotently to polar/cache/trend_<date>.json."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache = os.path.join(CACHE_DIR, f"trend_{target_date.isoformat()}.json")
    if os.path.exists(cache):
        try:
            d = json.load(open(cache))
            # tolerate legacy caches keyed on "label" (pre-v1.1-visual rename).
            st = d.get("state", d.get("label"))
            return {"date": d["date"], "state": st}, d.get("opportunity")
        except Exception:
            pass
    try:
        label, opp = quick_forecast(target_date, natal)
    except Exception as e:
        log(f"  trend run failed for {target_date}: {e} — dropping point")
        return None, None
    rec = {"date": target_date.isoformat(), "state": label, "opportunity": opp}
    try:
        json.dump(rec, open(cache, "w"), indent=2)
    except Exception as e:
        log(f"  could not cache trend point {target_date}: {e}")
    return {"date": rec["date"], "state": rec["state"]}, opp


def forecast_trend(today, natal):
    """Run the engine retroactively at TREND_OFFSETS days back; return (points, direction).
    Drops any failed point but keeps the rest; direction needs >=2 points."""
    pts = []
    for off in TREND_OFFSETS:
        p, _opp = trend_point(today - timedelta(days=off), natal)
        if p:
            pts.append(p)
    if len(pts) < 2:
        return pts, None
    first_o = LABEL_ORDINAL.get(pts[0]["state"], 0)
    last_o = LABEL_ORDINAL.get(pts[-1]["state"], 0)
    # Direction is regime-based: the forecast label is the signal. A tie means the
    # weather regime is unchanged across the window -> Stable (no overfitting to
    # transient fast-planet aspect noise).
    direction = "Strengthening" if last_o > first_o else "Weakening" if last_o < first_o else "Stable"
    return pts, direction


# --- High-priority dashboard framework (Codex narrative context) ---------
_MD_CACHE = {}


def read_md(path, cap_chars=None):
    """Read a markdown source once (cached per run). Missing/unreadable -> '' (PVR:
    never fabricate). Optional cap_chars trims very long reference docs so the Codex
    prompt stays a sane size; the purpose-built dashboard MDs are passed uncapped."""
    if path not in _MD_CACHE:
        try:
            _MD_CACHE[path] = open(path, encoding="utf-8").read().strip()
        except Exception as e:
            log(f"  could not read MD {path}: {e}")
            _MD_CACHE[path] = ""
    txt = _MD_CACHE[path]
    return txt[:cap_chars] if cap_chars else txt


def load_astrology_dashboards():
    """Load Alfie's two dashboard-purpose-built astrology MDs (Vedic + Tropical) from
    08_Drafts. Cached once per run in ASTRO_CONTEXT. A missing/unreadable file degrades
    to '' (PVR: never fabricate) so the engine still ships its narrative."""
    if ASTRO_CONTEXT:
        return ASTRO_CONTEXT
    for key, path in (("vedic_dashboard", VEDIC_DASHBOARD_MD),
                      ("tropical_dashboard", TROPICAL_DASHBOARD_MD)):
        try:
            ASTRO_CONTEXT[key] = open(path, encoding="utf-8").read().strip()
        except Exception as e:
            log(f"  could not read dashboard MD {path}: {e}")
            ASTRO_CONTEXT[key] = ""
    return ASTRO_CONTEXT


def astro_framework_block():
    """Assemble the HIGH-PRIORITY framework context injected into the Codex narrative
    prompts (daily reading, today's insight, recommended actions). Frames the two
    08_Drafts MDs as Alfie's own structural framework for this dashboard — primary for
    tone, lifetime-arc framing, and which life domains to surface; deep-research docs
    are reference background only. Names specific sections so Codex can reason from
    them. Returns '' when neither MD could be read (graceful degrade)."""
    ctx = load_astrology_dashboards()
    ved, trop = ctx.get("vedic_dashboard", ""), ctx.get("tropical_dashboard", "")
    if not ved and not trop:
        return ""
    parts = [
        "=== ALFIE'S STRUCTURAL FRAMEWORK — HIGH PRIORITY (purpose-built for THIS dashboard) ===",
        "The document(s) below are Alfie's own structural framework, written specifically to "
        "drive this dashboard. Treat them as the PRIMARY authority for tone, lifetime-arc "
        "framing, and WHICH life domains to surface (career/authority, property/home, "
        "financial reorganization, relationships — romance is explicitly NOT the headline). "
        "They OUTWEIGH any deep-research or reference/background material when there is tension; "
        "that other material is background only. Lean on their specific logic — the External "
        "Manifestation Windows (especially the strongest, Aug 12 – Sep 5 2026), the Moon–Venus "
        "antardasha, the 12th-House annual profection (a foundation/preparation year, not a "
        "coronation), the 'valuation cycle you work, not a predetermined one' framing, the June = valuation "
        "month read, and the self-valuation / 2nd-House North Node lifetime arc (servicing "
        "institutions → owning unconventional value, IP over salary). Manifestation requires "
        "agency — outcomes depend on decisions, not on the calendar. BUT still obey the output "
        "rules above: translate everything into plain, observable language — never name a "
        "planet, sign, house, window label, or tradition in your OUTPUT.",
    ]
    if ved:
        parts.append(
            "--- VEDIC DASHBOARD (Moon–Venus · External Manifestation Windows · Strongest Life "
            "Themes · Most Likely 2026 Outcome sequence) ---\n" + ved)
    if trop:
        parts.append(
            "--- TROPICAL DASHBOARD (Natal Structural Signature · 2026 Annual Profection · June "
            "Structural Summary · Strategic Focus · Master Summary) ---\n" + trop)
    parts.append("=== END STRUCTURAL FRAMEWORK ===")
    return "\n\n".join(parts)


# --- Section 9: Recommended Actions (Codex) ------------------------------
def codex_actions(forecast, dominant, pressure_src, phase):
    """4 do's + 3 avoidances via ~/bin/llm --model codex (forces Codex, no claude-handoff
    -> Cowork-safe). Returns (recommendations[<=4], avoidances[<=3]); empty on failure."""
    llm = os.path.expanduser("~/bin/llm")
    if not os.path.exists(llm):
        log("  ~/bin/llm not found — actions empty")
        return [], []
    framework = astro_framework_block()
    framework_section = ("\n\n" + framework + "\n") if framework else ""
    prompt = (
        "You are advising a high-output operator on how to play the current period of his "
        "life. He hates fluff and astrology jargon — NEVER mention planets, signs, transits, "
        "or 'energy'. Output ONLY two labeled lists, nothing else.\n\n"
        f"Current period: {phase}. Headline mode: {forecast}. The period favors building, "
        f"preparation and pipeline more than locking in final commitments; there is real "
        f"pressure/constraint in the background."
        + framework_section + "\n"
        "Give EXACTLY 4 do-more-of actions and EXACTLY 3 things to avoid. Each item is 2-4 "
        "words, action-oriented, concrete (e.g. 'Build pipeline', 'Schedule meetings', "
        "'Avoid irreversible decisions'). Format EXACTLY:\n"
        "DO: <action>\nDO: <action>\nDO: <action>\nDO: <action>\n"
        "AVOID: <thing>\nAVOID: <thing>\nAVOID: <thing>"
    )
    try:
        out = subprocess.run([llm, "--lane", "reasoning", "--model", "codex", prompt],
                             capture_output=True, text=True, timeout=180, cwd=DASH)
        if out.returncode != 0:
            log(f"  codex actions exited {out.returncode}: {out.stderr.strip()[:200]}")
            return [], []
    except Exception as e:
        log(f"  codex actions failed (non-fatal): {e}")
        return [], []
    dos, avoids = [], []
    for line in out.stdout.splitlines():
        line = line.strip().lstrip("-*0123456789. ").strip()
        m = re.match(r'(?i)^DO:\s*(.+)$', line)
        if m:
            dos.append(m.group(1).strip().rstrip("."))
            continue
        m = re.match(r'(?i)^AVOID:\s*(.+)$', line)
        if m:
            avoids.append(m.group(1).strip().rstrip("."))
    return dos[:4], avoids[:3]


# --- Section 9: What Changed (state persistence) -------------------------
HISTORY_KEYS = ("forecast", "momentum", "opportunity", "pressure", "volatility", "expansionScore")


def latest_prior_snapshot(today):
    """Most recent persisted snapshot STRICTLY BEFORE today (so a same-day re-run
    still compares against yesterday, not against itself). Returns (date, dict) or
    (None, None) when no prior history exists."""
    if not os.path.isdir(HISTORY_DIR):
        return None, None
    best = None
    for fn in os.listdir(HISTORY_DIR):
        m = re.match(r"(\d{4}-\d{2}-\d{2})\.json$", fn)
        if not m:
            continue
        d = datetime.strptime(m.group(1), "%Y-%m-%d").date()
        if d >= today:
            continue
        if best is None or d > best[0]:
            try:
                data = json.load(open(os.path.join(HISTORY_DIR, fn)))
            except Exception:
                continue
            best = (d, data)
    return best if best else (None, None)


def compute_daily_changes(today, metrics, expansion_score, now):
    """Real day-over-day deltas vs the most recent prior snapshot. None on the first
    day (no prior) -> UI shows 'Tracking begins today'. Honest about staleness: the
    snapshot we actually compared against is named in `comparedTo`."""
    prior_date, prior = latest_prior_snapshot(today)
    if not prior:
        return None
    cur = {"momentum": metrics["momentum"], "opportunity": metrics["opportunity"],
           "pressure": metrics["pressure"], "volatility": metrics["volatility"],
           "expansionScore": expansion_score}
    deltas = {}
    for k in ("momentum", "opportunity", "pressure", "volatility"):
        base = prior.get(k)
        deltas[k] = (cur[k] - base) if isinstance(base, (int, float)) else None
    deltas["comparedTo"] = prior_date.isoformat()
    deltas["lastComparedAt"] = now.isoformat(timespec="seconds")
    return deltas


def write_history_snapshot(today, forecast, metrics, expansion_score, now):
    """Persist today's snapshot to polar/state_history/<date>.json (overwrites a
    same-day re-run idempotently). Written AFTER deltas are computed so it never
    pollutes its own comparison. Non-fatal on failure."""
    os.makedirs(HISTORY_DIR, exist_ok=True)
    snap = {
        "forecast": forecast,
        "momentum": metrics["momentum"],
        "opportunity": metrics["opportunity"],
        "pressure": metrics["pressure"],
        "volatility": metrics["volatility"],
        "expansionScore": expansion_score,
        "timestamp": now.isoformat(timespec="seconds"),
    }
    path = os.path.join(HISTORY_DIR, f"{today.isoformat()}.json")
    try:
        with open(path, "w") as f:
            json.dump(snap, f, indent=2)
    except Exception as e:
        log(f"  could not write history snapshot {path}: {e}")
    return snap


# --- Section 4: Event Radar (timing buckets, NO planet glyphs) ------------
def event_radar(today):
    """Future council windows bucketed purely by days remaining:
    Near (<=45) / Mid (46-180) / Long (>180). Pure timing — the UI renders rings
    with day counts, never planet symbols."""
    near, mid, lng = [], [], []
    for w in COUNCIL_WINDOWS:
        days = (w["start"] - today).days
        if days <= 0:
            continue
        item = {"title": w["title"], "days": days}
        (near if days <= 45 else mid if days <= 180 else lng).append(item)
    for b in (near, mid, lng):
        b.sort(key=lambda x: x["days"])
    return {"near": near, "mid": mid, "long": lng}


# --- Section 6: Upcoming Events (top-3 future windows) -------------------
def upcoming_events(today, limit=3):
    fut = []
    for w in COUNCIL_WINDOWS:
        days = (w["start"] - today).days
        if days <= 0:
            continue
        theme = cap(DOMINANT_LABEL.get(w["driver"], "").lower()) or cap(w["driver"])
        fut.append({"title": w["title"], "theme": theme, "days": days})
    fut.sort(key=lambda x: x["days"])
    return fut[:limit]


# --- Section 2: Now Bar (quick-render glance row) ------------------------
def pressure_level(p):
    if p is None:
        return None
    return "Low" if p < 34 else "Moderate" if p < 67 else "High"


def momentum_direction(daily_changes, trend_dir):
    """Day-over-day momentum delta first (real persistence); fall back to the
    regime trend direction when there's no prior snapshot yet."""
    if daily_changes and isinstance(daily_changes.get("momentum"), (int, float)):
        d = daily_changes["momentum"]
        return "Rising" if d > 0 else "Falling" if d < 0 else "Steady"
    return {"Strengthening": "Rising", "Weakening": "Falling",
            "Stable": "Steady"}.get(trend_dir, "Steady")


def build_now_bar(forecast, pre, daily_changes, trend_dir, nxt):
    return {
        "forecast": forecast,
        "pressureLevel": pressure_level(pre),
        "momentumDirection": momentum_direction(daily_changes, trend_dir),
        "nextEventDays": nxt["daysRemaining"] if nxt else None,
    }


# --- Section 5: Planet Influences ---------------------------------------
def _planet_contrib_points(planet, contribs):
    """Sum the scoring points a given planet contributed within one metric's
    contribs list (matching the planet name in either the label or the audit
    detail). Returns total points (0 if none)."""
    total = 0
    for label, detail, pts in contribs:
        if re.search(rf"\b{planet}\b", label, re.I) or re.search(rf"\b{planet}\b", detail, re.I):
            total += pts
    return total


def build_planet_influences(dominant, supporting, pressure_src, volatility_src,
                            opp_c, pre_c, vol_c, metrics):
    """One row per role: planet, role, signed engine influence, archetype summary.
    Influence is engine-sourced (the planet's net scoring contribution to its metric,
    signed +benefic / -pressure / -volatility); summary is design copy (PLANET_SUMMARY)."""
    rows = []

    def add(planet_cap, role, contribs, sign, fallback_metric):
        if not planet_cap:
            return
        pts = _planet_contrib_points(planet_cap.lower(), contribs)
        infl = sign * (pts if pts else fallback_metric)
        rows.append({
            "planet": planet_cap,
            "role": role,
            "influence": int(round(infl)),
            "summary": PLANET_SUMMARY.get(planet_cap, "Active in the current sky"),
        })

    add(cap(dominant),       "Dominant",   opp_c, +1, metrics["opportunity"])
    add(cap(supporting),     "Supporting", opp_c, +1, max(1, metrics["opportunity"] // 3))
    add(cap(pressure_src),   "Pressure",   pre_c, -1, metrics["pressure"])
    add(cap(volatility_src), "Volatility", vol_c, -1, metrics["volatility"])
    return rows


# --- Vedic horoscope (sidereal Lahiri) -----------------------------------
def birth_jd():
    return swe.julday(BIRTH[0], BIRTH[1], BIRTH[2], BIRTH[3])


def sidereal_natal(natal):
    """Natal sidereal longitudes = tropical natal − ayanamsha(at birth). Lahiri.
    natal[] holds tropical ecliptic longitudes parsed from natal_context.md; for a
    single ecliptic longitude, sidereal = tropical − ayanamsha is exact. Sanity-
    checked against natal_context vedic signs (Sun→Leo, Moon→Sagittarius, etc.)."""
    swe.set_sid_mode(swe.SIDM_LAHIRI, 0, 0)
    aya = swe.get_ayanamsa_ut(birth_jd())
    sid = {b: (lon - aya) % 360 for b, lon in natal.items()}
    # Ketu = opposite the (north) node, if present.
    if "north_node" in sid:
        sid["ketu"] = (sid["north_node"] + 180) % 360
        sid["rahu"] = sid["north_node"]
    return sid


def vedic_transits_at(when_utc):
    """Today's sidereal (Lahiri) transit longitudes."""
    swe.set_sid_mode(swe.SIDM_LAHIRI, 0, 0)
    jd = jd_now(when_utc)
    flags = swe.FLG_SWIEPH | swe.FLG_SIDEREAL
    out, missing = {}, []
    for name, body in SWE_BODY.items():
        try:
            out[name] = swe.calc_ut(jd, body, flags)[0][0]
        except Exception as e:
            missing.append(name)
            log(f"  vedic transit compute failed for {name}: {e} — skipping")
    return out, missing


def vedic_subperiod(today):
    """Current Vimshottari chain (Mahadasha–Antardasha–Pratyantardasha) for `today`.
    Returns (chain_string, sub_lord_or_None)."""
    for w in VEDIC_SUBPERIODS:
        if w["start"] <= today <= w["end"]:
            return (f"{VEDIC_MAHADASHA}–{VEDIC_ANTARDASHA}–{w['sub']}", w["sub"])
    # Outside the sourced sub-period table — fall back to the MD–AD chain only.
    if VENUS_ANTARDASHA[0] <= today <= VENUS_ANTARDASHA[1]:
        return (f"{VEDIC_MAHADASHA}–{VEDIC_ANTARDASHA}", None)
    return (VEDIC_MAHADASHA, None)


def nakshatra_of(lon):
    return NAKSHATRAS[int(lon // (360.0 / 27)) % 27]


def nakshatra_pada_of(lon):
    """Pada (1–4) = which 3°20' quarter of the 13°20' nakshatra `lon` falls in."""
    nak_len = 360.0 / 27          # 13.3333°
    pada_len = nak_len / 4        # 3.3333°
    return int((lon % nak_len) / pada_len) + 1


# --- Moon Now (live Moon position, both systems) -------------------------
def natal_placidus_cusps():
    """Alfie's natal Placidus house cusps (tropical), house 1..12. Computed once from
    the birth chart — a transiting body's natal-house placement is which cusp pair it
    falls between. swe.houses returns tropical cusps regardless of sidereal mode."""
    raw = swe.houses(birth_jd(), BIRTH_LAT, BIRTH_LON, b"P")[0]
    return list(raw[1:13]) if len(raw) >= 13 else list(raw[:12])


def house_of(cusps, lon):
    """Which natal house (1..12) a longitude falls in, given ordered house cusps."""
    lon %= 360
    for i in range(12):
        a = cusps[i] % 360
        span = (cusps[(i + 1) % 12] - a) % 360
        if (lon - a) % 360 < span:
            return i + 1
    return None


def moon_now(now_utc, natal):
    """Live Moon in BOTH systems for state.json `moonNow`. Tropical = geocentric
    ecliptic (sign/degree + natal Placidus house). Vedic = Lahiri sidereal
    (sign/degree/nakshatra/pada + whole-sign house from the sidereal Lagna).
    PVR: returns None on any ephemeris failure — never fabricated."""
    try:
        jd = jd_now(now_utc)
        # --- Tropical (compute houses before switching sidereal mode) ---
        try:
            cusps = natal_placidus_cusps()
            trop_house = house_of(cusps, lon_of(jd, swe.MOON))
        except Exception as e:
            log(f"  moonNow: natal houses failed ({e}) — tropical house null")
            trop_house = None
        trop_lon = lon_of(jd, swe.MOON)
        tropical = {"sign": sign_of(trop_lon), "degree": round(trop_lon % 30, 2),
                    "house": trop_house}
        # --- Vedic (Lahiri sidereal) ---
        swe.set_sid_mode(swe.SIDM_LAHIRI, 0, 0)
        sid_lon = swe.calc_ut(jd, swe.MOON, swe.FLG_SWIEPH | swe.FLG_SIDEREAL)[0][0]
        # whole-sign house off the sidereal Lagna (derive from chart; MD says Sagittarius)
        try:
            lagna_idx = int(sidereal_natal(natal)["asc"] // 30) % 12
        except Exception:
            lagna_idx = SIGN_IDX["Sagittarius"]
        moon_idx = int(sid_lon // 30) % 12
        vedic = {"sign": sign_of(sid_lon), "degree": round(sid_lon % 30, 2),
                 "nakshatra": nakshatra_of(sid_lon),
                 "nakshatra_pada": nakshatra_pada_of(sid_lon),
                 "house": (moon_idx - lagna_idx) % 12 + 1}
        return {
            "timestamp": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "tropical": tropical,
            "vedic": vedic,
        }
    except Exception as e:
        log(f"  moonNow computation failed: {e} — emitting null")
        return None


# Natal points to weight when picking the strongest Vedic transit (Lagna/Moon/Sun
# carry the chart in Vimshottari practice), then everything else.
VEDIC_PRIORITY = {"moon": 3, "asc": 3, "sun": 2, "mc": 1}


def vedic_key_aspects(vtransits, vnatal, limit=2):
    """1–2 strongest sidereal transit→natal aspects, prioritizing Moon/Lagna/Sun.
    Excludes a planet's transit-to-its-own-natal trivial conjunction noise only when
    it isn't a real return. Returns list of factor strings (jargon OK — internal)."""
    cands = []
    for t, tl in vtransits.items():
        for n, nl in vnatal.items():
            asp, orb = closest_aspect(tl, nl, 5.0)
            if not asp:
                continue
            pri = VEDIC_PRIORITY.get(n, 0)
            cands.append((pri, -orb, t, asp, n, orb))
    cands.sort(key=lambda c: (-c[0], c[1]))
    seen, out = set(), []
    for pri, _negorb, t, asp, n, orb in cands:
        key = (t, n)
        if key in seen:
            continue
        seen.add(key)
        label = {"asc": "Lagna", "north_node": "Rahu"}.get(n, cap(n))
        out.append(f"Sidereal {cap(t)} {asp} natal {label} ({round(orb, 1)}°)")
        if len(out) >= limit:
            break
    return out


def vedic_factor_list(today, natal, now_utc):
    """Sidereal (Lahiri) factor list feeding the unified Daily Reading. Returns []
    (never raises) when the Vedic layer can't be computed honestly."""
    try:
        vnatal = sidereal_natal(natal)
        vtransits, _vmissing = vedic_transits_at(now_utc)
    except Exception as e:
        log(f"  vedic computation failed: {e} — vedic factors empty")
        return []
    if "moon" not in vtransits:
        log("  vedic: no sidereal Moon — vedic factors empty")
        return []
    chain, _sub = vedic_subperiod(today)
    factors = [f"Vimshottari {chain} sub-period"]
    if SADE_SATI[0] <= today <= SADE_SATI[1]:
        factors.append(f"Sade Sati ({SADE_SATI_PHASE})")
    factors.append(f"Transit Moon in {nakshatra_of(vtransits['moon'])}")
    factors.extend(vedic_key_aspects(vtransits, vnatal, limit=2))
    return factors


def read_transit_snapshot(today):
    """Opportunistically read today's persisted daily transit snapshot (the iMessage
    generator's archive) to enrich the tropical Codex context. Non-fatal: returns a
    short context string or '' if absent. Source: ~/Documents/Claude/Scheduled/."""
    path = os.path.expanduser(
        f"~/Documents/Claude/Scheduled/daily-transit-snapshot/{today.isoformat()}-transit-snapshot.md")
    try:
        txt = open(path, encoding="utf-8").read()
    except Exception:
        return ""
    grabbed = []
    for line in txt.splitlines():
        s = line.strip()
        if s.startswith("**Hierarchy") or s.startswith("**Guidance"):
            grabbed.append(re.sub(r"\*\*", "", s))
    return " ".join(grabbed)[:600]


def tropical_key_factors(aspects, limit=3):
    """Top tropical transit→natal aspects for today, prioritizing personal/angular
    natal points then tightness. Jargon OK (internal/audit array)."""
    pri = {"sun": 3, "moon": 3, "asc": 3, "mc": 2, "mercury": 1, "venus": 1, "mars": 1}
    ranked = sorted(aspects, key=lambda a: (-pri.get(a["natal"], 0), a["orb"]))
    out, seen = [], set()
    for a in ranked:
        key = (a["transit"], a["natal"])
        if key in seen:
            continue
        seen.add(key)
        label = {"asc": "Ascendant", "mc": "Midheaven",
                 "north_node": "North Node"}.get(a["natal"], cap(a["natal"]))
        out.append(f"{cap(a['transit'])} {a['aspect']} natal {label} ({a['orb']}°)")
        if len(out) >= limit:
            break
    return out


# --- Section 8: Daily Reading (split Tropical + Vedic sub-readings) -------
# v2.2.2 — the single unified reading is split into TWO independent Codex passes,
# one per framework. Each pass sees ONLY its system's MD context (no blending):
#   Tropical: natal_context + deep_research_tropical + 2026-06-07_tropical_dashboard
#   Vedic:    natal_context + deep_research_vedic    + 2026-06-07_vedic_dashboard
# Each emits its OWN state label + body, framed in that tradition's own vocabulary.

def tropical_context_block():
    """Tropical-ONLY narrative context: natal chart + tropical deep-research + the
    purpose-built Tropical dashboard MD. Frames Capricorn-Rising / 12th-House annual
    profection / valuation-cycle / structural-leverage vocabulary. Returns '' if
    nothing could be read (graceful degrade)."""
    natal = read_md(NATAL_MD, cap_chars=4000)
    dash = load_astrology_dashboards().get("tropical_dashboard", "")
    deep = read_md(TROPICAL_MD, cap_chars=6000)
    parts = []
    if natal:
        parts.append("--- NATAL CHART (authoritative, tropical longitudes) ---\n" + natal)
    if dash:
        parts.append("--- TROPICAL DASHBOARD (purpose-built, PRIMARY authority) ---\n" + dash)
    if deep:
        parts.append("--- TROPICAL DEEP RESEARCH 2026-2027 (reference) ---\n" + deep)
    return "\n\n".join(parts)


def vedic_context_block():
    """Vedic-ONLY narrative context: natal chart + Vedic deep-research + the
    purpose-built Vedic dashboard MD. Frames Moon-Venus Mahadasha/antardasha /
    External Manifestation Windows / nakshatra / Sagittarius-Lagna / Sade-Sati
    vocabulary. Returns '' if nothing could be read (graceful degrade)."""
    natal = read_md(NATAL_MD, cap_chars=4000)
    dash = load_astrology_dashboards().get("vedic_dashboard", "")
    deep = read_md(VEDIC_MD, cap_chars=6000)
    parts = []
    if natal:
        parts.append("--- NATAL CHART (authoritative; Vedic = sidereal Lahiri) ---\n" + natal)
    if dash:
        parts.append("--- VEDIC DASHBOARD (purpose-built, PRIMARY authority) ---\n" + dash)
    if deep:
        parts.append("--- VEDIC DEEP RESEARCH 2026 (reference) ---\n" + deep)
    return "\n\n".join(parts)


# --- Traditional (Hellenistic whole-sign) profection layer (v2.2.3) ------
# A THIRD reading framework: same tropical zodiac as the Modern pass, but read
# through traditional time-lord technique (annual + monthly profection) rather
# than modern psychological transit framing. Runs as its own isolated Codex pass
# with its own context window — no blending with Modern or Vedic.

def essential_dignity(planet, sign):
    """Traditional essential dignity of `planet` in `sign`: any of domicile /
    exaltation / detriment / fall (seven classical planets only). Returns a list
    (usually 0-2 labels); empty means peregrine (no essential dignity)."""
    labels = []
    opp = SIGNS[(SIGNS.index(sign) + 6) % 12]
    if TRADITIONAL_RULERS.get(sign) == planet:
        labels.append("domicile")
    if EXALTATION.get(planet) == sign:
        labels.append("exaltation")
    if TRADITIONAL_RULERS.get(opp) == planet:
        labels.append("detriment")
    if EXALTATION.get(planet) == opp:
        labels.append("fall")
    return labels


def traditional_profection(today, natal, aspects):
    """Compute Alfie's current annual + monthly profection (Hellenistic whole-sign)
    and the condition of the lord of the month by classical transit. Returns a list
    of factor strings for the Traditional Codex pass. Pure structure, fully derived
    (PVR: never fabricated) — annual house = age % 12 + 1 from the Ascendant; the
    month rotates one whole sign per 1/12 of the profection year from the birthday."""
    asc_i = SIGNS.index(ASC_SIGN)
    by = today.year if (today.month, today.day) >= BIRTH_MONTH_DAY else today.year - 1
    last_bd = date(by, *BIRTH_MONTH_DAY)
    age = by - 1990
    annual_house = age % 12 + 1
    annual_sign = SIGNS[(asc_i + annual_house - 1) % 12]
    lord_year = TRADITIONAL_RULERS[annual_sign]
    year_len = (date(by + 1, *BIRTH_MONTH_DAY) - last_bd).days
    month_index = min(12, int((today - last_bd).days // (year_len / 12)) + 1)
    month_house = ((annual_house - 1) + (month_index - 1)) % 12 + 1
    month_sign = SIGNS[(asc_i + month_house - 1) % 12]
    lord_month = TRADITIONAL_RULERS[month_sign]

    factors = [
        f"This is a {CHART_SECT} (day) chart, so Jupiter is the in-sect benefic "
        "(its help amplified) and Mars the out-of-sect malefic (its friction amplified)",
        f"Lord of the year: {lord_year} — annual profection to the {ordinal(annual_house)} "
        f"whole-sign house ({annual_sign})",
        f"Lord of the month: {lord_month} — month {month_index} of 12 since the {by} solar "
        f"return; monthly profection to the {ordinal(month_house)} whole-sign house ({month_sign})",
    ]
    lord_lc = lord_month.lower()
    if lord_lc in natal:
        nat_sign = sign_of(natal[lord_lc])
        dign = essential_dignity(lord_month, nat_sign)
        dign_txt = (" — " + " and ".join(dign)) if dign else " (peregrine, no essential dignity)"
        factors.append(f"The lord of the month {lord_month} is natally in {nat_sign}{dign_txt}")
        hits = sorted([a for a in aspects
                       if a["natal"] == lord_lc and a["transit"] in CLASSICAL_TRANSITS],
                      key=lambda a: a["orb"])
        for a in hits[:2]:
            tone = "hard / stressful" if a["aspect"] in HARD else "soft / supportive"
            factors.append(f"{cap(a['transit'])} {a['aspect']} the lord of the month "
                           f"({a['orb']}° — {tone})")
        if not hits:
            factors.append(f"No close classical transit to {lord_month} right now — the lord "
                           "of the month is quiet by transit")
    return factors


def traditional_context_block():
    """Traditional/Hellenistic-ONLY narrative context: natal chart + the Tropical
    dashboard's Annual Profection section + an inline whole-sign methodology note.
    Frames lord-of-year / lord-of-month / time-lord / essential-dignity vocabulary on
    the tropical zodiac. Returns '' if nothing readable (graceful degrade)."""
    natal = read_md(NATAL_MD, cap_chars=4000)
    dash = load_astrology_dashboards().get("tropical_dashboard", "")
    methodology = (
        "--- HELLENISTIC WHOLE-SIGN METHODOLOGY (your framework) ---\n"
        "Read with traditional whole-sign houses and the SEVEN CLASSICAL PLANETS ONLY "
        "(Sun, Moon, Mercury, Venus, Mars, Jupiter, Saturn). The Ascendant sign is the 1st "
        "whole-sign house. Annual profection: profected house = (age mod 12) + 1, counted from "
        "the Ascendant as the 1st; that sign's domicile ruler is the LORD OF THE YEAR (the "
        "year's time-lord). Monthly profection rotates one whole sign per month from the year's "
        "profected house, starting on the solar return (birthday, Aug 30); that sign's ruler is "
        "the LORD OF THE MONTH. Judge a time-lord by its natal essential dignity (domicile / "
        "exaltation / detriment / fall) and by current transits from the classical planets only "
        "— never from Uranus, Neptune, or Pluto, and never with modern psychological language."
    )
    parts = [methodology]
    if natal:
        parts.append("--- NATAL CHART (tropical longitudes; Ascendant 8° Capricorn, day chart) ---\n"
                     + natal)
    if dash:
        parts.append("--- TROPICAL DASHBOARD — 2026 ANNUAL PROFECTION (12th-house Sagittarius year, "
                     "Jupiter-ruled; a foundation/preparation year, not a coronation) ---\n" + dash)
    return "\n\n".join(parts)


# --- BaZi (Eastern / Chinese Four Pillars) layer (v2.4) ------------------
# A FOURTH reading framework, fully independent of the three Western/Vedic passes.
# Natal pillars are CANONICAL (verified by sexagenary-day + solar-term calc against
# 1990-08-30 16:22 CDT; confirmed by Alfie 2026-06-11, superseding the old Dog chart):
#   Year 庚午 Geng-Wu (Horse) · Month 甲申 Jia-Shen (Monkey) ·
#   Day 丁卯 Ding-Mao (RABBIT, Day Master Ding Fire) · Hour 戊申 Wu-Shen (Monkey).
# Sources: 02_Astrology/Alfie/natal_context.md (canonical YAML) +
#          02_Astrology/Alfie/bazi_verification_2026_activation_report.md (timing layer).
BAZI_STEMS = ["Jia", "Yi", "Bing", "Ding", "Wu", "Ji", "Geng", "Xin", "Ren", "Gui"]
BAZI_STEM_ELEM = {  # stem -> (element, Ten-God role relative to a DING FIRE day master)
    "Jia": ("Yang Wood", "Resource"), "Yi": ("Yin Wood", "Resource"),
    "Bing": ("Yang Fire", "Companion (Rob Wealth)"), "Ding": ("Yin Fire", "Companion (peer)"),
    "Wu": ("Yang Earth", "Output"), "Ji": ("Yin Earth", "Output"),
    "Geng": ("Yang Metal", "Wealth"), "Xin": ("Yin Metal", "Wealth"),
    "Ren": ("Yang Water", "Power/Officer"), "Gui": ("Yin Water", "Power/Officer"),
}
BAZI_BRANCHES = ["Zi", "Chou", "Yin", "Mao", "Chen", "Si",
                 "Wu", "Wei", "Shen", "You", "Xu", "Hai"]
BAZI_ANIMALS = ["Rat", "Ox", "Tiger", "Rabbit", "Dragon", "Snake",
                "Horse", "Goat", "Monkey", "Rooster", "Dog", "Pig"]
# Sectional solar terms (jié) that BEGIN each BaZi month, indexed from the Yin (Tiger)
# month at ecliptic longitude 315°, then every +30°.
BAZI_JIE = ["Li Chun", "Jing Zhe", "Qing Ming", "Li Xia", "Mang Zhong", "Xiao Shu",
            "Li Qiu", "Bai Lu", "Han Lu", "Li Dong", "Da Xue", "Xiao Han"]
# Five-Tigers: year stem -> stem INDEX of the FIRST (Yin) month.
#   Jia/Ji→Bing(2) · Yi/Geng→Wu(4) · Bing/Xin→Geng(6) · Ding/Ren→Ren(8) · Wu/Gui→Jia(0)
_BAZI_YIN_STEM = {"Jia": 2, "Ji": 2, "Yi": 4, "Geng": 4, "Bing": 6, "Xin": 6,
                  "Ding": 8, "Ren": 8, "Wu": 0, "Gui": 0}

# Canonical natal facts (do NOT recompute — verified + Alfie-confirmed).
BAZI_NATAL = {
    "dayMaster": "Ding Fire (丁火) — Yin Fire",
    "coreAnimal": "Rabbit",
    "coreAnimalBranch": "Mao (卯)",
    "pillars": {"year": "Geng-Wu", "month": "Jia-Shen", "day": "Ding-Mao", "hour": "Wu-Shen"},
    "animalStack": ["Horse", "Monkey", "Rabbit", "Monkey"],
    "elements": {"Wood": 2, "Fire": 2, "Earth": 4, "Metal": 3, "Water": 2},
    "daYun": "Wu-Zi (戊子)",          # current decade luck pillar (Yang-year male, forward)
    "benMingYear": 2026,             # classical: birth-year branch (Horse) repeats in 2026 Bing-Wu
}


def _greg_jdn(y, m, d):
    """Julian Day Number for a Gregorian civil date (noon-agnostic, integer)."""
    a = (14 - m) // 12
    yy = y + 4800 - a
    mm = m + 12 * a - 3
    return d + (153 * mm + 2) // 5 + 365 * yy + yy // 4 - yy // 100 + yy // 400 - 32045


def bazi_day_pillar(today):
    """Sexagenary DAY pillar for a civil date. Calibrated so 2000-01-07 = Jia-Zi
    (JDN 2451551). Returns (stem, branch, animal)."""
    j = _greg_jdn(today.year, today.month, today.day)
    return BAZI_STEMS[(j + 9) % 10], BAZI_BRANCHES[(j + 1) % 12], BAZI_ANIMALS[(j + 1) % 12]


def bazi_year_pillar(today):
    """Solar BaZi YEAR pillar. The year rolls at Li Chun (~Feb 4), not Jan 1."""
    y = today.year if (today.month, today.day) >= (2, 4) else today.year - 1
    i = (y - 4) % 10
    b = (y - 4) % 12
    return BAZI_STEMS[i], BAZI_BRANCHES[b], BAZI_ANIMALS[b]


def bazi_month_pillar(today, sun_lon, year_stem):
    """Solar BaZi MONTH pillar from the Sun's tropical longitude. Month branch advances
    one sign per 30° of solar longitude from the Yin (Tiger) month at 315°; the stem
    follows the Five-Tigers rule off the year stem. Returns (stem, branch, animal, jie)."""
    idx = int(((sun_lon - 315) % 360) // 30)          # 0 = Yin month (Li Chun)
    branch_i = (2 + idx) % 12                          # Yin = branch index 2
    stem_i = (_BAZI_YIN_STEM[year_stem] + idx) % 10
    return (BAZI_STEMS[stem_i], BAZI_BRANCHES[branch_i],
            BAZI_ANIMALS[branch_i], BAZI_JIE[idx])


def _bazi_sun_lon(now_utc):
    """Sun's tropical longitude now, or None on ephemeris failure (graceful degrade)."""
    try:
        return lon_of(jd_now(now_utc), swe.SUN)
    except Exception as e:
        log(f"  bazi: Sun longitude failed ({e}) — month pillar degraded")
        return None


def bazi_core(today, now_utc):
    """Structured, pure-computed BaZi facts for the dashboard card's Core Animal +
    Daily Tactical layers (no Codex). Live year/month/day pillars + the natal animal
    stack + the user mnemonic overlay (Rooster 'payoff' is a mnemonic, NOT a pillar)."""
    ys, yb, ya = bazi_year_pillar(today)
    ds, db, da = bazi_day_pillar(today)
    sun_lon = _bazi_sun_lon(now_utc)
    if sun_lon is not None:
        ms, mb, ma, jie = bazi_month_pillar(today, sun_lon, ys)
        month = {"pillar": f"{ms}-{mb}", "animal": ma, "solarTerm": jie}
    else:
        month = None
    # Daily tactical slots — the user's Horse/Monkey/Rabbit/Rooster mnemonic overlay.
    slots = [
        {"slot": "Drive", "animal": "Horse",
         "note": "Year branch repeats in 2026 — drive and visibility run hot"},
        {"slot": "Pressure", "animal": "Monkey",
         "note": "Natal month AND hour branch — structural pressure is real"},
        {"slot": "Self / Illuminate", "animal": "Rabbit",
         "note": "Your true core branch — finesse, curation, clean expression over force"},
        {"slot": "Payoff", "animal": "Rooster",
         "note": "Mnemonic overlay only — not a natal pillar (literal hour branch is Monkey)"},
    ]
    return {
        "dayMaster": BAZI_NATAL["dayMaster"],
        "coreAnimal": BAZI_NATAL["coreAnimal"],
        "coreAnimalBranch": BAZI_NATAL["coreAnimalBranch"],
        "animalStack": BAZI_NATAL["animalStack"],
        "elements": BAZI_NATAL["elements"],
        "daYun": BAZI_NATAL["daYun"],
        "benMingYear": BAZI_NATAL["benMingYear"],
        "currentYear": {"pillar": f"{ys}-{yb}", "animal": ya},
        "currentMonth": month,
        "currentDay": {"pillar": f"{ds}-{db}", "animal": da},
        "tacticalSlots": slots,
    }


def _bazi_stem_role(stem):
    elem, role = BAZI_STEM_ELEM.get(stem, ("", ""))
    return f"{elem} ({role} for Ding Fire)"


def bazi_factors(today, now_utc):
    """Live DAILY factors for the BaZi Codex pass — current year/month/day pillars read
    as Ten-Gods relative to the Ding Fire day master. PVR: fully computed, never faked."""
    ys, yb, ya = bazi_year_pillar(today)
    ds, db, da = bazi_day_pillar(today)
    facts = [
        f"Day Master Ding Fire (Yin Fire); core branch Rabbit (Mao). Earth-heavy chart "
        f"(Wood2/Fire2/Earth4/Metal3/Water2) — Output is the dominant element.",
        f"Current Da Yun (10-year luck pillar): Wu-Zi — Yang Earth Output over Rat Water "
        f"Power/Officer.",
        f"BaZi year {ys}-{yb} ({ya}): {ys} stem is {_bazi_stem_role(ys)}; 2026 repeats your "
        f"natal Horse year branch (Ben Ming year) — peer-fire amplification, visibility, "
        f"and heat/burnout risk.",
        f"Today's day pillar {ds}-{db} ({da}): {ds} stem is {_bazi_stem_role(ds)}.",
    ]
    sun_lon = _bazi_sun_lon(now_utc)
    if sun_lon is not None:
        ms, mb, ma, jie = bazi_month_pillar(today, sun_lon, ys)
        facts.insert(3, f"Current BaZi month {ms}-{mb} ({ma}), solar term {jie}: {ms} stem is "
                        f"{_bazi_stem_role(ms)}.")
    return facts


def bazi_monthly_factors(today, now_utc):
    """Live MONTHLY factors for the BaZi monthly Codex pass — the current solar-term month,
    the next jié handoff date, and the year's stacking window. PVR: derived from ephemeris
    + the verification report's fixed solar-term calendar."""
    ys, yb, ya = bazi_year_pillar(today)
    sun_lon = _bazi_sun_lon(now_utc)
    if sun_lon is None:
        return [f"BaZi year {ys}-{yb} ({ya}) — Ben Ming Horse year, peer-fire and visibility high."]
    ms, mb, ma, jie = bazi_month_pillar(today, sun_lon, ys)
    facts = [
        f"Current BaZi month {ms}-{mb} ({ma}), opened by solar term {jie}; {ms} stem is "
        f"{_bazi_stem_role(ms)} and {ma} branch sets the month's element field.",
    ]
    # Forward-search the next 30°-boundary (next jié / month change).
    try:
        jd = jd_now(now_utc)
        cur_idx = int(((sun_lon - 315) % 360) // 30)
        for d in range(1, 41):
            nl = lon_of(jd + d, swe.SUN)
            if int(((nl - 315) % 360) // 30) != cur_idx:
                nxt = (cur_idx + 1) % 12
                nms, nmb, nma, njie = bazi_month_pillar(today + timedelta(days=d), nl, ys)
                facts.append(f"The month rolls to {nms}-{nmb} ({nma}) at solar term {njie} around "
                             f"{(today + timedelta(days=d)).isoformat()} — the element field shifts then.")
                break
    except Exception as e:
        log(f"  bazi monthly: next-term search failed ({e}) — skipping handoff factor")
    facts.append("2026's tightest stacking window is Jul 7 – Sep 7 (Yi-Wei and Bing-Shen months, "
                 "holding the ~Jul 12 Jupiter return) — the year's center of gravity for the visible move.")
    return facts


def bazi_context_block():
    """BaZi-ONLY narrative context: canonical natal pillars + Five-Element / Ten-Gods
    framing for a Ding Fire day master + the 2026 activation layer. Pulls the canonical
    natal YAML and the verification report; never blends Western/Vedic vocabulary."""
    natal = read_md(NATAL_MD, cap_chars=3500)
    verify = read_md(os.path.join(ASTRO, "bazi_verification_2026_activation_report.md"),
                     cap_chars=3500)
    methodology = (
        "--- BAZI (FOUR PILLARS) METHODOLOGY (your framework) ---\n"
        "Day Master = Ding Fire (Yin Fire). Read everything as a Ten-Gods relationship to "
        "Ding: Wood = Resource (fuel), Fire = Companion/peer (Bing = Rob Wealth), Earth = "
        "Output (what the fire produces), Metal = Wealth, Water = Power/Officer. Natal pillars "
        "(CANONICAL — do not recompute): Year 庚午 Geng-Wu (Horse), Month 甲申 Jia-Shen (Monkey), "
        "Day 丁卯 Ding-Mao (RABBIT — the true core animal), Hour 戊申 Wu-Shen (Monkey). Literal "
        "natal animal stack: Horse / Monkey / Rabbit / Monkey. Element inventory Wood2 / Fire2 / "
        "Earth4 / Metal3 / Water2 — Earth (Output) dominant, nothing absent. Current Da Yun "
        "(10-year luck pillar) = 戊子 Wu-Zi. 2026 is the Ben Ming year (natal Horse year branch "
        "repeats in Bing-Wu). The Horse/Monkey/Rabbit/Rooster 'drive/pressure/self/payoff' "
        "labels are a USER MNEMONIC overlay — 'Rooster payoff' is NOT a natal pillar."
    )
    parts = [methodology]
    if natal:
        parts.append("--- NATAL CONTEXT (canonical; use only the bazi: block) ---\n" + natal)
    if verify:
        parts.append("--- 2026 BAZI ACTIVATION + MONTHLY TIMING (verification report) ---\n" + verify)
    return "\n\n".join(parts)


# Per-system framing vocabulary + the cross-contamination guardrail (each system
# names ONLY its own tradition's terms, never the other's).
_READING_SYSTEMS = {
    "tropical": {
        "name": "TROPICAL (Western)",
        "use": ("Western/tropical structural vocabulary naturally — Capricorn Rising, "
                "the 12th-House annual profection (a foundation/preparation year), the "
                "'valuation cycle you work, not a predetermined one' framing, structural leverage, the "
                "2nd-House North Node self-valuation arc, and natal aspects."),
        "forbid": ("Mahadasha, antardasha, dasha, Vimshottari, nakshatra, pada, Lagna, "
                   "Sade Sati, Panoti, or 'External Manifestation Windows'"),
    },
    "traditional": {
        "name": "TROPICAL · TRADITIONAL (Hellenistic)",
        "use": ("traditional / Hellenistic whole-sign vocabulary naturally — the lord of the "
                "year and the lord of the month (time-lords), the profected house, essential "
                "dignity (domicile / exaltation / detriment / fall), sect (this is a day chart), "
                "and the seven classical planets. NAME the month's profected house and its lord, "
                "say whether that lord is well-placed or under stress by current transit, and "
                "translate to plain English — what to lean into and what to watch THIS month."),
        "forbid": ("Pluto, Neptune, Uranus, 'structural leverage', 'self-valuation', modern "
                   "psychological framing, Mahadasha, antardasha, dasha, Vimshottari, nakshatra, "
                   "pada, Lagna, Sade Sati, or Panoti"),
    },
    "vedic": {
        "name": "VEDIC (sidereal)",
        "use": ("Vedic vocabulary naturally — the Moon Mahadasha with the Venus "
                "antardasha (relationship/value-positive), the External Manifestation "
                "Windows (strongest Aug 12 – Sep 5 2026), the transit Moon's nakshatra, "
                "the Sagittarius Lagna, Sade Sati (Small Panoti), and the Vimshottari "
                "sub-period chain."),
        "forbid": ("annual profection, Capricorn Rising, the 'valuation cycle' phrase, "
                   "tropical sign placements, or '12th-House profection'"),
    },
    "bazi": {
        "name": "BAZI (Eastern · Four Pillars)",
        "use": ("BaZi / Chinese Four Pillars vocabulary naturally — the Ding Fire day master, "
                "the Five Elements and their Ten-Gods roles (Resource / Companion / Output / "
                "Wealth / Power), the core animal Rabbit, the current solar-term month and its "
                "stem-branch, the 戊子 Wu-Zi Da Yun (10-year luck pillar), and the 2026 Ben Ming "
                "(Horse-year) peer-fire field. Name today's element field and what it favors, "
                "then the standing warning: move visibly but do not turn competition into "
                "compulsion or scatter into too many parallel fires (heat/burnout)."),
        "forbid": ("Mahadasha, antardasha, dasha, Vimshottari, nakshatra, pada, Lagna, Sade "
                   "Sati, Panoti, annual profection, lord of the year/month, Capricorn Rising, "
                   "houses, Ascendant, Pluto, Neptune, Uranus, or any tropical/sidereal zodiac sign"),
    },
}


# Canonical translation style guide — mirrors
# 02_Astrology/Alfie/translation_style_guide.md (authored 2026-06-14). Injected into
# every prose prompt so generated readings translate astrology into decision-oriented
# operational language rather than describing it. Keep in sync with the vault doc.
STYLE_GUIDE_BLOCK = (
    "=== TRANSLATION STYLE GUIDE (mandatory) ===\n"
    "Translate astrology into decision-oriented operational language. Do NOT describe "
    "astrology — translate it into what a high-agency, systems-oriented reader should do.\n"
    "- LEAD WITH HIERARCHY. Do not weight factors equally. Rank: structural/long-term first, "
    "then outer-planet activations, then personal transit spikes, then emotional tone. Name "
    "the dominant influence; demote the loud-but-transient one.\n"
    "- TRANSLATE SYMBOLISM INTO REALITY. Not 'Chiron is activated' but 'areas where competence "
    "and old sensitivity overlap become more visible.' Not 'Pluto transforms' but 'long-term "
    "consequences become more apparent.'\n"
    "- NO MYSTICAL LANGUAGE. Banned words: destiny, karma, soul, soul lesson, cosmic, universe, "
    "divine, divine timing, wounds activated, manifest, vibration, alignment(mystical sense). "
    "Replace with: direction, pattern, consequence, restructuring, opportunity, pressure.\n"
    "- CONVERT EMOTION INTO DECISION POINTS. Not 'you may feel frustrated' but 'frustration is "
    "best discharged through action, not discussion.' Not 'tensions arise' but 'if friction "
    "appears around fairness or value, do not reopen old disputes.'\n"
    "- ANSWER FOUR QUESTIONS: what matters, what doesn't, what to build, what to ignore.\n"
    "- ANNOUNCE STANDING THEMES ONCE, ON THEIR ACTIVATION DAY. Assume Alfredo already knows the "
    "standing background — lord of the year, the current dasha/antardasha, the current Da Yun, "
    "active solar arcs, Sade Sati. Do NOT restate them daily; he installed them himself. Mention "
    "a long-running theme only on the day it begins or shifts (see the activation note below). On "
    "an ordinary day, lead with the actionable stack — 1-3 day spikes, the trap, the best use — "
    "not with the standing frame. What stays daily: tone spikes, same-day observations, the trap "
    "and best use from THAT day's stack, and exactitude/station days.\n"
    "- INCLUDE EXACTLY ONE IMAGE-RICH SENTENCE. One — no more — evocative, decision-grounded "
    "sentence per reading: a metaphor or texture that helps pattern-recognition land, woven into "
    "the lead/bottom-line OR the closing line (never a separate aside). It must ground in "
    "observable mechanics and still pass every rule above. Good: 'Mars-Venus is friction looking "
    "for a build, not a fight'; 'Saturn is the quiet edit, not the loud cut.' Banned: fortune-"
    "cookie, cosmos, or therapy-voice phrasing ('the cosmos invites you', 'sacred space opens'). "
    "The rest of the reading stays clinical.\n"
    "- TONE: direct, clinical, high-signal. No therapy language, no motivational language, no "
    "prediction inflation, no emotional hand-holding. Pattern recognition and decision support, "
    "not inspiration.\n"
    "=== END STYLE GUIDE ==="
)


# --- Principle #6: announce standing themes ONCE, on their activation day ----
def _profection_month_index(d):
    """(month_index 1..12, year-start year, last birthday, month length in days) for date d."""
    by = d.year if (d.month, d.day) >= BIRTH_MONTH_DAY else d.year - 1
    last_bd = date(by, *BIRTH_MONTH_DAY)
    year_len = (date(by + 1, *BIRTH_MONTH_DAY) - last_bd).days
    month_len = year_len / 12.0
    idx = min(12, int((d - last_bd).days // month_len) + 1)
    return idx, by, last_bd, month_len


def _monthly_profection_rotation(today):
    """Activation label if today is a monthly-profection rotation (the lord of the month
    hands off), else None. The annual flip (birthday) is handled separately, so the
    birthday itself is skipped here. Mirrors the house math in traditional_monthly_factors."""
    if (today.month, today.day) == BIRTH_MONTH_DAY:
        return None
    idx_today, by, _, _ = _profection_month_index(today)
    idx_yest, _, _, _ = _profection_month_index(today - timedelta(days=1))
    if idx_today == idx_yest:
        return None
    asc_i = SIGNS.index(ASC_SIGN)
    annual_house = (by - 1990) % 12 + 1
    house = ((annual_house - 1) + (idx_today - 1)) % 12 + 1
    sign = SIGNS[(asc_i + house - 1) % 12]
    lord = TRADITIONAL_RULERS[sign]
    return (f"The monthly profection rotates today to the {ordinal(house)} whole-sign house "
            f"({sign}, lord {lord}) — the month's time-lord hands off today.")


def _slow_ingress_today(now_utc):
    """Tropical sign ingresses for slow bodies (Jupiter..Pluto) crossing a sign boundary in
    the last 24h. Moon and fast personal planets are excluded — those are daily tone, not
    standing themes. Pure ephemeris (PVR)."""
    out = []
    jd_t, jd_y = jd_now(now_utc), jd_now(now_utc - timedelta(days=1))
    slow = {"jupiter": swe.JUPITER, "saturn": swe.SATURN, "uranus": swe.URANUS,
            "neptune": swe.NEPTUNE, "pluto": swe.PLUTO}
    for name, b in slow.items():
        try:
            if sign_of(lon_of(jd_t, b)) != sign_of(lon_of(jd_y, b)):
                out.append(f"{name.title()} ingresses into {sign_of(lon_of(jd_t, b))} today — a "
                           "multi-year sign change. Name it today, then drop it from daily prose.")
        except Exception:
            continue
    return out


def standing_theme_activations(today, now_utc):
    """Per-system list of standing/long-running themes that BEGIN or SHIFT exactly today
    (Principle #6 of the translation style guide). These get announced ONCE, on the
    activation day, then drop out of daily prose. An EMPTY list for a system means: assume
    its standing background is known, do not restate it. Every entry is derived from the
    dated facts above or live ephemeris — never fabricated (PVR)."""
    acts = {"tropical": [], "traditional": [], "vedic": [], "bazi": []}
    # Annual profection / lord-of-year flip — birthday (tropical + traditional time-lord).
    if today == PROFECTION_FLIP:
        acts["tropical"].append(
            f"The annual profection turns over today: the 12th-house {LORD_BEFORE_FLIP.title()} "
            f"year ends and the 1st-house {LORD_AFTER_FLIP.title()} year begins.")
        acts["traditional"].append(
            f"The lord of the year changes today to {LORD_AFTER_FLIP.title()} — the profection "
            f"rotates to the 1st whole-sign house ({ASC_SIGN}). The annual time-lord hands off today.")
    # Traditional monthly profection rotation — lord of the month hands off.
    rot = _monthly_profection_rotation(today)
    if rot:
        acts["traditional"].append(rot)
    # BaZi 10-year Da Yun shift.
    if today == BAZI_SHIFT:
        acts["bazi"].append(
            "The 10-year Da Yun luck pillar shifts today (into the Output-payoff phase) — a "
            "once-a-decade handoff. Name it today, then drop it.")
    # Vedic Vimshottari sub-period (pratyantardasha) starts.
    for w in VEDIC_SUBPERIODS:
        if today == w["start"]:
            acts["vedic"].append(
                f"A new Vimshottari sub-period begins today: {VEDIC_MAHADASHA}–{VEDIC_ANTARDASHA}–"
                f"{w['sub']} (runs through {w['end'].isoformat()}).")
    # Vedic antardasha boundary.
    if today == VENUS_ANTARDASHA[1]:
        acts["vedic"].append(f"The {VEDIC_ANTARDASHA} antardasha ends today; the next one begins.")
    # Sade Sati boundaries.
    if today == SADE_SATI[0]:
        acts["vedic"].append(f"Sade Sati ({SADE_SATI_PHASE}) begins today.")
    if today == SADE_SATI[1]:
        acts["vedic"].append(f"Sade Sati ({SADE_SATI_PHASE}) ends today.")
    # Solar-arc directions perfecting (tropical structural).
    for d, desc in SOLAR_ARC_EXACTS:
        if today == d:
            acts["tropical"].append(desc)
    # Slow/outer-planet tropical sign ingress.
    try:
        acts["tropical"].extend(_slow_ingress_today(now_utc))
    except Exception as e:
        log(f"  ingress activation check failed ({e}) — skipping")
    return acts


def _activation_directive(system, activations):
    """The per-system activation note injected into a daily reading prompt (Principle #6)."""
    items = (activations or {}).get(system, [])
    if items:
        return ("ACTIVATION DAY NOTE — a standing/long-running theme BEGINS or SHIFTS today. LEAD "
                "the reading with it; it is genuine news today. State it once, plainly, then move to "
                "today's stack. Today's activation(s): " + " ".join(items))
    return ("ACTIVATION DAY NOTE — no standing-theme activation today. Do NOT restate the standing "
            "background (lord of year, current dasha, Da Yun, active solar arcs, Sade Sati); assume "
            "he knows it. Lead with today's actionable stack: spikes, trap, best use.")


def codex_reading(system, forecast, factors, moon_desc, context_block, mood, snap="", activation=""):
    """ONE framework's daily reading via ~/bin/llm --model codex (Cowork-safe). `system`
    is 'tropical' or 'vedic'; the prompt sees ONLY that system's context_block, speaks
    in that tradition's vocabulary, and is forbidden the other tradition's terms (no
    cross-contamination). Emits the framework's OWN state label + a ~3-4 line body.
    Returns (state_label, body) or (None, None) on any failure (PVR: that side -> null)."""
    cfg = _READING_SYSTEMS[system]
    llm = os.path.expanduser("~/bin/llm")
    if not os.path.exists(llm):
        log(f"  ~/bin/llm not found — {system}Reading null")
        return None, None
    facts = [f for f in list(factors) if f]
    if moon_desc:
        facts.append(moon_desc)
    if not facts:
        log(f"  no {system} factors — {system}Reading null")
        return None, None
    background = (
        "This is a preparation-and-pipeline phase: quiet leverage, cleanup, building "
        "relationships and documents, opening doors that convert into weight-bearing "
        "commitments after late August 2026 — open doors now, sign and formalize later. "
        "Real background pressure and volatility on home and foundations ask for fewer, "
        "better moves."
    )
    if snap:
        background += " Today's read from the morning snapshot: " + snap
    context_section = ("\n\n=== " + cfg["name"] + " CONTEXT (your ONLY source) ===\n"
                       + context_block + "\n=== END CONTEXT ===") if context_block else ""
    prompt = (
        f"You are writing the {cfg['name']} sub-reading for a personal astrology dashboard. "
        f"This card has three clearly-labeled sub-sections; you write ONLY the {cfg['name']} one. "
        f"USE {cfg['use']} "
        f"Speak ONLY in the {cfg['name']} framework — do NOT use the OTHER tradition's terms "
        f"(no {cfg['forbid']}). "
        "Second person, EXACTLY 3-4 short declarative sentences — 45-60 words TOTAL, a hard cap. "
        "Lead with the bottom line, then the why. Blunt, plain, direct: no hedging, no stacked "
        "qualifiers, no run-on sentences, no semicolons. Be honest about BOTH the supports and "
        "the tensions. No event predictions, no fortune-telling, no hype, no fluff. "
        "Exactly ONE of those sentences must carry an image — an evocative, decision-grounded "
        "metaphor in the bottom line or the closing line (e.g. 'Saturn is the quiet edit, not the "
        "loud cut'); the rest stay clinical. No fortune-cookie or therapy voice.\n\n"
        + STYLE_GUIDE_BLOCK + "\n\n"
        + (activation + "\n\n" if activation else "")
        + f"Headline weather mode: {forecast}.\n"
        "Live factors to weave in (interpret in your framework, do not just list): "
        + "; ".join(facts) + ".\n"
        f"Mood: {mood}\n"
        f"Background: {background}"
        + context_section + "\n\n"
        "Output EXACTLY this shape and nothing else:\n"
        "STATE: <one or two word state label for THIS framework today, e.g. Expansion, "
        "Consolidation, Pivot, Preparation>\n"
        "BODY: <the second-person passage>"
    )
    try:
        out = subprocess.run([llm, "--lane", "reasoning", "--model", "codex", prompt],
                             capture_output=True, text=True, timeout=180, cwd=DASH)
        if out.returncode != 0:
            log(f"  codex {system} reading exited {out.returncode}: {out.stderr.strip()[:200]}")
            return None, None
    except Exception as e:
        log(f"  codex {system} reading failed (non-fatal): {e}")
        return None, None
    raw = out.stdout
    sm = re.search(r"(?im)^\s*STATE:\s*(.+?)\s*$", raw)
    bm = re.search(r"(?is)BODY:\s*(.+)$", raw)
    state_label = sm.group(1).strip().strip(".").strip() if sm else None
    body = re.sub(r"\s+", " ", bm.group(1)).strip() if bm else re.sub(r"\s+", " ", raw).strip()
    if not body:
        log(f"  codex {system} reading produced no body — null")
        return None, None
    if not state_label:
        state_label = forecast.title()
    return state_label, body


# --- v2.3: Monthly readings (this-month view per system) -----------------
# Each system gets a SECOND Codex pass framed in its NATIVE month concept:
#   Modern:      the Sun's current ~30-day sign transit (solar month).
#   Traditional: the Hellenistic profection month (lord of the month + condition).
#   Vedic:       the Vimshottari sub-period progression + transit-Moon nakshatra cycle.
# Same per-system vocabulary isolation as the dailies (no cross-contamination).
# All factors are pure-derived (PVR: never fabricated).
_MONTHLY_FRAME = {
    "tropical": "the Sun's current ~30-day sign transit (the modern solar month)",
    "traditional": ("the Hellenistic profection month — the lord of the month and its "
                    "condition over the next ~30 days"),
    "vedic": ("the Vimshottari sub-period progression and the transit Moon's nakshatra "
              "cycle across the sidereal lunar month"),
    "bazi": ("the current BaZi solar-term month (its stem-branch and element field) and "
             "the next jié handoff over the ~30 days ahead"),
}


def tropical_monthly_factors(today, now_utc):
    """Modern monthly frame: the Sun's current ~30-day sign transit. Pure ephemeris —
    current Sun sign, degrees elapsed, and the next ingress date (forward-searched up
    to 40 days). PVR: fully derived, never fabricated."""
    jd = jd_now(now_utc)
    try:
        sun_lon = lon_of(jd, swe.SUN)
    except Exception as e:
        log(f"  tropical monthly: Sun longitude failed ({e}) — no factors")
        return []
    sun_sign = sign_of(sun_lon)
    deg_in = round(sun_lon % 30, 1)
    factors = [f"The Sun is transiting {sun_sign}, {deg_in}° in — the ~30-day solar month"]
    next_sign, ingress_date = None, None
    for d in range(1, 41):
        if sign_of(lon_of(jd + d, swe.SUN)) != sun_sign:
            next_sign = sign_of(lon_of(jd + d, swe.SUN))
            ingress_date = today + timedelta(days=d)
            break
    if ingress_date:
        factors.append(f"The Sun ingresses {next_sign} around {ingress_date.isoformat()}, "
                       "shifting the month's tone partway through")
    else:
        factors.append(f"The Sun stays in {sun_sign} for the whole month ahead")
    return factors


def traditional_monthly_factors(today, natal, aspects):
    """Traditional monthly frame: the profection month. Reuses traditional_profection
    (which already covers the lord of the month for the next ~30 days) and appends the
    next monthly-profection rotation date + the incoming lord, so the month body can
    name when the time-lord hands off. PVR: derived from the profection math only."""
    factors = list(traditional_profection(today, natal, aspects))
    asc_i = SIGNS.index(ASC_SIGN)
    by = today.year if (today.month, today.day) >= BIRTH_MONTH_DAY else today.year - 1
    last_bd = date(by, *BIRTH_MONTH_DAY)
    year_len = (date(by + 1, *BIRTH_MONTH_DAY) - last_bd).days
    month_len = year_len / 12
    month_index = min(12, int((today - last_bd).days // month_len) + 1)
    annual_house = (by - 1990) % 12 + 1
    if month_index < 12:
        next_rot = last_bd + timedelta(days=int(round(month_index * month_len)))
        next_house = ((annual_house - 1) + month_index) % 12 + 1
        next_sign = SIGNS[(asc_i + next_house - 1) % 12]
        next_lord = TRADITIONAL_RULERS[next_sign]
        factors.append(f"The monthly profection rotates to the {ordinal(next_house)} whole-sign "
                       f"house ({next_sign}, lord {next_lord}) around {next_rot.isoformat()} — the "
                       "month's time-lord hands off then")
    return factors


def vedic_monthly_factors(today, now_utc):
    """Vedic monthly frame: Vimshottari sub-period progression + the transit-Moon
    nakshatra cycle for the month. Flags any sub-period (pratyantardasha) handoff in
    the next 30 days, the Venus antardasha tail, the current transit-Moon nakshatra
    (cycling all 27 over the ~27-day sidereal lunar month), and active Sade Sati.
    PVR: every factor is looked up or computed, never fabricated."""
    chain, _ = vedic_subperiod(today)
    factors = [f"Current Vimshottari sub-period chain: {chain}"]
    horizon = today + timedelta(days=30)
    for w in VEDIC_SUBPERIODS:
        if today < w["start"] <= horizon:
            factors.append(f"The pratyantardasha shifts to {VEDIC_MAHADASHA}–{VEDIC_ANTARDASHA}–"
                           f"{w['sub']} around {w['start'].isoformat()} — a sub-period handoff "
                           "inside this month")
    if today <= VENUS_ANTARDASHA[1] <= horizon:
        factors.append(f"The {VEDIC_ANTARDASHA} antardasha runs out around "
                       f"{VENUS_ANTARDASHA[1].isoformat()}")
    try:
        vt, _ = vedic_transits_at(now_utc)
        if "moon" in vt:
            factors.append(f"The transit Moon is in {nakshatra_of(vt['moon'])} now and will cycle "
                           "through all 27 nakshatras over the ~27-day sidereal lunar month")
    except Exception as e:
        log(f"  vedic monthly: transit Moon nakshatra failed ({e}) — skipping that factor")
    if SADE_SATI[0] <= today <= SADE_SATI[1]:
        factors.append(f"Sade Sati ({SADE_SATI_PHASE}) stays active through "
                       f"{SADE_SATI[1].isoformat()}")
    return factors


def codex_monthly_reading(system, forecast, factors, context_block, mood):
    """ONE framework's MONTHLY reading (this month, next ~30 days) via ~/bin/llm
    --model codex. Same per-system vocabulary isolation as codex_reading, but frames the
    month through that system's NATIVE month concept (see _MONTHLY_FRAME) and runs a bit
    longer (5-6 lines) so it can name specific dates inside the month. Sees ONLY its
    system's context_block — no blending. Returns (state, body) or (None, None) on any
    failure (PVR: that monthly side -> null; the daily for that system is unaffected)."""
    cfg = _READING_SYSTEMS[system]
    llm = os.path.expanduser("~/bin/llm")
    if not os.path.exists(llm):
        log(f"  ~/bin/llm not found — {system}Monthly null")
        return None, None
    facts = [f for f in list(factors) if f]
    if not facts:
        log(f"  no {system} monthly factors — {system}Monthly null")
        return None, None
    background = (
        "Zoom out from today to the whole month ahead. This is a preparation-and-pipeline "
        "phase: quiet leverage and building now, with weight-bearing commitments landing after "
        "late August 2026 — name what this month sets up rather than any single day."
    )
    context_section = ("\n\n=== " + cfg["name"] + " CONTEXT (your ONLY source) ===\n"
                       + context_block + "\n=== END CONTEXT ===") if context_block else ""
    prompt = (
        f"You are writing the {cfg['name']} MONTHLY reading (this month — the next ~30 days) for a "
        f"personal astrology dashboard. Frame the month through {_MONTHLY_FRAME[system]}. "
        f"USE {cfg['use']} "
        f"Speak ONLY in the {cfg['name']} framework — do NOT use the OTHER tradition's terms "
        f"(no {cfg['forbid']}). "
        "Second person, ~5-6 lines (roughly 100-150 words). Name specific dates inside the month "
        "where the factors give them. Be honest about BOTH the supports and the tensions. No event "
        "predictions, no fortune-telling, no hype, no fluff.\n\n"
        + STYLE_GUIDE_BLOCK + "\n\n"
        f"Headline weather mode: {forecast}.\n"
        "Live monthly factors to weave in (interpret in your framework, do not just list): "
        + "; ".join(facts) + ".\n"
        f"Mood: {mood}\n"
        f"Background: {background}"
        + context_section + "\n\n"
        "Output EXACTLY this shape and nothing else:\n"
        "STATE: <one or two word state label for THIS framework's month, e.g. Expansion, "
        "Consolidation, Pivot, Preparation>\n"
        "BODY: <the second-person passage>"
    )
    try:
        out = subprocess.run([llm, "--lane", "reasoning", "--model", "codex", prompt],
                             capture_output=True, text=True, timeout=180, cwd=DASH)
        if out.returncode != 0:
            log(f"  codex {system} monthly exited {out.returncode}: {out.stderr.strip()[:200]}")
            return None, None
    except Exception as e:
        log(f"  codex {system} monthly failed (non-fatal): {e}")
        return None, None
    raw = out.stdout
    sm = re.search(r"(?im)^\s*STATE:\s*(.+?)\s*$", raw)
    bm = re.search(r"(?is)BODY:\s*(.+)$", raw)
    state_label = sm.group(1).strip().strip(".").strip() if sm else None
    body = re.sub(r"\s+", " ", bm.group(1)).strip() if bm else re.sub(r"\s+", " ", raw).strip()
    if not body:
        log(f"  codex {system} monthly produced no body — null")
        return None, None
    if not state_label:
        state_label = forecast.title()
    return state_label, body


# --- Section 10: Today's Insight (Codex one-liner) -----------------------
def codex_todays_insight(forecast, dominant, daily_changes, phase):
    """<=2 imperative sentences via ~/bin/llm --model codex. No jargon. None on failure."""
    llm = os.path.expanduser("~/bin/llm")
    if not os.path.exists(llm):
        log("  ~/bin/llm not found — todaysInsight null")
        return None
    change_note = ""
    if daily_changes:
        parts = []
        for k in ("momentum", "opportunity", "pressure", "volatility"):
            v = daily_changes.get(k)
            if isinstance(v, (int, float)) and v != 0:
                parts.append(f"{k} {'up' if v > 0 else 'down'} {abs(v)}")
        if parts:
            change_note = " Since yesterday: " + ", ".join(parts) + "."
    framework = astro_framework_block()
    framework_section = ("\n\n" + framework + "\n") if framework else ""
    prompt = (
        "You are writing the single headline insight for a personal 'life weather' "
        "dashboard. Output EXACTLY one or two short sentences, imperative voice "
        "(e.g. 'Build leverage. Do not finalize commitments.'). NO astrology jargon, NO "
        "planet/sign names, NO 'energy'. Concrete and decisive, no hedging, no hype.\n\n"
        f"Current period: {phase}. Headline mode: {forecast}. The period favors building, "
        f"preparation and pipeline over locking in final commitments; there is real "
        f"background pressure.{change_note}"
        + framework_section + "\n\n"
        "Output ONLY the one or two sentences, nothing else."
    )
    try:
        out = subprocess.run([llm, "--lane", "reasoning", "--model", "codex", prompt],
                             capture_output=True, text=True, timeout=180, cwd=DASH)
        if out.returncode != 0:
            log(f"  codex insight exited {out.returncode}: {out.stderr.strip()[:200]}")
            return None
        text = re.sub(r"\s+", " ", out.stdout).strip()
        # keep at most two sentences, hard-trim runaway output
        sentences = re.split(r"(?<=[.!?])\s+", text)
        text = " ".join(sentences[:2]).strip()
        return text or None
    except Exception as e:
        log(f"  codex insight failed (non-fatal): {e}")
        return None


# --- v3.0: Consensus + Snapshots derivation (Home Screen) ----------------
# Per SPEC_V3.md: Home consumes Modern + Traditional + Consensus only (Vedic
# hidden from home, Decision 1). These are ADDITIVE — existing readings/monthlies/
# moonNow are untouched. PVR strict: any Codex failure -> that derived field null,
# never fabricated; the rest of the run is unaffected.

# Qualitative metric label from a 0-100 numeric. Thresholds per SPEC_V3 chunk 1:
# 0-25 Low, 25-50 Moderate, 50-75 High, 75-100 Critical (lower bound inclusive).
def qual_label(v):
    if not isinstance(v, (int, float)):
        return None
    if v < 25:
        return "Low"
    if v < 50:
        return "Moderate"
    if v < 75:
        return "High"
    return "Critical"


# Semantic family of a reading STATE label, for Modern-vs-Traditional comparison.
# Codex emits free-text state labels; we bucket them so adjacency/opposition is
# robust to wording. Unknown labels -> None (treated as "can't assert").
_STATE_FAMILY = {
    # growth / openness
    "expansion": "growth", "growth": "growth", "activation": "growth",
    "opportunity": "growth", "momentum": "growth", "attraction": "growth",
    "ascent": "growth", "opening": "growth", "flow": "growth",
    # restraint / structure
    "consolidation": "restraint", "preparation": "restraint",
    "contraction": "restraint", "foundation": "restraint",
    "restraint": "restraint", "caution": "restraint", "formalize": "restraint",
    "pressure": "restraint", "constraint": "restraint",
    # deep change / flux
    "transformation": "flux", "transition": "flux", "pivot": "flux",
    "disruption": "flux", "restructuring": "flux", "change": "flux",
}
# Families that directly oppose each other.
_OPPOSING_FAMILIES = {frozenset({"growth", "restraint"})}


def _state_family(label):
    if not label:
        return None
    return _STATE_FAMILY.get(label.strip().lower())


def compute_consensus(tropical, traditional):
    """Derive the Modern-vs-Traditional consensus block from the two daily readings.
    Returns the consensus dict (primaryAction left None for compute_primary_action to
    fill), or None if BOTH readings are null. Vedic is intentionally excluded
    (Decision 1). agreementPct/status are pure-derived; no Codex here."""
    m_state = tropical.get("state") if tropical else None
    t_state = traditional.get("state") if traditional else None
    if not m_state and not t_state:
        return None
    # If only one side exists we cannot truly compare -> partial, conservative pct.
    if not m_state or not t_state:
        return {
            "modernState": m_state,
            "traditionalState": t_state,
            "agreementPct": 50,
            "status": "partial",
            "primaryAction": None,
        }
    same = m_state.strip().lower() == t_state.strip().lower()
    mf, tf = _state_family(m_state), _state_family(t_state)
    if same:
        pct, status = 92, "agreement"
    elif mf and tf and frozenset({mf, tf}) in _OPPOSING_FAMILIES:
        pct, status = 30, "disagreement"
    elif mf and tf and mf == tf:
        pct, status = 72, "partial"
    else:
        # one/both unfamiliar, or non-opposing different families -> mild partial
        pct, status = 60, "partial"
    return {
        "modernState": m_state,
        "traditionalState": t_state,
        "agreementPct": pct,
        "status": status,
        "primaryAction": None,
    }


# Per-system extraction config for snapshots (vocabulary isolation, no cross-contam).
_SNAPSHOT_SYSTEMS = {
    "modern": {
        "name": "Modern Western (psychological transit) astrology",
        "driver_desc": ("the single dominant planet driving this reading "
                        "(e.g. Mercury, Jupiter, Saturn)"),
        "forbid": ("Vedic terms (nakshatra, dasha, antardasha, pratyantar, "
                   "Sade Sati, lord of the month/year, profection, whole-sign)"),
    },
    "traditional": {
        "name": "Traditional Hellenistic (whole-sign profection) astrology",
        "driver_desc": ("the dominant lord/planet of the period as named in the "
                        "reading (e.g. Mercury, or a Moon-Venus-Jupiter chain)"),
        "forbid": ("Vedic terms (nakshatra, dasha, antardasha, pratyantar, "
                   "Sade Sati, Vimshottari, sidereal)"),
    },
}


def extract_snapshot(reading, system_name, opp, pre):
    """Compact 5-field Home snapshot for ONE system, extracted from its full daily
    reading. theme/opportunity/pressure are pure-derived (reading state + numeric
    thresholds); driver + action come from ONE Codex pass over the reading body.
    Returns the 5-field dict, or None if the reading itself is null. On Codex
    failure, driver/action are null but the deterministic fields still ship (PVR)."""
    if not reading or not reading.get("body"):
        return None
    cfg = _SNAPSHOT_SYSTEMS[system_name]
    snap = {
        "theme": reading.get("state"),
        "driver": None,
        "opportunity": qual_label(opp),
        "pressure": qual_label(pre),
        "action": None,
    }
    llm = os.path.expanduser("~/bin/llm")
    if not os.path.exists(llm):
        log(f"  ~/bin/llm not found — {system_name} snapshot driver/action null")
        return snap
    prompt = (
        f"You are extracting a compact summary from a {cfg['name']} reading. "
        f"Read the passage and return TWO things ONLY:\n"
        f"1. DRIVER: {cfg['driver_desc']} — name it exactly as the passage frames it. "
        f"Do NOT use {cfg['forbid']}.\n"
        "2. ACTION: a 2-4 word imperative phrase capturing the single recommended "
        "move (e.g. 'Build leverage', 'Prepare quietly', 'Formalize agreements').\n\n"
        "Reading:\n" + reading["body"] + "\n\n"
        "Output EXACTLY this shape and nothing else:\n"
        "DRIVER: <planet or lord-chain>\n"
        "ACTION: <2-4 word imperative>"
    )
    try:
        out = subprocess.run([llm, "--lane", "reasoning", "--model", "codex", prompt],
                             capture_output=True, text=True, timeout=180, cwd=DASH)
        if out.returncode != 0:
            log(f"  codex {system_name} snapshot exited {out.returncode}: "
                f"{out.stderr.strip()[:200]}")
            return snap
    except Exception as e:
        log(f"  codex {system_name} snapshot failed (non-fatal): {e}")
        return snap
    raw = out.stdout
    dm = re.search(r"(?im)^\s*DRIVER:\s*(.+?)\s*$", raw)
    am = re.search(r"(?im)^\s*ACTION:\s*(.+?)\s*$", raw)
    if dm:
        snap["driver"] = dm.group(1).strip().strip(".").strip() or None
    if am:
        snap["action"] = am.group(1).strip().strip(".").strip() or None
    return snap


def compute_primary_action(consensus, snapshots):
    """ONE Codex pass: synthesize Modern + Traditional into a SINGLE actionable
    direction sentence for the Consensus block. Returns the sentence, or None if
    consensus is null (both readings null) or Codex fails (PVR: no fabrication)."""
    if not consensus:
        return None
    llm = os.path.expanduser("~/bin/llm")
    if not os.path.exists(llm):
        log("  ~/bin/llm not found — primaryAction null")
        return None
    m = snapshots.get("modern") or {}
    t = snapshots.get("traditional") or {}
    parts = []
    if m.get("theme") or m.get("action"):
        parts.append(f"Modern system: theme {m.get('theme')}, suggested move "
                     f"'{m.get('action')}'.")
    if t.get("theme") or t.get("action"):
        parts.append(f"Traditional system: theme {t.get('theme')}, suggested move "
                     f"'{t.get('action')}'.")
    status = consensus.get("status")
    prompt = (
        "You advise a high-output operator. Two independent timing systems have read "
        "the current period; synthesize them into ONE actionable direction. Output "
        "EXACTLY one short sentence, imperative voice, concrete and decisive. NO "
        "astrology jargon — NO planet/sign/lord names, NO 'energy', NO hedging, no "
        "hype.\n\n"
        f"System agreement level: {status}.\n"
        + " ".join(parts) + "\n\n"
        "Output ONLY the one sentence, nothing else."
    )
    try:
        out = subprocess.run([llm, "--lane", "reasoning", "--model", "codex", prompt],
                             capture_output=True, text=True, timeout=180, cwd=DASH)
        if out.returncode != 0:
            log(f"  codex primaryAction exited {out.returncode}: "
                f"{out.stderr.strip()[:200]}")
            return None
        text = re.sub(r"\s+", " ", out.stdout).strip()
        sentences = re.split(r"(?<=[.!?])\s+", text)
        text = (sentences[0] if sentences else text).strip()
        return text or None
    except Exception as e:
        log(f"  codex primaryAction failed (non-fatal): {e}")
        return None


# --- main ----------------------------------------------------------------
def compute(now=None, with_codex=True):
    now = now or datetime.now().astimezone()
    today = now.date()
    now_utc = now.astimezone(timezone.utc)

    natal = parse_natal(NATAL_MD)
    missing = [p for p in ["sun", "moon", "mercury", "venus", "mars", "jupiter",
                           "saturn", "uranus", "neptune", "pluto"] if p not in natal]
    if missing:
        log(f"  WARNING natal parse missing: {missing}")

    transits, transit_missing = transits_at(now_utc)
    if transit_missing:
        log(f"  shipping without: {transit_missing}")
    aspects = transit_aspects(transits, natal, max_orb=6.0)

    scores, comps = score_dominance(today, transits, natal)
    dominant = max(scores, key=scores.get)
    forecast = DOMINANT_LABEL[dominant]

    opp, opp_c = score_opportunity(today, transits, natal, aspects)
    pre, pre_c = score_pressure(today, transits, natal, aspects)
    vol, vol_c = score_volatility(today, transits, natal, aspects)
    mom, mom_c = score_momentum(today, transits, natal, aspects)
    metrics = {"opportunity": opp, "pressure": pre, "volatility": vol, "momentum": mom}

    supporting = pick_supporting(today, aspects, dominant)
    pressure_src = pick_pressure(today, aspects, dominant)
    volatility_src = pick_volatility(aspects)
    dur = duration_days(today, dominant, comps, natal)

    drivers = build_drivers(opp_c)
    evidence = build_evidence(opp, opp_c, pre_c, vol_c)

    nxt = next_major_window(today)
    next_days = nxt["daysRemaining"] if nxt else None

    phase_name, phase_start, phase_end = classify_phase(today, forecast, next_days)
    if phase_start is None:
        phase_start = today
        phase_end = today + timedelta(days=dur)

    trend, trend_dir = forecast_trend(today, natal)

    texts = []
    for p in (TROPICAL_MD, VEDIC_MD, COUNCIL_MD):
        try:
            texts.append(open(p, encoding="utf-8").read())
        except Exception as e:
            log(f"  could not read {p}: {e}")
            texts.append("")
    # Confidence ENGINE is deferred to v3 (roadmap). v2 emits null on the contract
    # -> UI renders "Not Rated" in a neutral ring (PVR: never a fabricated grade).
    # The corroboration count is kept in the audit trail only.
    conf = None
    corroboration = confidence_for(dominant, texts)

    # --- Section 9: What Changed (real persistence) ----------------------
    # Compute deltas vs the most recent PRIOR snapshot first, THEN write today's —
    # so a same-day re-run still compares against yesterday, never itself.
    daily_changes = compute_daily_changes(today, metrics, evidence["expansionScore"], now)
    write_history_snapshot(today, forecast, metrics, evidence["expansionScore"], now)

    # --- Sections 2/4/5/6: derived structure (pure, no Codex) ------------
    radar = event_radar(today)
    upcoming = upcoming_events(today)
    moon = moon_now(now_utc, natal)
    now_bar = build_now_bar(forecast, pre, daily_changes, trend_dir, nxt)
    influences = build_planet_influences(dominant, supporting, pressure_src, volatility_src,
                                         opp_c, pre_c, vol_c, metrics)

    # --- Codex layers: Recommended Actions, Daily Reading, Today's Insight
    recommendations, avoidances = ([], [])
    tropical_reading = None
    traditional_reading = None
    vedic_reading = None
    tropical_monthly = None
    traditional_monthly = None
    vedic_monthly = None
    bazi_reading = None
    bazi_monthly = None
    todays_insight = None
    # BaZi core facts (Core Animal + Daily Tactical layers) — pure-computed, Codex-independent.
    bazi_core_data = bazi_core(today, now_utc)
    if with_codex:
        recommendations, avoidances = codex_actions(forecast, dominant, pressure_src, phase_name)
        reading_mood = (
            f"{forecast.title()} headline. Preparation/building phase — supportive openings "
            f"(opportunity {opp}/100) against real background pressure ({pre}/100) and high "
            f"volatility ({vol}/100); momentum {mom}/100. Build leverage now, formalize later."
        )
        trop_factors = tropical_key_factors(aspects, limit=3)
        ved_factors = vedic_factor_list(today, natal, now_utc)
        snap = read_transit_snapshot(today)
        # Moon legs — each system gets ONLY its own leg of moonNow (no blending).
        trop_moon_desc, ved_moon_desc = "", ""
        if moon:
            tl = moon.get("tropical", {})
            if tl:
                trop_moon_desc = (f"Transit Moon in {tl.get('sign')} {tl.get('degree')}°, "
                                  f"natal house {tl.get('house')}")
            vl = moon.get("vedic", {})
            if vl:
                ved_moon_desc = (f"Sidereal Moon in {vl.get('sign')} {vl.get('degree')}°, "
                                 f"nakshatra {vl.get('nakshatra')} pada {vl.get('nakshatra_pada')}, "
                                 f"house {vl.get('house')}")
        # Three independent passes — each sees ONLY its framework's MD context (no
        # blending). v2.2.3 adds the Traditional/Hellenistic pass between the two.
        trad_factors = traditional_profection(today, natal, aspects)
        # Principle #6: announce standing themes only on their activation/shift day.
        activations = standing_theme_activations(today, now_utc)
        ts, tb = codex_reading("tropical", forecast, trop_factors, trop_moon_desc,
                               tropical_context_block(), reading_mood, snap,
                               _activation_directive("tropical", activations))
        trs, trb = codex_reading("traditional", forecast, trad_factors, "",
                                 traditional_context_block(), reading_mood, "",
                                 _activation_directive("traditional", activations))
        vs, vb = codex_reading("vedic", forecast, ved_factors, ved_moon_desc,
                               vedic_context_block(), reading_mood, "",
                               _activation_directive("vedic", activations))
        bzs, bzb = codex_reading("bazi", forecast, bazi_factors(today, now_utc), "",
                                 bazi_context_block(), reading_mood, "",
                                 _activation_directive("bazi", activations))
        tropical_reading = {"state": ts, "body": tb} if tb else None
        traditional_reading = {"state": trs, "body": trb} if trb else None
        vedic_reading = {"state": vs, "body": vb} if vb else None
        bazi_reading = {"state": bzs, "body": bzb} if bzb else None
        # v2.3 — three MONTHLY passes (this month), each in its native month frame.
        # Independent of the dailies: a monthly failure leaves that system's daily intact.
        trop_m_factors = tropical_monthly_factors(today, now_utc)
        trad_m_factors = traditional_monthly_factors(today, natal, aspects)
        ved_m_factors = vedic_monthly_factors(today, now_utc)
        tms, tmb = codex_monthly_reading("tropical", forecast, trop_m_factors,
                                         tropical_context_block(), reading_mood)
        trms, trmb = codex_monthly_reading("traditional", forecast, trad_m_factors,
                                           traditional_context_block(), reading_mood)
        vms, vmb = codex_monthly_reading("vedic", forecast, ved_m_factors,
                                         vedic_context_block(), reading_mood)
        bzms, bzmb = codex_monthly_reading("bazi", forecast, bazi_monthly_factors(today, now_utc),
                                           bazi_context_block(), reading_mood)
        tropical_monthly = {"state": tms, "body": tmb} if tmb else None
        traditional_monthly = {"state": trms, "body": trmb} if trmb else None
        vedic_monthly = {"state": vms, "body": vmb} if vmb else None
        bazi_monthly = {"state": bzms, "body": bzmb} if bzmb else None
        todays_insight = codex_todays_insight(forecast, dominant, daily_changes, phase_name)

    # --- v3.0 Home: Consensus + Snapshots (additive; Vedic excluded per Decision 1)
    # Derived AFTER the readings exist. PVR: null-graceful at every step.
    consensus = None
    snapshots = {"modern": None, "traditional": None}
    if with_codex:
        consensus = compute_consensus(tropical_reading, traditional_reading)
        snapshots["modern"] = extract_snapshot(tropical_reading, "modern", opp, pre)
        snapshots["traditional"] = extract_snapshot(traditional_reading, "traditional", opp, pre)
        if consensus is not None:
            consensus["primaryAction"] = compute_primary_action(consensus, snapshots)

    sources = [NATAL_MD, TROPICAL_MD, VEDIC_MD, COUNCIL_MD]

    state = {
        # --- Section 1: Hero Solar Intelligence ---
        "forecast": forecast,
        "subtitle": SUBTITLE.get(forecast, ""),
        "dominantPlanet": cap(dominant),
        "supportingPlanet": cap(supporting),
        "pressurePlanet": cap(pressure_src),
        "volatilityPlanet": cap(volatility_src),
        "confidence": conf,          # always null in v2 -> UI "Not Rated"
        "durationDays": dur,
        # --- Section 2: Now Bar ---
        "nowBar": now_bar,
        # --- Section 3: Current Phase ---
        "currentPhase": phase_name,
        "currentPhaseStart": phase_start.isoformat() if hasattr(phase_start, "isoformat") else phase_start,
        "currentPhaseEnd": phase_end.isoformat() if hasattr(phase_end, "isoformat") else phase_end,
        # --- Section 4: Event Radar (pure timing) ---
        "eventRadar": radar,
        # --- Section 5: Planet Influences ---
        "planetInfluences": influences,
        # --- Section 6: Upcoming Events ---
        "upcomingEvents": upcoming,
        # --- Section 7: Sky Conditions (renders from these 4 metrics) ---
        "opportunity": opp,
        "pressure": pre,
        "volatility": vol,
        "momentum": mom,
        # --- Moon Now (live Moon position, both systems; null on ephemeris failure) ---
        "moonNow": moon,
        # --- Section 8: Daily Reading (v2.2.3 split: three independent sub-readings) ---
        "tropicalReading": tropical_reading,         # Modern Western — {state, body} or null
        "traditionalReading": traditional_reading,   # Hellenistic whole-sign — {state, body} or null
        "vedicReading": vedic_reading,               # sidereal Vedic — {state, body} or null
        "baziReading": bazi_reading,                 # Eastern Four Pillars — {state, body} or null
        # --- v2.3: Monthly readings (this month, native month frame per system) ---
        "tropicalMonthly": tropical_monthly,         # Modern — Sun-sign transit month
        "traditionalMonthly": traditional_monthly,   # Traditional — profection month
        "vedicMonthly": vedic_monthly,               # Vedic — Vimshottari sub-period + nakshatra cycle
        "baziMonthly": bazi_monthly,                 # BaZi — current solar-term month + next jié handoff
        # --- v2.4: BaZi core facts (Core Animal + Daily Tactical layers; pure-computed) ---
        "baziCore": bazi_core_data,                  # {dayMaster, coreAnimal, animalStack, current*, daYun, tacticalSlots}
        # --- v3.0 Home Screen: Consensus + Snapshots (additive; Vedic excluded) ---
        "consensus": consensus,                      # Modern-vs-Traditional agreement or null
        "snapshots": snapshots,                      # {modern, traditional} compact 5-field summaries
        # --- v3.0 drawer stubs (null now; populated in v3.1 per Decision 2) ---
        "tropicalQuarter": None,
        "traditionalQuarter": None,
        "tropicalYear": None,
        "traditionalYear": None,
        "dailyReading": None,                        # DEPRECATED — split into the three above
        # --- Section 9: What Changed (null on first day) ---
        "dailyChanges": daily_changes,
        # --- Section 10: Today's Insight ---
        "todaysInsight": todays_insight,
        # --- Section 11: Recommended Actions ---
        "recommendations": recommendations,
        "avoidances": avoidances,
        # --- Section 12: Top Drivers ---
        "drivers": drivers,
        # --- Section 13: Why This Forecast ---
        "evidence": evidence,
        # --- Section 7 (legacy): Next Major Window + Forecast Trend (kept for
        #     nowBar/Upcoming derivation + audit; not a standalone v2 section) ---
        "nextWindow": nxt,
        "forecastTrend": trend,
        "trendDirection": trend_dir,
        # --- meta ---
        "updatedAt": now.isoformat(timespec="seconds"),
        "sourceMode": "static",
        "currentDate": today.isoformat(),
        "sources": [os.path.relpath(s, VAULT) for s in sources],
        # --- audit trail (not part of the locked contract; aids sanity-check) ---
        "scoringDetail": {
            "dominanceScores": scores,
            "corroboration": corroboration,
            "lordOfYear": lord_of_year(today),
            "activeWindows": [w["name"] for w in active_windows(today)],
            "metricDetail": {
                "opportunity": [d for _, d, _ in opp_c],
                "pressure": [d for _, d, _ in pre_c],
                "volatility": [d for _, d, _ in vol_c],
                "momentum": [d for _, d, _ in mom_c],
            },
            "transitSigns": {k: f"{round(v % 30, 2)}° {sign_of(v)}" for k, v in transits.items()},
            "tightAspects": sorted(aspects, key=lambda a: a["orb"])[:12],
            "transitMissing": transit_missing,
            "natalMissing": missing,
        },
    }
    return state


def main():
    out_path = OUT_PATH
    if "--out" in sys.argv:
        i = sys.argv.index("--out")
        if i + 1 < len(sys.argv):
            out_path = sys.argv[i + 1]
    now = None
    if "--date" in sys.argv:
        i = sys.argv.index("--date")
        if i + 1 < len(sys.argv):
            d = datetime.strptime(sys.argv[i + 1], "%Y-%m-%d").date()
            now = datetime.combine(d, time(12, 0)).astimezone()
    with_codex = "--no-codex" not in sys.argv
    state = compute(now=now, with_codex=with_codex)
    with open(out_path, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    nw = state["nextWindow"]
    dc = state["dailyChanges"]
    log(f"Timing Weather v2.0: {state['forecast']} (dominant={state['dominantPlanet']}, "
        f"conf={state['confidence']}, dur={state['durationDays']}d, phase={state['currentPhase']}, "
        f"changes={'tracking-begins' if dc is None else 'computed'}, "
        f"reading=trop:{'yes' if state['tropicalReading'] else 'null'}/"
        f"trad:{'yes' if state['traditionalReading'] else 'null'}/"
        f"ved:{'yes' if state['vedicReading'] else 'null'}, "
        f"monthly=trop:{'yes' if state['tropicalMonthly'] else 'null'}/"
        f"trad:{'yes' if state['traditionalMonthly'] else 'null'}/"
        f"ved:{'yes' if state['vedicMonthly'] else 'null'}, "
        f"insight={'yes' if state['todaysInsight'] else 'null'}, "
        f"next={nw['title'] if nw else None}) -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
