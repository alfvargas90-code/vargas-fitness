#!/usr/bin/env python3
"""Pattern Engine v1 — Lunar Phase Correlations.

The lunar-phase slice of Phase 3 (Correlation Engine) from the locked North Star.
For each historical day we know the Moon phase (computed directly from the date —
no ephemeris, no lunar_daily files needed) and Alfie's sleep / recovery / strain.
We bucket every day by its Moon phase, average each metric per phase, and express
the per-phase average as a DELTA vs his overall average across all days.

Output: polar/patterns.json — current phase + per-phase deltas + overall averages.
Runs cheaply (read N small JSON files, compute, write one tiny JSON). No AI calls.

Honest by design: with ~2 weeks of data each phase bucket holds only a couple of
days, so deltas are noisy. We always surface the real sample size; phases with
< MIN_SAMPLE days report no deltas. The card-side caveat handles the thin-data UX.
"""
import glob
import json
import os
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))

# The 8 traditional phases, in synodic order starting from New Moon.
PHASES = [
    "New Moon", "Waxing Crescent", "First Quarter", "Waxing Gibbous",
    "Full Moon", "Waning Gibbous", "Last Quarter", "Waning Crescent",
]

SYNODIC = 29.53058867          # mean synodic month, days
# Reference new moon: 2000-01-06 18:14 UTC (JD 2451550.1) — standard epoch used by
# the common "moon age from Julian day" formula.
REF_NEW_MOON_JD = 2451550.1

MIN_SAMPLE = 3                 # below this, a phase bucket reports deltas as None


# --- moon phase from date ------------------------------------------------
def _julian_day(year, month, day, hour=12.0):
    """Gregorian calendar date -> Julian Day (UT). Fliegel-Van Flandern."""
    if month <= 2:
        year -= 1
        month += 12
    a = year // 100
    b = 2 - a + a // 4
    jd = (int(365.25 * (year + 4716)) + int(30.6001 * (month + 1))
          + day + b - 1524.5)
    return jd + hour / 24.0


def moon_phase(date_iso):
    """Phase name for a YYYY-MM-DD date, computed straight from the date.

    Moon age = days since the reference new moon, modulo the synodic month. We map
    age -> one of 8 buckets, each centered on its principal point (so the New Moon
    bucket straddles the wrap, Full Moon is centered on age ~14.77, etc.), matching
    how moon apps label days rather than naive 0-3.7 day slices."""
    y, m, d = (int(x) for x in date_iso.split("-"))
    jd = _julian_day(y, m, d)                      # local noon ~ midday of the day
    age = (jd - REF_NEW_MOON_JD) % SYNODIC
    frac = age / SYNODIC                           # 0..1 through the cycle
    idx = int(frac * 8 + 0.5) % 8                  # round to nearest of 8 centers
    return PHASES[idx]


# --- metric extractors (mirror summary.py's definitions) -----------------
def _load(path):
    with open(path) as f:
        return json.load(f)


def sleep_hours(slp):
    """Sleep span start->end (hours); fall back to summed stages."""
    try:
        s = datetime.fromisoformat(slp["sleep_start_time"])
        e = datetime.fromisoformat(slp["sleep_end_time"])
        h = (e - s).total_seconds() / 3600
        if h > 0:
            return round(h, 1)
    except Exception:
        pass
    secs = sum(slp.get(k, 0) or 0 for k in ("light_sleep", "deep_sleep", "rem_sleep"))
    return round(secs / 3600, 1) if secs else None


def recovery_pct(rec):
    """Nightly Recharge ans_charge_status (1-6) normalized to 0-100. The delta math
    is scale-invariant, but 0-100 reads naturally in the overall-average payload."""
    s = rec.get("ans_charge_status")
    return round(s / 6 * 100) if s is not None else None


def strain_kcal(act):
    """Active calories as a strain / training-load proxy (no session data is synced)."""
    return act.get("active-calories")


# --- aggregation ---------------------------------------------------------
def _dates_in(folder):
    out = []
    for p in sorted(glob.glob(os.path.join(HERE, folder, "*.json"))):
        name = os.path.basename(p)[:-5]           # strip .json
        if len(name) == 10 and name[4] == "-":    # YYYY-MM-DD only
            out.append((name, p))
    return out


