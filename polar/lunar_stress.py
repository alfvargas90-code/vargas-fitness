#!/usr/bin/env python3
"""
Lunar Stress Index (LSI) — nervous-system compression / stress model.

A behavioral-calibration score (0-100, NOT a prediction). It fuses:
  - lunar transit activation against Alfie's natal chart (Swiss Ephemeris)
  - physiological strain from Polar (HRV / RHR / sleep / workout vs 7-day baseline)
into a single score + band, then asks `claude -p` for a 1-2 sentence behavioral
directive in a performance-based-male register (action, not feelings).

Runs piggy-backed on the polar-sync 30-min cadence (sync.py calls this after a
successful pull). Writes polar/lunar_stress.json; the dashboard renders it under
"Today's Read". The git push is handled by sync.py's allowlisted git_push().

Deps (in polar/.venv): pyswisseph. No network at runtime.

Natal references (locked):
  Moon   5deg31' Capricorn  -> 275deg31' absolute longitude
  Uranus 5deg41' Capricorn  -> 275deg41'
  Birth  Aug 30 1990, 4:22 PM CDT, Chicago IL (41.85N, -87.65W)
  Orb    1deg strict   House system  Placidus
"""
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from statistics import mean

import swisseph as swe

# --- paths ---------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))      # .../fitness-dashboard/polar
ROOT = os.path.dirname(HERE)                            # .../fitness-dashboard
OUT_PATH = os.path.join(HERE, "lunar_stress.json")

# --- natal chart (computed once per run from birth constants) ------------
# Birth in UT: 16:22 CDT (UTC-5) -> 21:22 UT on 1990-08-30.
BIRTH = (1990, 8, 30, 21 + 22 / 60.0)
BIRTH_LAT, BIRTH_LON = 41.85, -87.65
ORB = 1.0                       # strict aspect orb, degrees
FULL_MOON_ORB = 1.0             # Sun-Moon opposition orb for the +10 Full Moon point

# Workout intensity is derived from Polar daily active-calories (no training-session
# data is synced). Active calories at/above this are treated as a "high" day.
WORKOUT_HIGH_ACTIVE_CAL = 600

SIGNS = ["Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
         "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"]

# Major aspects: name -> exact angle.
ASPECTS = {"conjunction": 0, "sextile": 60, "square": 90, "trine": 120, "opposition": 180}

BANDS = [
    (0, 25, "Stable Control"),
    (26, 45, "Mild Compression"),
    (46, 65, "Moderate Compression"),
    (66, 85, "Elevated Reactivity"),
    (86, 100, "High Nervous Load"),
]


def log(msg):
    print(msg, flush=True)


def load_json(path):
    with open(path) as f:
        return json.load(f)


# --- astronomy helpers ---------------------------------------------------
def jd_now(now_utc):
    return swe.julday(now_utc.year, now_utc.month, now_utc.day,
                      now_utc.hour + now_utc.minute / 60.0 + now_utc.second / 3600.0)


def lon_of(jd, body):
    return swe.calc_ut(jd, body)[0][0]


