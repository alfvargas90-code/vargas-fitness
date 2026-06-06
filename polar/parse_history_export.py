#!/usr/bin/env python3
"""Backfill the live Polar schema from the Polar history export.

The Polar "user data export" ships aggregate files (one JSON array each) rather
than the per-night files the live sync writes:

    sleep_result_<...>.json      62 nights — timing, stages, hypnogram, cycles
    sleep_score_<...>.json       62 nights — sleep score + sub-scores
    nightly_recovery_<...>.json  62 nights — mean RRi / rMSSD / respiration interval

This script reads those three (straight out of the .zip — no full extraction),
joins sleep_result + sleep_score by ``night``, and writes per-night files in the
LIVE schema into separate ``historical/`` folders so live syncs never collide:

    polar/sleep/historical/<DATE>.json
    polar/recharge/historical/<DATE>.json

Honest mapping notes (see WHEN_HOME for the full writeup):
  * Sleep maps cleanly — start/end times + ISO-8601 stage durations are exactly
    what pattern_engine.sleep_hours() consumes. This is the real unlock.
  * The export's recovery records carry HRV (rMSSD), mean RR interval and mean
    respiration interval, but DO NOT carry Polar's ANS Charge status (1-6) or the
    Nightly Recharge status. pattern_engine.recovery_pct() keys off
    ``ans_charge_status``; since the export lacks it we DO NOT synthesise one
    (that would fake a metric on a different scale than the live nights). The
    historical recharge files therefore feed baseline HRV but do NOT contribute
    to the recovery-delta buckets. That asymmetry is intentional and documented.

Idempotent: re-runs overwrite the same per-night files; nothing duplicates.
No AI calls, no network. Run:  python3 polar/parse_history_export.py
"""
import argparse
import glob
import json
import os
import re
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
SLEEP_OUT = os.path.join(HERE, "sleep", "historical")
RECHARGE_OUT = os.path.join(HERE, "recharge", "historical")

# Where the export zip might live (iCloud Drive is where Alfie dropped it).
ZIP_GLOBS = [
    os.path.expanduser("~/Library/Mobile Documents/com~apple~CloudDocs/polar-user-data-export*.zip"),
    os.path.expanduser("~/Downloads/polar-user-data-export*.zip"),
    os.path.expanduser("~/Desktop/polar-user-data-export*.zip"),
    os.path.join(HERE, "history", "polar-user-data-export*.zip"),
]

# Prefixes of the aggregate files we care about (export appends a user id + uuid).
PREFIX_SLEEP_RESULT = "sleep_result_"
PREFIX_SLEEP_SCORE = "sleep_score_"
PREFIX_RECOVERY = "nightly_recovery_"          # NB: also matches nightly_recovery_blob_
PREFIX_RECOVERY_BLOB = "nightly_recovery_blob_"


# --- ISO-8601 duration -> seconds ---------------------------------------
_DUR_RE = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?")


def iso_dur_seconds(s):
    """'PT8H5M', 'PT7H41M30S', 'PT0S', 'PT25140S' -> int seconds. None if unparseable."""
    if not s or not isinstance(s, str):
        return None
    m = _DUR_RE.fullmatch(s)
    if not m:
        return None
    h, mi, se = m.groups()
    total = (int(h or 0) * 3600) + (int(mi or 0) * 60) + (float(se) if se else 0)
    return int(round(total))


# --- locating + loading the aggregate files -----------------------------
def find_zip(explicit=None):
    if explicit:
        return explicit if os.path.exists(explicit) else None
    for pat in ZIP_GLOBS:
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]
    return None


def _load_named_from_zip(zf, prefix, exclude_prefix=None):
    """Return the parsed JSON of the first archive member whose basename starts
    with ``prefix`` (and not ``exclude_prefix``), or None."""
    for name in zf.namelist():
        base = os.path.basename(name)
        if base.startswith(prefix) and not (exclude_prefix and base.startswith(exclude_prefix)):
            with zf.open(name) as fh:
                return json.load(fh)
    return None