def _collect(folder, extractor):
    """-> {date: value} for every readable file with a non-None metric.

    Reads the live ``<folder>/*.json`` files AND the backfilled
    ``<folder>/historical/*.json`` files (written by parse_history_export.py),
    deduping by date with LIVE taking precedence. So overlapping nights count
    once, and a date the live sync already owns is never overwritten by the
    coarser history-export version. If the historical folder is absent the
    behaviour is identical to before — the engine degrades gracefully."""
    out = {}
    # Historical first, then live overwrites any shared date (live precedence).
    for src in (os.path.join(folder, "historical"), folder):
        for date_iso, path in _dates_in(src):
            try:
                v = extractor(_load(path))
            except Exception:
                v = None
            if v is not None:
                out[date_iso] = v
    return out


def _mean(vals):
    return sum(vals) / len(vals) if vals else None


def build():
    sleep = _collect("sleep", sleep_hours)
    recovery = _collect("recharge", recovery_pct)
    strain = _collect("daily_activity", strain_kcal)

    overall = {
        "sleep_h": _mean(list(sleep.values())),
        "recovery": _mean(list(recovery.values())),
        "strain_kcal": _mean(list(strain.values())),
    }

    # Per-phase buckets. Sample size = distinct days with ANY metric in that phase.
    buckets = {ph: {"sleep": [], "recovery": [], "strain": [], "days": set()}
               for ph in PHASES}
    all_dates = set(sleep) | set(recovery) | set(strain)
    for date_iso in all_dates:
        ph = moon_phase(date_iso)
        b = buckets[ph]
        b["days"].add(date_iso)
        if date_iso in sleep:
            b["sleep"].append(sleep[date_iso])
        if date_iso in recovery:
            b["recovery"].append(recovery[date_iso])
        if date_iso in strain:
            b["strain"].append(strain[date_iso])

    def _delta_pct(phase_avg, base):
        if phase_avg is None or not base:
            return None
        return round((phase_avg / base - 1) * 100)

    phase_stats = {}
    for ph in PHASES:
        b = buckets[ph]
        n = len(b["days"])              # distinct days with ANY metric → "Based on N nights"
        if n == 0:
            continue
        # Per-metric gating. Each metric's delta is claimed only when THAT metric
        # clears MIN_SAMPLE on its own — not when the union day-count does. This
        # matters now that the history backfill makes sleep far denser (~68 nights)
        # than recovery/strain (live-only): without it, a phase could show a
        # recovery delta computed from a single live night while displaying n=10.
        # Below the per-metric threshold we emit None, and the card renders "—".
        ns, nr, nstr = len(b["sleep"]), len(b["recovery"]), len(b["strain"])
        ps = _mean(b["sleep"]) if ns >= MIN_SAMPLE else None
        pr = _mean(b["recovery"]) if nr >= MIN_SAMPLE else None
        pstr = _mean(b["strain"]) if nstr >= MIN_SAMPLE else None
        phase_stats[ph] = {
            "sleep_delta_h": (round(ps - overall["sleep_h"], 1)
                              if ps is not None and overall["sleep_h"] is not None else None),
            "recovery_delta_pct": _delta_pct(pr, overall["recovery"]),
            "strain_delta_pct": _delta_pct(pstr, overall["strain_kcal"]),
            "sample_size": n,
            "metric_samples": {"sleep": ns, "recovery": nr, "strain": nstr},
        }

    today = datetime.now().astimezone().date().isoformat()
    return {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "current_phase": moon_phase(today),
        "phase_stats": phase_stats,
        "overall_avg": {
            "sleep_h": round(overall["sleep_h"], 1) if overall["sleep_h"] is not None else None,
            "recovery": round(overall["recovery"]) if overall["recovery"] is not None else None,
            "strain_kcal": round(overall["strain_kcal"]) if overall["strain_kcal"] is not None else None,
        },
    }


def main():
    payload = build()
    out = os.path.join(HERE, "patterns.json")
    with open(out, "w") as f:
        json.dump(payload, f, indent=2)
    cur = payload["current_phase"]
    n = payload["phase_stats"].get(cur, {}).get("sample_size", 0)
    print(f"pattern_engine: {cur} (n={n}), {len(payload['phase_stats'])} phases populated -> patterns.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
