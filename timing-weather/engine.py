#!/usr/bin/env python3
"""
Timing Weather — Intelligence Engine (Phase 1).

Reads Alfie's authoritative natal chart + the overnight deep-research / council
convergence report, computes live geocentric tropical transits (Swiss Ephemeris),
classifies the current "operational weather" (dominant planet, forecast label,
supporting/pressure sources, four 0-100 weather metrics, confidence, duration),
asks Codex for a single plain-language narrative paragraph, and writes state.json.

Engine-first, no fake data: any metric that can't be honestly computed is null.

Stack note: the spec named pyephem, but this repo already ships a proven,
autonomous-safe pyswisseph venv (polar/.venv, swisseph 2.10.03) used by
polar/lunar_stress.py. Reusing it is the honest path — Swiss Ephemeris is more
accurate and already runs under launchd without venv-rebuild hazards. Same
natal constants as lunar_stress.py.

Sources (read each run):
  02_Astrology/Alfie/natal_context.md                  (YAML frontmatter = authoritative)
  02_Astrology/Alfie/deep_research_tropical_2026-2027.md
  02_Astrology/Alfie/deep_research_vedic_2026.md
  05_Council/octopus-debates/2026-06-06_predictive_convergence_review.md

Run:  polar/.venv/bin/python timing-weather/engine.py
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime, date, timedelta, timezone

import swisseph as swe

# --- paths ---------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))               # .../fitness-dashboard/timing-weather
DASH = os.path.dirname(HERE)                                     # .../fitness-dashboard
VAULT = os.path.dirname(os.path.dirname(DASH))                   # .../alfredo.v
ASTRO = os.path.join(VAULT, "02_Astrology", "Alfie")
COUNCIL = os.path.join(VAULT, "05_Council", "octopus-debates")

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

# The five dominance-eligible planets and their forecast labels (per spec).
DOMINANT_LABEL = {
    "jupiter": "EXPANSION",
    "saturn": "CONSOLIDATION",
    "pluto": "TRANSFORMATION",
    "uranus": "DISRUPTION",
    "venus": "ATTRACTION",
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

# Council windows (from 2026-06-06 convergence review). dominance_weight=True only for
# the structurally strong top windows that legitimately claim a dominant planet; the
# weak/admin clearing window feeds display + the Pressure metric, not dominance.
COUNCIL_WINDOWS = [
    {"name": "Late May–early June clearing", "start": date(2026, 5, 28), "end": date(2026, 6, 8),
     "driver": "saturn", "polarity": "neutral", "dominance_weight": False},
    {"name": "Jupiter return — chapter reset", "start": date(2026, 7, 12), "end": date(2026, 8, 1),
     "driver": "jupiter", "polarity": "positive", "dominance_weight": True},
    {"name": "Embodiment pivot — Saturn year begins", "start": date(2026, 8, 12), "end": date(2026, 10, 8),
     "driver": "saturn", "polarity": "saturnian", "dominance_weight": True},
    {"name": "Jupiter–Venus benefic window", "start": date(2026, 10, 7), "end": date(2026, 10, 8),
     "driver": "venus", "polarity": "positive", "dominance_weight": True},
    {"name": "Contract hinge", "start": date(2026, 10, 29), "end": date(2026, 12, 4),
     "driver": "venus", "polarity": "neutral", "dominance_weight": False},
    {"name": "Consolidation / Saturn-square-Saturn checkpoint", "start": date(2027, 1, 8), "end": date(2027, 4, 20),
     "driver": "saturn", "polarity": "saturnian", "dominance_weight": True},
]

# 2026–2027 eclipses (approximate dates) for volatility proximity.
ECLIPSES = [date(2026, 2, 17), date(2026, 3, 3), date(2026, 8, 12), date(2026, 8, 28),
            date(2027, 2, 6), date(2027, 2, 20), date(2027, 7, 18), date(2027, 8, 2), date(2027, 8, 17)]


def log(msg):
    print(msg, flush=True)


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
    """All transit->natal major aspects within orb.
    Returns list of dicts {transit, natal, aspect, orb}."""
    out = []
    for t, tl in transits.items():
        for n, nl in natal.items():
            asp, orb = closest_aspect(tl, nl, max_orb)
            if asp:
                out.append({"transit": t, "natal": n, "aspect": asp, "orb": round(orb, 2)})
    return out


# --- scoring -------------------------------------------------------------
def active_windows(today):
    return [w for w in COUNCIL_WINDOWS if w["start"] <= today <= w["end"]]


def lord_of_year(today):
    return LORD_AFTER_FLIP if today >= PROFECTION_FLIP else LORD_BEFORE_FLIP


def score_dominance(today, transits, natal):
    """Score the five dominance-eligible planets. Returns (scores, components).
    Components are kept for the duration branch + audit trail."""
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
        # tightest natal aspect for this transiting planet (0..5, exact=5)
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


def score_opportunity(today, transits, natal, aspects):
    pts, why = 0, []
    benefics = {"sun", "venus", "jupiter"}
    for a in aspects:
        if a["transit"] == "jupiter" and a["natal"] in benefics:
            if a["aspect"] in SOFT or a["aspect"] == "conjunction":
                pts += 25; why.append(f"Jupiter {a['aspect']} natal {a['natal']} ({a['orb']}°)")
        if a["transit"] == "venus" and a["natal"] in {"sun", "moon", "venus", "jupiter", "asc"}:
            if a["aspect"] in SOFT or a["aspect"] == "conjunction":
                pts += 10; why.append(f"Venus {a['aspect']} natal {a['natal']} ({a['orb']}°)")
    if lord_of_year(today) == "jupiter":
        pts += 15; why.append("Jupiter is lord of the year (benefic regime)")
    for w in active_windows(today):
        if w["polarity"] == "positive":
            pts += 20; why.append(f"inside positive council window: {w['name']}")
    # an approaching benefic window is real (forward-loaded) opportunity — mirrors momentum
    for w in COUNCIL_WINDOWS:
        if w["polarity"] != "positive" or not w["dominance_weight"]:
            continue
        days = (w["start"] - today).days
        if 0 < days <= 45:
            pts += int(round((45 - days) / 45 * 15)); why.append(f"approaching benefic window: {w['name']} ({days}d)")
            break
    if VENUS_ANTARDASHA[0] <= today <= VENUS_ANTARDASHA[1]:
        pts += 10; why.append("Vedic Moon–Venus antardasha (relationship-positive)")
    # Solar-return Muntha 9th (favorable) applies from the birthday varshaphal onward.
    if today >= PROFECTION_FLIP:
        pts += 8; why.append("Varshaphal Muntha in 9th (favorable)")
    return clamp(pts), why


def score_pressure(today, transits, natal, aspects):
    pts, why = 0, []
    pers = {"sun", "moon", "mercury", "venus", "mars", "asc", "saturn", "neptune"}
    for a in aspects:
        if a["transit"] == "saturn" and a["natal"] in pers and a["aspect"] in HARD:
            pts += 25; why.append(f"Saturn {a['aspect']} natal {a['natal']} ({a['orb']}°)")
        if a["transit"] == "mars" and a["natal"] in {"sun", "moon", "mercury", "venus", "mars", "asc"} and a["aspect"] in HARD:
            pts += 12; why.append(f"Mars {a['aspect']} natal {a['natal']} ({a['orb']}°)")
    if SADE_SATI[0] <= today <= SADE_SATI[1]:
        pts += 15; why.append("Sade Sati (Small Panoti) — pressure on foundations")
    for w in active_windows(today):
        if w["polarity"] == "saturnian":
            pts += 20; why.append(f"inside Saturnian council window: {w['name']}")
        elif w["polarity"] == "neutral" and w["driver"] == "saturn":
            pts += 8; why.append(f"inside admin/clearing window: {w['name']}")
    return clamp(pts), why


def score_volatility(today, transits, natal, aspects):
    pts, why = 0, []
    for a in aspects:
        if a["transit"] == "uranus":
            if a["aspect"] in HARD:
                pts += 25; why.append(f"Uranus {a['aspect']} natal {a['natal']} ({a['orb']}°)")
            elif a["aspect"] in SOFT:
                pts += 8; why.append(f"Uranus {a['aspect']} natal {a['natal']} ({a['orb']}°)")
        if a["natal"] in {"asc", "mc"} and a["orb"] <= 3.0 and a["transit"] in {"saturn", "uranus", "pluto", "mars", "jupiter"}:
            pts += 12; why.append(f"{a['transit']} {a['aspect']} natal {a['natal']} (angular, {a['orb']}°)")
    near = min((abs((e - today).days) for e in ECLIPSES), default=999)
    if near <= 14:
        pts += 25; why.append(f"eclipse within {near} days")
    return clamp(pts), why


def score_momentum(today, transits, natal, aspects):
    pts, why = 0, []
    fast = sum(1 for a in aspects if a["transit"] in FAST_BODIES and a["orb"] <= 3.0)
    if fast:
        pts += 8 * fast; why.append(f"{fast} fast transit(s) exact within 3°")
    # proximity to a strong council window (peak)
    for w in COUNCIL_WINDOWS:
        if not w["dominance_weight"]:
            continue
        if w["start"] <= today <= w["end"]:
            pts += 25; why.append(f"inside strong window peak: {w['name']}")
            break
        days = (w["start"] - today).days
        if 0 < days <= 45:
            pts += int(round((45 - days) / 45 * 18)); why.append(f"approaching {w['name']} ({days}d)")
            break
    # BaZi Da Yun shift proximity
    dy = abs((BAZI_SHIFT - today).days)
    if dy <= 120:
        pts += int(round((120 - dy) / 120 * 20)); why.append(f"BaZi Da Yun shift within {dy} days")
    return clamp(pts), why


def pick_supporting(today, transits, natal, aspects, dominant):
    """Most opportunity-contributing planet other than the dominant."""
    if lord_of_year(today) == "venus":
        pass
    # Venus antardasha + any Venus/Jupiter soft contact -> prefer that benefic.
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


def pick_pressure(today, transits, natal, aspects, dominant):
    """Most pressure-contributing planet (hard aspect malefic)."""
    cands = []
    for a in aspects:
        if a["transit"] in {"saturn", "mars", "pluto"} and a["aspect"] in HARD:
            w = {"saturn": 3, "pluto": 2, "mars": 1}[a["transit"]]
            cands.append((a["transit"], w, a["orb"]))
    if not cands:
        if SADE_SATI[0] <= today <= SADE_SATI[1]:
            return "saturn"
        return None
    # highest malefic weight, then tightest orb
    cands.sort(key=lambda x: (-x[1], x[2]))
    return cands[0][0]


def duration_days(today, dominant, comps, transits, natal):
    """Days the current dominant 'weather' plausibly persists.
    Branch by what is driving the dominance:
      - lord-of-year driven  -> days until the profection flip (regime boundary)
      - council-window driven -> days until that window ends
      - aspect driven        -> forward-scan until the primary aspect exits 3° orb."""
    c = comps[dominant]
    driver = max(("lord", c["lord"]), ("window", c["window"]), ("aspect", c["aspect"]),
                 ("static", c["static"]), key=lambda x: x[1])[0]
    if driver == "lord" and today < PROFECTION_FLIP:
        return (PROFECTION_FLIP - today).days
    if driver == "window":
        for w in active_windows(today):
            if w["dominance_weight"] and w["driver"] == dominant:
                return max(1, (w["end"] - today).days)
    # aspect branch (or fallback): scan the dominant's tightest aspect to 3° exit
    nat = c.get("aspect_to")
    if nat and nat in natal:
        nl = natal[nat]
        for d in range(0, 400):
            jd = jd_now((datetime.combine(today, datetime.min.time()) + timedelta(days=d)).replace(tzinfo=timezone.utc))
            asp, orb = closest_aspect(lon_of(jd, SWE_BODY[dominant]), nl, 30.0)
            if orb is None or orb > 3.0:
                return max(1, d)
    # last resort: days to profection flip if in the future, else 30
    if today < PROFECTION_FLIP:
        return (PROFECTION_FLIP - today).days
    return 30


def confidence_for(dominant, texts):
    """Corroboration count: dominant planet named across the two research MDs + council.
    >=2 -> High, 1 -> Medium, 0 -> Low (per spec). Presence-based heuristic."""
    n = sum(1 for t in texts if re.search(rf"\b{dominant}\b", t, re.I))
    return "High" if n >= 2 else "Medium" if n == 1 else "Low"


def active_council_window_for(today):
    for w in active_windows(today):
        return {"name": w["name"], "started": w["start"].isoformat(), "ends": w["end"].isoformat()}
    return {"name": None, "started": None, "ends": None}


# --- narrative (Codex) ---------------------------------------------------
def codex_narrative(state):
    """Single plain-language paragraph via ~/bin/llm --lane reasoning --model codex.
    No astrology jargon. Returns string or None on failure (UI shows fallback)."""
    llm = os.path.expanduser("~/bin/llm")
    if not os.path.exists(llm):
        log("  ~/bin/llm not found — narrative null")
        return None
    wm = state["weather_metrics"]
    acw = state["active_council_window"]
    win = f" Active window: {acw['name']} (through {acw['ends']})." if acw["name"] else ""
    prompt = (
        "You are writing ONE short plain-English paragraph (4-6 sentences) for a personal "
        "'life weather' dashboard. The reader is a high-output operator who hates fluff and "
        "does NOT want astrology jargon. NEVER mention planets, signs, houses, transits, "
        "horoscopes, or 'energy'. Translate the classified state below into a grounded, "
        "operational read of what this period is for and what to do with it. Be concrete and "
        "decisive, no hedging, no hype.\n\n"
        f"CLASSIFIED STATE (do not echo the labels):\n"
        f"- Headline mode: {state['forecast_label']} (the dominant theme right now)\n"
        f"- Opportunity {wm['opportunity']}/100, Pressure {wm['pressure']}/100, "
        f"Volatility {wm['volatility']}/100, Momentum {wm['momentum']}/100\n"
        f"- Confidence: {state['confidence']}; this phase lasts ~{state['duration_days']} days.{win}\n\n"
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


# --- main ----------------------------------------------------------------
def compute(now=None):
    now = now or datetime.now().astimezone()
    today = now.date()
    now_utc = now.astimezone(timezone.utc)

    natal = parse_natal(NATAL_MD)
    missing = [p for p in ["sun", "moon", "mercury", "venus", "mars", "jupiter",
                           "saturn", "uranus", "neptune", "pluto"] if p not in natal]
    if missing:
        log(f"  WARNING natal parse missing: {missing}")

    jd = jd_now(now_utc)
    transits, transit_missing = {}, []
    for name, body in SWE_BODY.items():
        try:
            transits[name] = lon_of(jd, body)
        except Exception as e:
            transit_missing.append(name)
            log(f"  transit compute failed for {name}: {e} — skipping")
    if transit_missing:
        log(f"  shipping without: {transit_missing}")

    aspects = transit_aspects(transits, natal, max_orb=6.0)

    scores, comps = score_dominance(today, transits, natal)
    dominant = max(scores, key=scores.get)
    label = DOMINANT_LABEL[dominant]

    opp, opp_why = score_opportunity(today, transits, natal, aspects)
    pre, pre_why = score_pressure(today, transits, natal, aspects)
    vol, vol_why = score_volatility(today, transits, natal, aspects)
    mom, mom_why = score_momentum(today, transits, natal, aspects)

    supporting = pick_supporting(today, transits, natal, aspects, dominant)
    pressure_src = pick_pressure(today, transits, natal, aspects, dominant)

    dur = duration_days(today, dominant, comps, transits, natal)

    texts = []
    for p in (TROPICAL_MD, VEDIC_MD, COUNCIL_MD):
        try:
            texts.append(open(p, encoding="utf-8").read())
        except Exception as e:
            log(f"  could not read {p}: {e}")
            texts.append("")
    conf = confidence_for(dominant, texts)
    acw = active_council_window_for(today)

    sources = [NATAL_MD, TROPICAL_MD, VEDIC_MD, COUNCIL_MD]

    state = {
        "generated_at": now.isoformat(timespec="seconds"),
        "current_date": today.isoformat(),
        "dominant_planet": dominant,
        "forecast_label": label,
        "supporting_planet": supporting,
        "pressure_source": pressure_src,
        "confidence": conf,
        "duration_days": dur,
        "weather_metrics": {
            "opportunity": opp, "pressure": pre, "volatility": vol, "momentum": mom,
        },
        "narrative": None,  # filled below
        "active_council_window": acw,
        "sources": [os.path.relpath(s, VAULT) for s in sources],
        # --- audit trail (extra; not part of the locked schema, aids sanity-check) ---
        "scoring_detail": {
            "dominance_scores": scores,
            "dominance_components": {k: {kk: (round(vv, 3) if isinstance(vv, float) else vv)
                                         for kk, vv in v.items()} for k, v in comps.items()},
            "lord_of_year": lord_of_year(today),
            "active_windows": [w["name"] for w in active_windows(today)],
            "metric_drivers": {"opportunity": opp_why, "pressure": pre_why,
                               "volatility": vol_why, "momentum": mom_why},
            "transit_longitudes": {k: round(v, 2) for k, v in transits.items()},
            "transit_signs": {k: f"{round(v % 30, 2)}° {sign_of(v)}" for k, v in transits.items()},
            "tight_aspects": sorted(aspects, key=lambda a: a["orb"])[:12],
            "transit_missing": transit_missing,
            "natal_missing": missing,
        },
    }
    state["narrative"] = codex_narrative(state)
    return state


def main():
    out_path = OUT_PATH
    if "--out" in sys.argv:
        i = sys.argv.index("--out")
        if i + 1 < len(sys.argv):
            out_path = sys.argv[i + 1]
    state = compute()
    with open(out_path, "w") as f:
        json.dump(state, f, indent=2)
    log(f"Timing Weather: {state['forecast_label']} (dominant={state['dominant_planet']}, "
        f"conf={state['confidence']}, dur={state['duration_days']}d) -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
