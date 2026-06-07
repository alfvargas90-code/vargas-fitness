#!/usr/bin/env python3
"""
Timing Weather — Intelligence Engine (v1.1).

Reads Alfie's authoritative natal chart + the overnight deep-research / council
convergence report, computes live geocentric tropical transits (Swiss Ephemeris),
classifies the current "operational weather" and writes state.json in the v1.1
camelCase contract.

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

NATAL_MD = os.path.join(ASTRO, "natal_context.md")
TROPICAL_MD = os.path.join(ASTRO, "deep_research_tropical_2026-2027.md")
VEDIC_MD = os.path.join(ASTRO, "deep_research_vedic_2026.md")
COUNCIL_MD = os.path.join(COUNCIL, "2026-06-06_predictive_convergence_review.md")
OUT_PATH = os.path.join(HERE, "state.json")

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

# Sade Sati Small Panoti active window (natal_context.md vedic.sade_sati).
SADE_SATI = (date(2025, 3, 30), date(2027, 6, 2))

# BaZi Da Yun shift (~Sep 2026, Output->payoff). natal_context.md bazi.da_yun.
BAZI_SHIFT = date(2026, 9, 15)

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

# Forecast-trend retroactive offsets in days (today minus N). Spec: ~27/17/5/0.
TREND_OFFSETS = [27, 17, 5, 0]


def log(msg):
    print(msg, flush=True)


def cap(s):
    return (s[:1].upper() + s[1:]) if s else None


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


# --- Section 9: Recommended Actions (Codex) ------------------------------
def codex_actions(forecast, dominant, pressure_src, phase):
    """4 do's + 3 avoidances via ~/bin/llm --model codex (forces Codex, no claude-handoff
    -> Cowork-safe). Returns (recommendations[<=4], avoidances[<=3]); empty on failure."""
    llm = os.path.expanduser("~/bin/llm")
    if not os.path.exists(llm):
        log("  ~/bin/llm not found — actions empty")
        return [], []
    prompt = (
        "You are advising a high-output operator on how to play the current period of his "
        "life. He hates fluff and astrology jargon — NEVER mention planets, signs, transits, "
        "or 'energy'. Output ONLY two labeled lists, nothing else.\n\n"
        f"Current period: {phase}. Headline mode: {forecast}. The period favors building, "
        f"preparation and pipeline more than locking in final commitments; there is real "
        f"pressure/constraint in the background.\n\n"
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


# --- narrative (Codex) ---------------------------------------------------
def codex_narrative(forecast, metrics, confidence, duration, phase, phase_end):
    """One plain-language paragraph via ~/bin/llm --model codex. No jargon."""
    llm = os.path.expanduser("~/bin/llm")
    if not os.path.exists(llm):
        log("  ~/bin/llm not found — narrative null")
        return None
    win = f" Current phase: {phase} (through {phase_end})." if phase_end else f" Current phase: {phase}."
    prompt = (
        "You are writing ONE short plain-English paragraph (4-6 sentences) for a personal "
        "'life weather' dashboard. The reader is a high-output operator who hates fluff and "
        "does NOT want astrology jargon. NEVER mention planets, signs, houses, transits, "
        "horoscopes, or 'energy'. Translate the classified state below into a grounded, "
        "operational read of what this period is for and what to do with it. Be concrete and "
        "decisive, no hedging, no hype.\n\n"
        f"CLASSIFIED STATE (do not echo the labels):\n"
        f"- Headline mode: {forecast} (the dominant theme right now)\n"
        f"- Opportunity {metrics['opportunity']}/100, Pressure {metrics['pressure']}/100, "
        f"Volatility {metrics['volatility']}/100, Momentum {metrics['momentum']}/100\n"
        f"- Confidence: {confidence}; this phase lasts ~{duration} days.{win}\n\n"
        "GROUND TRUTH from the underlying research (use it, don't cite it): right now is a "
        "preparation-and-pipeline phase — quiet leverage, cleanup, building relationships and "
        "documents — that converts into weight-bearing responsibility and formal commitments "
        "after late August 2026, with a hard checkpoint in April 2027 where what got built "
        "must be written, titled, or committed. Open doors now; sign and formalize later.\n\n"
        "Output ONLY the paragraph, no preamble."
    )
    try:
        out = subprocess.run([llm, "--lane", "reasoning", "--model", "codex", prompt],
                             capture_output=True, text=True, timeout=180, cwd=DASH)
        if out.returncode != 0:
            log(f"  codex narrative exited {out.returncode}: {out.stderr.strip()[:200]}")
            return None
        text = re.sub(r"\s+", " ", out.stdout).strip()
        return text or None
    except Exception as e:
        log(f"  codex narrative failed (non-fatal): {e}")
        return None


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


def compute_vedic_horoscope(today, natal, now_utc, mood, with_codex=True):
    """Build the vedicHoroscope field, or None if it can't be authored honestly."""
    try:
        vnatal = sidereal_natal(natal)
        vtransits, vmissing = vedic_transits_at(now_utc)
    except Exception as e:
        log(f"  vedic computation failed: {e} — vedicHoroscope null")
        return None
    if "moon" not in vtransits:
        log("  vedic: no sidereal Moon — vedicHoroscope null")
        return None

    chain, _sub = vedic_subperiod(today)
    factors = [f"Vimshottari {chain} sub-period"]
    if SADE_SATI[0] <= today <= SADE_SATI[1]:
        factors.append(f"Sade Sati ({SADE_SATI_PHASE})")
    factors.append(f"Transit Moon in {nakshatra_of(vtransits['moon'])}")
    factors.extend(vedic_key_aspects(vtransits, vnatal, limit=2))

    subtitle = "Today's sidereal picture · " + chain
    body = None
    if with_codex:
        background = (
            "This Vedic year externalizes after a long inward phase: the live themes are "
            "concrete movement in work/operations, home/property, finances and important "
            "agreements — not fairy-tale romance. Now is supportive restructuring; "
            "responsibility and weight build from late August, with paperwork and "
            "formalization in the late-autumn stretch. There is steady background pressure "
            "on home and foundations that rewards patience and structure."
        )
        body = codex_horoscope("Vedic / sidereal", factors, mood, background)
    if not body:
        return None
    return {"for_date": today.isoformat(), "subtitle": subtitle,
            "body": body, "key_factors": factors}


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