def sign_of(lon):
    return SIGNS[int(lon // 30) % 12]


def angular_sep(a, b):
    """Smallest separation between two longitudes, 0-180."""
    return abs(((a - b + 180) % 360) - 180)


def match_aspect(moon_lon, natal_lon, orb=ORB):
    """Return (aspect_name, signed_offset) of the closest major aspect within orb,
    or (None, None). signed_offset = sep - exact (negative = applying side)."""
    sep = angular_sep(moon_lon, natal_lon)
    best = None
    for name, exact in ASPECTS.items():
        delta = sep - exact
        if abs(delta) <= orb and (best is None or abs(delta) < abs(best[1])):
            best = (name, delta)
    return best if best else (None, None)


def natal_house(moon_lon, cusps):
    """Which natal Placidus house contains moon_lon (1-12). cusps[i] starts house i+1."""
    for h in range(12):
        start = cusps[h]
        end = cusps[(h + 1) % 12]
        span = (end - start) % 360
        if (moon_lon - start) % 360 < span:
            return h + 1
    return None


def moon_phase(elong):
    """Phase name from Moon-Sun elongation (0-360). Principal phases (New/First
    Quarter/Full/Last Quarter) only within ~6deg of exact; the rest fill the
    crescent/gibbous ranges — closer to how moon apps label than wide 45deg bins."""
    if elong < 6 or elong > 354:
        return "New"
    if elong < 84:
        return "Waxing Crescent"
    if elong < 96:
        return "First Quarter"
    if elong < 174:
        return "Waxing Gibbous"
    if elong < 186:
        return "Full"
    if elong < 264:
        return "Waning Gibbous"
    if elong < 276:
        return "Last Quarter"
    return "Waning Crescent"


def applying_or_separating(jd, body, natal_lon, exact_angle):
    """Is the body's aspect to natal_lon applying (tightening) or separating?"""
    off0 = abs(angular_sep(lon_of(jd, body), natal_lon) - exact_angle)
    off1 = abs(angular_sep(lon_of(jd + 0.02, body), natal_lon) - exact_angle)
    return "applying" if off1 < off0 else "separating"


# --- physiology helpers --------------------------------------------------
def manifest_dates(cat):
    try:
        m = load_json(os.path.join(HERE, "manifest.json"))
        return sorted(m.get("categories", {}).get(cat, []))
    except Exception:
        return []


def rolling_mean(dates, folder, key, n=7):
    vals = []
    for d in reversed(dates):                 # newest first
        try:
            v = load_json(os.path.join(HERE, folder, f"{d}.json")).get(key)
        except Exception:
            v = None
        if v is not None:
            vals.append(v)
        if len(vals) >= n:
            break
    return mean(vals) if vals else None


def load_latest(folder, dates):
    return load_json(os.path.join(HERE, folder, f"{dates[-1]}.json")) if dates else {}


def workout_intensity_today():
    """'high' or 'rest', derived from today's Polar active-calories (proxy — no
    training-session data is synced). Returns 'rest' if no file."""
    from datetime import date as _date
    path = os.path.join(HERE, "daily_activity", f"{_date.today().isoformat()}.json")
    try:
        act = load_json(path)
        ac = act.get("active-calories")
        if ac is not None and ac >= WORKOUT_HIGH_ACTIVE_CAL:
            return "high", ac
        return "rest", ac
    except Exception:
        return "rest", None


def band_for(score):
    for lo, hi, name in BANDS:
        if lo <= score <= hi:
            return name
    return "Stable Control"


# --- scoring -------------------------------------------------------------
def score_transits(moon_lon, sun_lon, natal_moon, natal_uranus, house, jd):
    """Part A — lunar transit activation. Returns (points, breakdown list, trigger,
    aspect_to_natal_moon string, is_full_moon)."""
    pts = 0
    breakdown = []
    # (weight, label) candidates for the headline trigger, highest weight wins.
    trigger_candidates = []

    asp_moon, off_moon = match_aspect(moon_lon, natal_moon)
    asp_ura, off_ura = match_aspect(moon_lon, natal_uranus)

    conj_moon = asp_moon == "conjunction"
    aspect_to_natal_moon = None

    if asp_moon:
        state = applying_or_separating(jd, swe.MOON, natal_moon, ASPECTS[asp_moon])
        aspect_to_natal_moon = f"{asp_moon} ({abs(off_moon):.1f}° {state})"

    # Conjunctions collapse Uranus into the same event (no double count).
    if conj_moon:
        pts += 30
        breakdown.append(("+30", "Moon conjunct natal Moon (Uranus collapsed)"))
        trigger_candidates.append((30, "Moon conjunct natal Moon"))
    elif asp_moon == "square":
        pts += 20
        breakdown.append(("+20", "Moon square natal Moon"))
        trigger_candidates.append((20, "Moon square natal Moon"))
    elif asp_moon == "opposition":
        pts += 15
        breakdown.append(("+15", "Moon opposite natal Moon"))
        trigger_candidates.append((15, "Moon opposite natal Moon"))
    elif asp_moon == "trine":
        pts -= 15
        breakdown.append(("-15", "Moon trine natal Moon"))
    elif asp_moon == "sextile":
        pts -= 10
        breakdown.append(("-10", "Moon sextile natal Moon"))

    # Uranus conjunction only counts if NOT already conjunct natal Moon.
    if asp_ura == "conjunction" and not conj_moon:
        pts += 15
        breakdown.append(("+15", "Moon conjunct natal Uranus"))
        trigger_candidates.append((15, "Moon conjunct natal Uranus"))

    if sign_of(moon_lon) == "Capricorn":
        pts += 10
        breakdown.append(("+10", "Moon in Capricorn"))
        trigger_candidates.append((10, "Moon in Capricorn"))

    elongation = (moon_lon - sun_lon) % 360
    is_full = abs(elongation - 180) <= FULL_MOON_ORB
    if is_full:
        pts += 10
        breakdown.append(("+10", "Full Moon"))
        trigger_candidates.append((10, "Full Moon"))

    if house == 12:
        pts += 5
        breakdown.append(("+5", "Moon transiting natal 12th house"))
        trigger_candidates.append((5, "Moon in natal 12th house"))

    trigger = max(trigger_candidates, key=lambda x: x[0])[1] if trigger_candidates else "No active lunar trigger"
    return pts, breakdown, trigger, aspect_to_natal_moon, is_full


def score_physiology(hrv, hrv_base, rhr, rhr_base, sleep_score, intensity):
    """Part B — physiological overlay. Returns (points, breakdown, hrv_pct, rhr_delta)."""
    pts = 0
    breakdown = []

    hrv_pct = None
    if hrv is not None and hrv_base:
        hrv_pct = (hrv - hrv_base) / hrv_base * 100
        if hrv_pct <= -10:
            pts += 10; breakdown.append(("+10", f"HRV {hrv_pct:.0f}% below baseline"))
        elif hrv_pct <= -5:
            pts += 5; breakdown.append(("+5", f"HRV {hrv_pct:.0f}% below baseline"))
        elif hrv_pct >= 5:
            pts -= 5; breakdown.append(("-5", f"HRV {hrv_pct:.0f}% above baseline"))

    rhr_delta = None
    if rhr is not None and rhr_base:
        rhr_delta = rhr - rhr_base
        if rhr_delta >= 5:
            pts += 10; breakdown.append(("+10", f"RHR +{rhr_delta:.0f} bpm vs baseline"))
        elif rhr_delta >= 2:
            pts += 5; breakdown.append(("+5", f"RHR +{rhr_delta:.0f} bpm vs baseline"))
        elif rhr_delta <= -2:
            pts -= 5; breakdown.append(("-5", f"RHR {rhr_delta:.0f} bpm vs baseline"))

    if sleep_score is not None:
        if sleep_score < 70:
            pts += 10; breakdown.append(("+10", f"Sleep score {sleep_score} (<70)"))
        elif sleep_score < 80:
            pts += 5; breakdown.append(("+5", f"Sleep score {sleep_score} (70-80)"))
        elif sleep_score > 90:
            pts -= 5; breakdown.append(("-5", f"Sleep score {sleep_score} (>90)"))

    # Workout: high + low HRV -> +10; high + normal HRV -> +3; rest -> 0.
    hrv_low = hrv_pct is not None and hrv_pct <= -5
    if intensity == "high":
        if hrv_low:
            pts += 10; breakdown.append(("+10", "High-intensity day on suppressed HRV"))
        else:
            pts += 3; breakdown.append(("+3", "High-intensity day, HRV normal"))

    return pts, breakdown, hrv_pct, rhr_delta


# --- recommendation (claude -p) ------------------------------------------
def call_claude(prompt):
    claude = shutil.which("claude") or "/Users/alfredovargas/.local/bin/claude"
    out = subprocess.run([claude, "-p", prompt], capture_output=True, text=True,
                         timeout=180, cwd=ROOT)
    if out.returncode != 0:
        raise RuntimeError(f"claude exited {out.returncode}: {out.stderr.strip()[:300]}")
    return out.stdout


def clean(text):
    text = re.sub(r"[*_`#>]", "", text)
    return re.sub(r"\s+", " ", text).strip()


BAND_GUIDANCE = {
    "Stable Control": "system is regulated — green light to load up and produce hard.",
    "Mild Compression": "slight load building — proceed, just keep output structured.",
    "Moderate Compression": "real compression — channel it into structured work, delay any confrontation.",
    "Elevated Reactivity": "reactivity is up — hold the line, no big decisions or escalations today.",
    "High Nervous Load": "system is overloaded — de-escalate hard, strip the day to essentials, no confrontation.",
}


def build_recommendation(score, band, trigger, physiology, intensity):
    guidance = BAND_GUIDANCE.get(band, "")
    rhr_d = physiology["rhr_delta_bpm"]
    prompt = (
        "Write a nervous-system regulation directive for a high-output, performance-based "
        "man. He PRODUCES; he does not process feelings.\n\n"
        "OUTPUT: exactly 1-2 short sentences. Start with an action verb (Load, Hold, "
        "Channel, Delay, De-escalate, Strip...). Output ONLY the directive — nothing else.\n\n"
        "HARD RULES:\n"
        "- Do NOT restate the score, band, or numbers. Do NOT preface with 'Directive:' or similar.\n"
        "- No feelings-talk ('be gentle with yourself', 'honor your emotions', 'recharge emotionally').\n"
        "- No symbolic/astrological/outcome language ('the moon', 'energy', 'the universe', predictions).\n"
        "- No hype, no soft phrasing. Behavioral instruction only — what to DO with the day.\n\n"
        f"Internal context (do not echo): state is '{band}' — {guidance} "
        f"Trigger: {trigger}. HRV {physiology['hrv_pct_baseline']}% vs baseline, "
        f"RHR {rhr_d:+d} bpm, sleep {physiology['sleep_score']}, "
        f"workout {intensity}.\n"
    )
    try:
        rec = clean(call_claude(prompt))
        # Guard against a runaway response — keep it tight (drop any echoed score).
        if rec and len(rec) <= 280:
            return rec
        if rec:
            return rec[:280].rsplit(".", 1)[0] + "."
    except Exception as e:
        log(f"  claude recommendation failed (non-fatal): {e}")
    # Deterministic fallback in the same register.
    return {
        "Stable Control": "System's regulated. Load up and push output hard today.",
        "Mild Compression": "Keep the day structured and move work forward; no need to back off.",
        "Moderate Compression": "Avoid escalation. Channel energy into structured output and delay any strategic confrontation.",
        "Elevated Reactivity": "Hold the line. No big decisions or confrontations today — route the charge into routine execution.",
        "High Nervous Load": "De-escalate and strip the day to essentials. No confrontation, no major decisions — protect output and reset tonight.",
    }.get(band, "Keep the day structured and avoid escalation.")


# --- main ----------------------------------------------------------------
def compute(now=None):
    now = now or datetime.now().astimezone()
    now_utc = now.astimezone(timezone.utc)

    # Natal chart (once per run).
    jd_natal = swe.julday(*BIRTH)
    natal_moon = lon_of(jd_natal, swe.MOON)
    natal_uranus = lon_of(jd_natal, swe.URANUS)
    natal_cusps, _ = swe.houses(jd_natal, BIRTH_LAT, BIRTH_LON, b'P')

    # Current Moon / Sun.
    jd = jd_now(now_utc)
    moon_lon = lon_of(jd, swe.MOON)
    sun_lon = lon_of(jd, swe.SUN)
    house = natal_house(moon_lon, natal_cusps)
    elongation = (moon_lon - sun_lon) % 360

    a_pts, a_break, trigger, aspect_str, is_full = score_transits(
        moon_lon, sun_lon, natal_moon, natal_uranus, house, jd)

    # Physiology inputs.
    rec_dates = manifest_dates("recharge")
    slp_dates = manifest_dates("sleep")
    rec = load_latest("recharge", rec_dates)
    slp = load_latest("sleep", slp_dates)
    hrv = rec.get("heart_rate_variability_avg")
    rhr = rec.get("heart_rate_avg")
    sleep_score = slp.get("sleep_score")
    hrv_base = rolling_mean(rec_dates, "recharge", "heart_rate_variability_avg")
    rhr_base = rolling_mean(rec_dates, "recharge", "heart_rate_avg")
    intensity, active_cal = workout_intensity_today()

    b_pts, b_break, hrv_pct, rhr_delta = score_physiology(
        hrv, hrv_base, rhr, rhr_base, sleep_score, intensity)

    raw = a_pts + b_pts
    score = max(0, min(100, raw))
    band = band_for(score)

    physiology = {
        "hrv_pct_baseline": round(hrv_pct) if hrv_pct is not None else None,
        "rhr_delta_bpm": round(rhr_delta) if rhr_delta is not None else None,
        "sleep_score": sleep_score,
    }

    recommendation = build_recommendation(
        score, band, trigger, physiology, intensity)

    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "score": score,
        "band": band,
        "trigger": trigger,
        "physiology": physiology,
        "workout_intensity": intensity,
        "recommendation": recommendation,
        "transit_detail": {
            "moon_longitude": round(moon_lon, 2),
            "moon_sign": sign_of(moon_lon),
            "moon_phase": moon_phase(elongation),
            "moon_house_natal": house,
            "aspect_to_natal_moon": aspect_str,
            "is_full_moon": is_full,
        },
        "scoring_detail": {
            "raw_score": raw,
            "transit_points": a_pts,
            "physiology_points": b_pts,
            "breakdown": [f"{w} {label}" for w, label in (a_break + b_break)],
            "baselines": {
                "hrv_7d": round(hrv_base, 1) if hrv_base else None,
                "rhr_7d": round(rhr_base, 1) if rhr_base else None,
            },
            "active_calories": active_cal,
            "natal": {"moon_lon": round(natal_moon, 3), "uranus_lon": round(natal_uranus, 3)},
        },
    }


def main():
    out_path = OUT_PATH
    if "--out" in sys.argv:
        i = sys.argv.index("--out")
        if i + 1 < len(sys.argv):
            out_path = sys.argv[i + 1]
    data = compute()
    with open(out_path, "w") as f:
        json.dump(data, f, indent=2)
    log(f"LSI {data['score']} ({data['band']}) — {data['trigger']} -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
