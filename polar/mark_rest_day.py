#!/usr/bin/env python3
"""Add or remove an explicit rest day in polar/rest_days.json.

Penny invokes this when Alfie tells her "rest day" in chat. The three AI prompt
layers (summary regular + day-review, lunar_stress) read rest_days.json; a date
present in the list flips that day's prose + LSI directive to recovery framing.

Usage:
    .venv/bin/python3 mark_rest_day.py 2026-06-02      # add a specific date
    .venv/bin/python3 mark_rest_day.py today           # add today
    .venv/bin/python3 mark_rest_day.py yesterday       # add yesterday
    .venv/bin/python3 mark_rest_day.py 2026-06-02 --remove   # back a date out

Idempotent: adding a date already present is a no-op; removing one that's
absent is a no-op. Dates are kept sorted and de-duplicated.
"""
import json
import os
import sys
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "rest_days.json")


def resolve_date(token):
    """Map 'today' / 'yesterday' / 'YYYY-MM-DD' to an ISO date string."""
    t = token.strip().lower()
    if t == "today":
        return date.today().isoformat()
    if t == "yesterday":
        return (date.today() - timedelta(days=1)).isoformat()
    # Validate it's a real ISO date; raises ValueError on bad input.
    return date.fromisoformat(token.strip()).isoformat()


def load():
    """Read rest_days.json, tolerating a missing file."""
    if not os.path.exists(PATH):
        return {"rest_days": [], "updated_at": None, "notes": ""}
    with open(PATH) as f:
        data = json.load(f)
    data.setdefault("rest_days", [])
    return data


def save(data):
    data["rest_days"] = sorted(set(data["rest_days"]))
    data["updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    with open(PATH, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def main():
    args = [a for a in sys.argv[1:]]
    remove = "--remove" in args
    args = [a for a in args if a != "--remove"]
    if len(args) != 1:
        print(__doc__.strip())
        return 2

    try:
        iso = resolve_date(args[0])
    except ValueError:
        print(f"error: '{args[0]}' is not a valid date "
              "(use YYYY-MM-DD, 'today', or 'yesterday')")
        return 2

    data = load()
    days = set(data["rest_days"])

    if remove:
        if iso in days:
            days.discard(iso)
            data["rest_days"] = list(days)
            save(data)
            print(f"removed rest day {iso}")
        else:
            print(f"no-op: {iso} was not a rest day")
    else:
        if iso in days:
            print(f"no-op: {iso} is already a rest day")
        else:
            days.add(iso)
            data["rest_days"] = list(days)
            save(data)
            print(f"added rest day {iso}")

    print("rest_days now:", sorted(data["rest_days"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
