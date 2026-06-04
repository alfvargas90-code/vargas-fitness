#!/usr/bin/env python3
"""
Lunar Stress Index (LSI) — nervous-system compression / stress model.

A behavioral-calibration score (0-100, NOT a prediction). It fuses:
  - lunar transit activation against Alfie's natal chart (Swiss Ephemeris)
  - physiological strain from Polar (HRV / RHR / sleep / workout vs 7-day baseline)
into a single score + band, then asks `claude -p` for a 1-2 sentence behavioral
directive in a performance-based-male register (action, not feelings).

DIRECT-DATA REFRAME (2026-06-03): the score + band still compute internally (kept in
the JSON for trend math + Layer 3 daily logging), but they are NO LONGER the dashboard
surface. The card now renders a data-forward lunar readout: moon sign + degree, phase,
next sign change, void-of-course window (when active), and active major transits
(Mercury Rx, Saturn/Jupiter aspects to natal). See compute()'s `lunar` block.

Runs piggy-backed on the polar-sync 30-min cadence (sync.py calls this after a
successful pull). Writes polar/lunar_stress.json + a per-day archive
(polar/lunar_daily/<date>.json) for the future monthly pattern roll-up. The git push
is handled by sync.py's allowlisted git_push().

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
from datetime import datetime, timedelta, timezone
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

# Load bands — SINGLE SOURCE OF TRUTH for the Python side, mirrored exactly from the
# dashboard's app.js LOAD_BANDS. Interpret today's accumulated Polar active-calories
# (no training-session data is synced) into one band, so the Recovery tile, Activity
# card, LSI, and AI prompts (summary.py imports these) never contradict each other.
#   —/Light  -> "rest"      (no workout points)
#   Moderate -> "moderate"  (+3 points)
#   Heavy    -> "high"      (+10 on suppressed HRV, else +3)
LOAD_BANDS = [
    ("—",        0,   49),
    ("Light",    50,  399),
    ("Moderate", 400, 799),
    ("Heavy",    800, 10 ** 9),
]
BAND_INTENSITY = {"—": "rest", "Light": "rest", "Moderate": "moderate", "Heavy": "high"}


def load_band_for(active_cal):
    """Map active-calories -> band name (—/Light/Moderate/Heavy). None/non-numeric -> '—'."""
    c = active_cal if isinstance(active_cal, (int, float)) else 0
    for name, lo, hi in LOAD_BANDS:
        if lo <= c <= hi:
            return name
    return "—"

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


def goal_framing():
    """Soft secondary input for the LSI directive. The recommendation stays primarily
    about nervous-system compression — but when the system is regulated enough to
    train, this nudges the charge toward resistance work / protein rather than generic
    'do something'. Reads polar/goal_config.json; never raises; returns "" if absent."""
    try:
        cfg = load_json(os.path.join(HERE, "goal_config.json"))
        framing = cfg.get("framing", "").strip()
        if not framing:
            return ""
        return (
            "SECONDARY CONTEXT (soft — nervous-system regulation stays primary): his "
            "active goal is body recomp — build muscle while losing fat; protein is the "
            "load-bearing variable and resistance work matters more than cardio churn. "
            "If the state is regulated enough to train, you MAY point the charge toward "
            "resistance work or protein-loading rather than a generic 'produce'. If the "
            "state is compressed, ignore this entirely — regulation wins. Never name it "
            "as a 'goal' or 'recomp'; keep it a one-clause nudge, not a lecture.\n\n"
        )
    except Exception as e:
        log(f"  goal_config parse failed (non-fatal): {e}")
        return ""


def is_rest_day_today():
    """True if today is in polar/rest_days.json (Penny writes it from Alfie's chat).
    Never raises; returns False if the file is missing or unparseable."""
    from datetime import date as _date
    try:
        cfg = load_json(os.path.join(HERE, "rest_days.json"))
        return _date.today().isoformat() in (cfg.get("rest_days") or [])
    except Exception as e:
        log(f"  rest_days parse failed (non-fatal): {e}")
        return False


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


# --- data-forward lunar readout (Layer 2) --------------------------------
SIGN_ABBR = {"Aries": "Ari", "Taurus": "Tau", "Gemini": "Gem", "Cancer": "Can",
             "Leo": "Leo", "Virgo": "Vir", "Libra": "Lib", "Scorpio": "Sco",
             "Sagittarius": "Sag", "Capricorn": "Cap", "Aquarius": "Aqu", "Pisces": "Pis"}

# Bodies + aspects used for void-of-course (Moon makes no further aspect before ingress).
VOC_BODIES = [swe.SUN, swe.MERCURY, swe.VENUS, swe.MARS, swe.JUPITER,
              swe.SATURN, swe.URANUS, swe.NEPTUNE, swe.PLUTO]
VOC_ASPECTS = [0, 60, 90, 120, 180]
TRANSIT_ORB = 1.5   # orb for slow-planet (Saturn/Jupiter) aspects to natal points


def format_moon_degree(moon_lon):
    """'23° Cap 36'' — whole degree + arcminute WITHIN the current sign."""
    pos = moon_lon % 30
    d = int(pos)
    m = int(round((pos - d) * 60))
    if m == 60:
        d, m = d + 1, 0
    return f"{d}° {SIGN_ABBR[sign_of(moon_lon)]} {m:02d}'"


def fmt_time(dt):
    """6:45 PM — local 12-hour clock, no leading zero, no platform strftime flags."""
    h = dt.hour % 12 or 12
    return f"{h}:{dt.minute:02d} {'AM' if dt.hour < 12 else 'PM'}"


def jd_to_local(jd):
    """Julian Day (UT) -> timezone-aware local datetime."""
    y, mo, d, ut = swe.revjul(jd)
    base = datetime(y, mo, d, tzinfo=timezone.utc) + timedelta(hours=ut)
    return base.astimezone()


def next_sign_change(jd, moon_lon):
    """When the Moon crosses into the next sign. Bisects the sign-index change over the
    next 3 days (Moon changes sign at most ~every 2.3 days). Returns
    (next_sign_name, local_datetime, ingress_jd)."""
    cur = int(moon_lon // 30) % 12
    nxt = (cur + 1) % 12
    lo, hi = jd, jd + 3.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if int(lon_of(mid, swe.MOON) // 30) % 12 == cur:
            lo = mid
        else:
            hi = mid
    return SIGNS[nxt], jd_to_local(hi), hi


def _aspect_signature(jd):
    """Snapshot of (sep - aspect_angle) for every Moon↔planet aspect pair at `jd`."""
    ml = lon_of(jd, swe.MOON)
    sig = {}
    for body in VOC_BODIES:
        try:
            sep = angular_sep(ml, lon_of(jd, body))
        except Exception:
            continue
        for asp in VOC_ASPECTS:
            sig[(body, asp)] = sep - asp
    return sig


def has_upcoming_aspect(jd_start, jd_end):
    """True if the Moon perfects any major aspect to a planet between start and end —
    detected as a zero-crossing of (sep - aspect_angle) on a ~28-min step grid."""
    steps = max(8, int((jd_end - jd_start) / 0.02))
    prev = None
    for i in range(steps + 1):
        j = jd_start + (jd_end - jd_start) * i / steps
        cur = _aspect_signature(j)
        if prev is not None:
            for k, v in cur.items():
                pv = prev.get(k)
                if pv is None:
                    continue
                if pv == 0 or (pv < 0) != (v < 0):
                    return True
        prev = cur
    return False


def compute_voc(jd, ingress_jd, ingress_dt):
    """Moon is void-of-course when it makes NO further major aspect before the next
    ingress. Returns a dict when active now, else None."""
    if has_upcoming_aspect(jd, ingress_jd):
        return None
    return {"active": True, "until": ingress_dt.isoformat(timespec="minutes"),
            "until_display": f"{ingress_dt.month}/{ingress_dt.day} at {fmt_time(ingress_dt)}"}


def mercury_retrograde(jd):
    """'Mercury retrograde (until M/D)' if Mercury is currently Rx (negative longitude
    speed), else None. Forward-scans daily up to 45 days for the direct station."""
    try:
        if swe.calc_ut(jd, swe.MERCURY)[0][3] >= 0:
            return None
    except Exception:
        return None
    for day in range(1, 46):
        try:
            if swe.calc_ut(jd + day, swe.MERCURY)[0][3] >= 0:
                end = jd_to_local(jd + day)
                return f"Mercury retrograde (until {end.month}/{end.day})"
        except Exception:
            break
    return "Mercury retrograde"


def outer_aspects_to_natal(jd, natal_moon, natal_uranus):
    """Saturn/Jupiter major aspects to natal Moon/Uranus within TRANSIT_ORB. Plain
    strings like 'Saturn square natal Moon'. The slow-mover transits worth surfacing."""
    out = []
    targets = [(natal_moon, "Moon"), (natal_uranus, "Uranus")]
    for body, pname in ((swe.SATURN, "Saturn"), (swe.JUPITER, "Jupiter")):
        try:
            bl = lon_of(jd, body)
        except Exception:
            continue
        for nat_lon, nat_name in targets:
            sep = angular_sep(bl, nat_lon)
            for aname, exact in ASPECTS.items():
                if abs(sep - exact) <= TRANSIT_ORB:
                    out.append(f"{pname} {aname} natal {nat_name}")
                    break
    return out


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
    """'high' / 'moderate' / 'rest', derived from today's Polar active-calories band
    (proxy — no training-session data is synced). Returns ('rest', None) if no file."""
    from datetime import date as _date
    path = os.path.join(HERE, "daily_activity", f"{_date.today().isoformat()}.json")
    try:
        act = load_json(path)
        ac = act.get("active-calories")
        return BAND_INTENSITY[load_band_for(ac)], ac
    except Exception:
        return "rest", None


def band_for(score):
    for lo, hi, name in BANDS:
        if lo <= score <= hi:
            return name
    return "Stable Control"


# Micro-bar normalization: relative weight of each contribution to the band.
# Realistic upper bounds, not theoretical maxima.
TRANSIT_MAX = 55   # Moon conj natal Moon (+30) + Cap (+10) + Full Moon (+10) + 12th house (+5)
BODY_MAX = 40      # HRV +10, RHR +10, Sleep +10, Workout +10


def compute_bars(transit_pts, body_pts):
    """10-segment fill for each contribution. Negative net points clamp to 0
    (a regulating overlay reads as 'unloaded', not negative-length)."""
    def seg(pts, mx):
        return max(0, min(10, round(pts / mx * 10)))
    return {
        "transit": {"filled": seg(transit_pts, TRANSIT_MAX), "total": 10,
                    "points": transit_pts, "max": TRANSIT_MAX},
        "body": {"filled": seg(body_pts, BODY_MAX), "total": 10,
                 "points": body_pts, "max": BODY_MAX},
    }


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

    # Workout (band-derived): high + low HRV -> +10; high + normal HRV -> +3;
    # moderate -> +3; rest (—/Light) -> 0.
    hrv_low = hrv_pct is not None and hrv_pct <= -5
    if intensity == "high":
        if hrv_low:
            pts += 10; breakdown.append(("+10", "High-intensity day on suppressed HRV"))
        else:
            pts += 3; breakdown.append(("+3", "High-intensity day, HRV normal"))
    elif intensity == "moderate":
        pts += 3; breakdown.append(("+3", "Moderate-intensity day"))

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


# Absolute-avoidance phrasing the recommendation must never contain — calibration,
# not avoidance programming. If claude emits any of these, we drop to the fallback.
BANNED_ABSOLUTES = re.compile(
    r"\b(delay every|always|never|skip all|postpone all|avoid \w+ today)\b", re.I)


def has_absolutes(text):
    return bool(BANNED_ABSOLUTES.search(text or ""))


BAND_GUIDANCE = {
    "Stable Control": "system is regulated — green light to load up and produce hard.",
    "Mild Compression": "slight load building — proceed, just keep output structured.",
    "Moderate Compression": "real compression — route it into structured work; initiate confrontation selectively, respond only if necessary.",
    "Elevated Reactivity": "reactivity is up — calibrate before big decisions; if a call must be made, make it deliberately rather than on impulse.",
    "High Nervous Load": "system is overloaded — strip the day to essentials; weigh any escalation against the data before acting.",
}


def build_recommendation(score, band, trigger, physiology, intensity, rest_day=False):
    guidance = BAND_GUIDANCE.get(band, "")
    rhr_d = physiology["rhr_delta_bpm"]
    rest_block = (
        "REST DAY (overrides the training nudge): today is an explicit rest day the "
        "user declared. Point the charge toward protein-loading and structured recovery "
        "work (mobility, hydration, an early night) — NOT 'lift heavy' or hard output. "
        "Still calibration, not avoidance: recover deliberately, don't collapse.\n\n"
        if rest_day else ""
    )
    prompt = (
        "Write a nervous-system regulation directive for a high-output, performance-based "
        "man. He PRODUCES; he does not process feelings.\n\n"
        "OUTPUT: exactly 1-2 short sentences. Start with an action verb (Load, Hold, "
        "Channel, Route, Calibrate, Strip...). Output ONLY the directive — nothing else.\n\n"
        "TONE: ENGINEER, not therapist. He calibrates instinct against data; he does NOT "
        "need protection from his own impulses. This is calibration, not avoidance programming.\n\n"
        "HARD RULES:\n"
        "- Do NOT restate the score, band, or numbers. Do NOT preface with 'Directive:' or similar.\n"
        "- No feelings-talk ('be gentle with yourself', 'honor your emotions', 'recharge emotionally').\n"
        "- No symbolic/astrological/outcome language ('the moon', 'energy', 'the universe', predictions).\n"
        "- No hype, no soft phrasing. Behavioral instruction only — what to DO with the day.\n"
        "- NO ABSOLUTE AVOIDANCE LANGUAGE. Never write 'delay every', 'always', 'never', "
        "'skip all', 'postpone all', or 'avoid X today'. These program avoidance, not calibration.\n"
        "- PREFER calibrated phrasing: 'respond only if necessary', 'initiate selectively', "
        "'calibrate before deciding', 'if the call must be made'. Gate action on judgment, "
        "not a blanket ban.\n\n"
        f"{goal_framing()}"
        f"{rest_block}"
        f"Internal context (do not echo): state is '{band}' — {guidance} "
        f"Trigger: {trigger}. HRV {physiology['hrv_pct_baseline']}% vs baseline, "
        f"RHR {rhr_d:+d} bpm, sleep {physiology['sleep_score']}, "
        f"workout {intensity}.\n"
    )
    try:
        rec = clean(call_claude(prompt))
        if rec and has_absolutes(rec):
            log("  claude recommendation used absolute language — dropping to calibrated fallback")
            rec = ""
        # Guard against a runaway response — keep it tight (drop any echoed score).
        if rec and len(rec) <= 280:
            return rec
        if rec:
            return rec[:280].rsplit(".", 1)[0] + "."
    except Exception as e:
        log(f"  claude recommendation failed (non-fatal): {e}")
    # Deterministic fallback in the same register. On a rest day, recovery-frame it
    # regardless of band so the fallback never says "push output hard".
    if rest_day:
        return ("Rest day: load protein and run structured recovery — hydration, easy "
                "mobility, an early night. Recover deliberately, don't collapse.")
    return {
        "Stable Control": "System's regulated. Load up and push output hard today.",
        "Mild Compression": "Keep the day structured and move work forward; no need to back off.",
        "Moderate Compression": "Channel it into structured, pre-planned work — let the day's hardest task absorb the load. Initiate confrontation selectively; respond only if necessary.",
        "Elevated Reactivity": "Route the charge into routine execution. Calibrate before any big decision; if the call must be made, make it deliberately.",
        "High Nervous Load": "Strip the day to essentials and protect output. Weigh any escalation against the data before acting, and reset tonight.",
    }.get(band, "Keep the day structured and calibrate before escalating.")


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
    rest_today = is_rest_day_today()
    if rest_today and intensity != "rest":
        # Explicit rest day: high active-calories are accumulated daily movement, not
        # training load. Force 'rest' so it neither adds nervous-system load points nor
        # reads as a workout in the directive.
        log(f"  rest day declared — forcing workout_intensity rest (was {intensity}, "
            f"active-cal {active_cal})")
        intensity = "rest"

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
        score, band, trigger, physiology, intensity, rest_day=rest_today)

    # --- Layer 2: data-forward lunar readout (the new dashboard surface) ---
    next_sign, next_dt, ingress_jd = next_sign_change(jd, moon_lon)
    voc = compute_voc(jd, ingress_jd, next_dt)
    active_transits = []
    merc = mercury_retrograde(jd)
    if merc:
        active_transits.append(merc)
    active_transits += outer_aspects_to_natal(jd, natal_moon, natal_uranus)
    lunar = {
        "sign": sign_of(moon_lon),
        "degree": format_moon_degree(moon_lon),
        "phase": moon_phase(elongation),
        "next_sign_change": {
            "sign": next_sign,
            "at": next_dt.isoformat(timespec="minutes"),
            "display": f"Enters {next_sign} {next_dt.month}/{next_dt.day} at {fmt_time(next_dt)}",
        },
        "void_of_course": voc,
        "active_transits": active_transits,
    }

    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "score": score,
        "band": band,
        "trigger": trigger,
        "physiology": physiology,
        "workout_intensity": intensity,
        "recommendation": recommendation,
        "lunar": lunar,
        "bars": compute_bars(a_pts, b_pts),
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


def write_daily_log(data):
    """Layer 3: append today's lunar state to polar/lunar_daily/<date>.json so the
    monthly pattern roll-up (WHEN_HOME #10) can correlate moon phase/sign/transits
    against daily physiology later. Overwrites only TODAY's file each run (latest
    state); past days are immutable, so the directory accumulates a daily history.
    Never raises."""
    try:
        from datetime import date as _date
        lunar = data.get("lunar", {}) or {}
        today = _date.today().isoformat()
        rec = {
            "date": today,
            "moon_sign": lunar.get("sign"),
            "moon_degree": lunar.get("degree"),
            "moon_phase": lunar.get("phase"),
            "active_major_transits": lunar.get("active_transits", []),
            "score": data.get("score"),
        }
        folder = os.path.join(HERE, "lunar_daily")
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, f"{today}.json"), "w") as f:
            json.dump(rec, f, indent=2)
    except Exception as e:
        log(f"  lunar_daily log failed (non-fatal): {e}")


def main():
    out_path = OUT_PATH
    testing = "--out" in sys.argv
    if testing:
        i = sys.argv.index("--out")
        if i + 1 < len(sys.argv):
            out_path = sys.argv[i + 1]
    data = compute()
    with open(out_path, "w") as f:
        json.dump(data, f, indent=2)
    # Daily pattern log only on the real run (skip during --out manual tests).
    if not testing:
        write_daily_log(data)
    log(f"LSI {data['score']} ({data['band']}) — {data['trigger']} -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