def load_aggregates(zip_path=None, src_dir=None):
    """-> (sleep_result_list, sleep_score_list, recovery_list). Reads from a zip
    or, if ``src_dir`` is given, from an already-extracted folder."""
    if src_dir:
        def _load_dir(prefix, exclude=None):
            for p in sorted(glob.glob(os.path.join(src_dir, prefix + "*"))):
                b = os.path.basename(p)
                if exclude and b.startswith(exclude):
                    continue
                with open(p) as fh:
                    return json.load(fh)
            return None
        return (_load_dir(PREFIX_SLEEP_RESULT),
                _load_dir(PREFIX_SLEEP_SCORE),
                _load_dir(PREFIX_RECOVERY, exclude=PREFIX_RECOVERY_BLOB))

    with zipfile.ZipFile(zip_path) as zf:
        return (_load_named_from_zip(zf, PREFIX_SLEEP_RESULT),
                _load_named_from_zip(zf, PREFIX_SLEEP_SCORE),
                _load_named_from_zip(zf, PREFIX_RECOVERY, exclude_prefix=PREFIX_RECOVERY_BLOB))


# --- mapping export records -> live schema ------------------------------
def map_sleep(result, score):
    """Join one sleep_result + matching sleep_score into a live-schema sleep dict.

    Only the fields pattern_engine / future consumers actually use are emitted;
    the bulky per-minute hypnogram + HR-sample dicts are intentionally dropped
    (unused downstream, and they'd 10x the on-disk footprint)."""
    ev = result.get("evaluation", {}) or {}
    sres = result.get("sleepResult", {}) or {}
    hyp = sres.get("hypnogram", {}) or {}
    phases = ev.get("phaseDurations", {}) or {}
    analysis = ev.get("analysis", {}) or {}
    intr = ev.get("interruptions", {}) or {}
    cycles = (sres.get("sleepCycles", {}) or {}).get("cycles", {}) or {}
    cycle_models = cycles.get("sleepCycleModels", []) or []
    ssr = (score or {}).get("sleepScoreResult", {}) or {}

    night = result.get("night")
    out = {
        "date": night,
        "sleep_start_time": hyp.get("sleepStart"),
        "sleep_end_time": hyp.get("sleepEnd"),
        "continuity": analysis.get("continuityIndex"),
        "continuity_class": analysis.get("continuityClass"),
        "light_sleep": iso_dur_seconds(phases.get("light")),
        "deep_sleep": iso_dur_seconds(phases.get("deep")),
        "rem_sleep": iso_dur_seconds(phases.get("rem")),
        "unrecognized_sleep_stage": iso_dur_seconds(phases.get("unknown")) or 0,
        "sleep_score": int(round(ssr["sleepScore"])) if ssr.get("sleepScore") is not None else None,
        "total_interruption_duration": iso_dur_seconds(intr.get("totalDuration")),
        "short_interruption_duration": iso_dur_seconds(intr.get("shortDuration")),
        "long_interruption_duration": iso_dur_seconds(intr.get("longDuration")),
        "sleep_cycles": len(cycle_models) or None,
        "group_duration_score": ssr.get("groupDurationScore"),
        "group_solidity_score": ssr.get("groupSolidityScore"),
        "group_regeneration_score": ssr.get("groupRefreshScore"),
        "efficiency_percent": analysis.get("efficiencyPercent"),
        "source": "history_export",
    }
    return night, out


