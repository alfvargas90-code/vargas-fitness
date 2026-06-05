#!/bin/bash
# dashboard-deploy-watch.sh — MANUAL "deploy-now" shim for the dashboard gate.
#
# The real logic lives ONCE in deploy-watch/dashboard_deploy_watch.py. The
# launchd job runs that .py directly via the FDA-granted python.org Python
# (bare bash is TCC-blocked from the external volume under launchd — see the
# .py header). This shim is for forcing a deploy by hand from a Terminal (which
# DOES have Full Disk Access): it just execs the same .py via the same python,
# so manual and unattended runs are byte-identical logic.
#
#   usage:  ~/bin/dashboard-deploy-watch.sh
#
# Source-of-truth copy: 04_Projects/fitness-dashboard/deploy-watch/

REPO="/Volumes/Alfie&Co2/alfredo.v/04_Projects/fitness-dashboard"
PY="$REPO/polar/.venv/bin/python3"
SCRIPT="$REPO/deploy-watch/dashboard_deploy_watch.py"

[ -x "$PY" ] || { echo "deploy-watch: FDA python not found at $PY" >&2; exit 1; }
[ -f "$SCRIPT" ] || { echo "deploy-watch: script not found at $SCRIPT" >&2; exit 1; }

exec "$PY" "$SCRIPT" "$@"