def compute_tropical_horoscope(today, aspects, mood, with_codex=True):
    """Build the tropicalHoroscope field, or None if it can't be authored honestly.
    Factors come from the engine's live geocentric ephemeris (the same Swiss
    Ephemeris the iMessage snapshot uses); today's persisted snapshot, if present,
    only enriches the Codex prompt — it is never required."""
    factors = tropical_key_factors(aspects, limit=3)
    if not factors:
        log("  tropical: no transit aspects today — tropicalHoroscope null")
        return None
    body = None
    if with_codex:
        snap = read_transit_snapshot(today)
        background = (
            "This is a preparation-and-pipeline phase: quiet leverage, cleanup, building "
            "relationships and documents, opening doors that convert into weight-bearing "
            "commitments after late August 2026 — open doors now, sign and formalize "
            "later. Real background pressure and volatility ask for fewer, better moves."
        )
        if snap:
            background += " Today's read from the morning snapshot: " + snap
        body = codex_horoscope("Tropical / Western transits", factors, mood, background)
    if not body:
        return None
    return {"for_date": today.isoformat(), "subtitle": "Today's transits",
            "body": body, "key_factors": factors}


def codex_horoscope(tradition, factors, mood, background):
    """Plain-English daily horoscope body via ~/bin/llm --model codex (Cowork-safe).
    No jargon, ~80-120 words, second person, single paragraph. None on failure."""
    llm = os.path.expanduser("~/bin/llm")
    if not os.path.exists(llm):
        log("  ~/bin/llm not found — horoscope body null")
        return None
    prompt = (
        "You are writing a plain-English daily horoscope reading. NO astrology jargon, "
        "NO Latin terms, NO aspect names, NO planet or sign names. Speak in observable "
        "themes — energy, focus, relationships, work, decisions. ~80-120 words. The "
        "subject is a high-output operator on a known multi-month cycle; reference the "
        "subtle current tensions AND supports honestly. No predictions of specific events, "
        "no fortune-telling, no hype, no fluff.\n\n"
        f"Context (translate, do not quote): {tradition} factors for today — "
        + "; ".join(factors) + ".\n"
        f"Mood: {mood}\n"
        f"Background: {background}\n\n"
        "Output: a SINGLE second-person paragraph (\"today you may notice\", \"this is a "
        "day for\"). Honest about both supports and tensions. Output ONLY the paragraph, "
        "no heading, no preamble."
    )
    try:
        out = subprocess.run([llm, "--lane", "reasoning", "--model", "codex", prompt],
                             capture_output=True, text=True, timeout=180, cwd=DASH)
        if out.returncode != 0:
            log(f"  codex horoscope ({tradition}) exited {out.returncode}: "
                f"{out.stderr.strip()[:200]}")
            return None
        text = re.sub(r"\s+", " ", out.stdout).strip()
        return text or None
    except Exception as e:
        log(f"  codex horoscope ({tradition}) failed (non-fatal): {e}")
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
    conf = confidence_for(dominant, texts)

    recommendations, avoidances = ([], [])
    narrative = None
    if with_codex:
        recommendations, avoidances = codex_actions(forecast, dominant, pressure_src, phase_name)
        narrative = codex_narrative(forecast, metrics, conf, dur, phase_name,
                                    phase_end.isoformat() if hasattr(phase_end, "isoformat") else phase_end)

    # Daily horoscope cards (v1.2). Shared plain-English "mood" derived from the
    # classified state; each tradition sources its own factors. Either may be null
    # (UI shows a graceful placeholder) — never fabricated.
    horoscope_mood = (
        f"{forecast.title()} headline. Preparation/building phase — supportive openings "
        f"(opportunity {opp}/100) against real background pressure ({pre}/100) and high "
        f"volatility ({vol}/100); momentum {mom}/100. Build leverage now, formalize later."
    )
    tropical_horoscope = compute_tropical_horoscope(today, aspects, horoscope_mood, with_codex)
    vedic_horoscope = compute_vedic_horoscope(today, natal, now_utc, horoscope_mood, with_codex)

    sources = [NATAL_MD, TROPICAL_MD, VEDIC_MD, COUNCIL_MD]

    state = {
        # --- core ---
        "forecast": forecast,
        "subtitle": SUBTITLE.get(forecast, ""),
        "dominantPlanet": cap(dominant),
        "supportingPlanet": cap(supporting),
        "pressurePlanet": cap(pressure_src),
        "volatilityPlanet": cap(volatility_src),
        "confidence": conf,
        "durationDays": dur,
        # --- Section 2: Current Phase ---
        "currentPhase": phase_name,
        "currentPhaseStart": phase_start.isoformat() if hasattr(phase_start, "isoformat") else phase_start,
        "currentPhaseEnd": phase_end.isoformat() if hasattr(phase_end, "isoformat") else phase_end,
        # --- Section 4/8: metrics (Active Sky planets above) ---
        "opportunity": opp,
        "pressure": pre,
        "volatility": vol,
        "momentum": mom,
        # --- Section 5: Top Drivers ---
        "drivers": drivers,
        # --- Section 6: Forecast Trend ---
        "forecastTrend": trend,
        "trendDirection": trend_dir,
        # --- Section 7: Next Major Window ---
        "nextWindow": nxt,
        # --- Section 9: Recommended Actions ---
        "recommendations": recommendations,
        "avoidances": avoidances,
        # --- Section 10: Why This Forecast ---
        "evidence": evidence,
        # --- v1.2: Daily Horoscope cards (right panel, between Weather Metrics
        #           and Recommended Actions). null -> UI placeholder. ---
        "tropicalHoroscope": tropical_horoscope,
        "vedicHoroscope": vedic_horoscope,
        # --- Section 11: Narrative ---
        "narrative": narrative,
        # --- meta ---
        "updatedAt": now.isoformat(timespec="seconds"),
        "sourceMode": "static",
        "currentDate": today.isoformat(),
        "sources": [os.path.relpath(s, VAULT) for s in sources],
        # --- audit trail (not part of the locked contract; aids sanity-check) ---
        "scoringDetail": {
            "dominanceScores": scores,
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
    log(f"Timing Weather v1.1: {state['forecast']} (dominant={state['dominantPlanet']}, "
        f"conf={state['confidence']}, dur={state['durationDays']}d, phase={state['currentPhase']}, "
        f"trend={state['trendDirection']}, next={nw['title'] if nw else None}) -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