def map_recovery(rec):
    """One nightly_recovery record -> live-recharge-ish dict.

    Derivations are exact unit conversions, not estimates:
      heart_rate_avg      = 60000 / mean RR interval (ms)
      breathing_rate_avg  = 60000 / mean respiration interval (ms)
      heart_rate_variability_avg = mean rMSSD (already the HRV avg)
      beat_to_beat_avg    = mean RR interval (ms)   [direct, same field as live]
    NO ans_charge_status / ans_charge / nightly_recharge_status — absent in the
    export, deliberately not synthesised."""
    night = rec.get("night")
    rri = rec.get("meanNightlyRecoveryRri")
    rmssd = rec.get("meanNightlyRecoveryRmssd")
    resp = rec.get("meanNightlyRecoveryRespirationInterval")
    out = {
        "date": night,
        "heart_rate_avg": int(round(60000 / rri)) if rri else None,
        "beat_to_beat_avg": rri,
        "heart_rate_variability_avg": rmssd,
        "breathing_rate_avg": round(60000 / resp, 1) if resp else None,
        "source": "history_export",
    }
    return night, out


# --- writing ------------------------------------------------------------
def _write(folder, date_iso, payload):
    if not date_iso or len(date_iso) != 10 or date_iso[4] != "-":
        return False
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, f"{date_iso}.json"), "w") as f:
        json.dump(payload, f, indent=2)
    return True


def run(zip_path=None, src_dir=None):
    sleep_results, sleep_scores, recoveries = load_aggregates(zip_path, src_dir)
    report = {"sleep_written": 0, "recovery_written": 0,
              "sleep_skipped": [], "recovery_skipped": [], "hrv_values": []}

    score_by_night = {e.get("night"): e for e in (sleep_scores or [])}
    for result in (sleep_results or []):
        night, payload = map_sleep(result, score_by_night.get(result.get("night")))
        # A usable sleep night needs at least the span (engine's primary path) or
        # summed stages (its fallback). Skip & log anything with neither.
        has_span = payload["sleep_start_time"] and payload["sleep_end_time"]
        has_stages = any(payload[k] for k in ("light_sleep", "deep_sleep", "rem_sleep"))
        if not (has_span or has_stages):
            report["sleep_skipped"].append(night)
            continue
        if _write(SLEEP_OUT, night, payload):
            report["sleep_written"] += 1
        else:
            report["sleep_skipped"].append(night)

    for rec in (recoveries or []):
        night, payload = map_recovery(rec)
        if payload["heart_rate_variability_avg"] is None and payload["beat_to_beat_avg"] is None:
            report["recovery_skipped"].append(night)
            continue
        if _write(RECHARGE_OUT, night, payload):
            report["recovery_written"] += 1
            if payload["heart_rate_variability_avg"] is not None:
                report["hrv_values"].append(payload["heart_rate_variability_avg"])
        else:
            report["recovery_skipped"].append(night)

    return report


def main():
    ap = argparse.ArgumentParser(description="Backfill live Polar schema from the history export.")
    ap.add_argument("--zip", help="path to polar-user-data-export*.zip")
    ap.add_argument("--dir", help="path to an already-extracted export folder")
    args = ap.parse_args()

    src_dir = args.dir
    zip_path = None
    if not src_dir:
        zip_path = find_zip(args.zip)
        if not zip_path:
            print("ERROR: export zip not found. Pass --zip <path> or --dir <folder>.")
            return 2
        print(f"export zip: {zip_path}")

    rep = run(zip_path=zip_path, src_dir=src_dir)
    print(f"sleep    -> {rep['sleep_written']} files into {os.path.relpath(SLEEP_OUT, HERE)}/"
          + (f"  (skipped {len(rep['sleep_skipped'])}: {rep['sleep_skipped']})" if rep['sleep_skipped'] else ""))
    print(f"recharge -> {rep['recovery_written']} files into {os.path.relpath(RECHARGE_OUT, HERE)}/"
          + (f"  (skipped {len(rep['recovery_skipped'])}: {rep['recovery_skipped']})" if rep['recovery_skipped'] else ""))
    if rep["hrv_values"]:
        hv = rep["hrv_values"]
        print(f"HRV (rMSSD) across {len(hv)} nights: avg={sum(hv)/len(hv):.1f} min={min(hv)} max={max(hv)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
