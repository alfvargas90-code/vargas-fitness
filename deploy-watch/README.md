# deploy-watch — dashboard auto-push gate

Belt-and-suspenders LaunchAgent that auto-commits + pushes **only** the
dashboard meta files when they change, so hand edits never sit un-pushed (the
loop that broke all day 2026-06-05). Covers **both** dashboards: the root
fitness dashboard and `timing-weather/`.

**Watched (and nothing else):**
`index.html`, `app.js`, `version.json`, `sw.js`,
`timing-weather/index.html`, `timing-weather/app.js`,
`timing-weather/version.json`, `timing-weather/sw.js`,
`WHEN_HOME.md`, `polar/summary.py`. Polar/nutrition JSON is left to polar-sync.

**Self-healing cache bust:** when a dashboard's *content* (`index.html` or
`app.js`) changes, the gate rewrites that dashboard's `version.json` with a
fresh timestamp and ships it in the same commit. The inline version check at the
top of each `index.html` then busts the browser/PWA cache automatically — no
more delete-and-re-add the iOS home-screen icon. `version.json` is regenerated
**only** on a real content change, so clean-tree re-runs never loop. Full
explanation: `../docs/cache-busting.md`.

## Files (this dir = source-of-truth, committed to origin)

| File | Role |
|------|------|
| `dashboard_deploy_watch.py` | The actual watcher. Runs **in place** from here. |
| `com.alfredo.dashboard-deploy-watch.plist` | LaunchAgent: 5-min `StartInterval` + `RunAtLoad`. |
| `dashboard-deploy-watch.sh` | Thin manual "deploy-now" shim → installed to `~/bin/`. |

## Why Python, not bash (important)

A launchd-spawned `/bin/bash` has **no Full Disk Access**, so TCC blocks it from
the external `/Volumes/Alfie&Co2` volume (`getcwd: Operation not permitted`) —
it can't even reach the repo, let alone git-push. The watcher therefore runs via
the **FDA-granted python.org Python** at `polar/.venv/bin/python3` (the same
interpreter polar-sync uses); its `git` subprocess inherits the access. The bash
shim is only for manual runs from a Terminal, which already has FDA.

## Safety

- **Pathspec-scoped commit** (`git commit -- <4 files>`): cannot absorb polar's
  staged JSON even mid-cycle. Structurally impossible, not just guarded.
- **Stale `.git/*.lock` sweep** (ports `polar/summary.py::_sweep_stale_git_locks`),
  but only a live **git** holder blocks it — an incidental Spotlight/mdworker
  reader no longer pins the lock forever.
- **Concurrency defer:** if another git op is mid-flight, retry once after 5s
  then `[DEPLOY-DEFER]` and bail (retries next interval).
- **Post-commit guard:** if a non-watched file ever lands in the commit, undo it
  (`reset --soft`) and shout `[DEPLOY-UNEXPECTED-STAGED]`.
- **Loud failures only:** `[DEPLOY-FAIL]` + stderr + non-zero exit on any
  push/auth failure. Never a silent exit 0.

Log: `~/.local/state/dashboard-deploy-watch.log`

## Redeploy after a Mac reset

```bash
REPO="/Volumes/Alfie&Co2/alfredo.v/04_Projects/fitness-dashboard"
cp "$REPO/deploy-watch/dashboard-deploy-watch.sh" ~/bin/dashboard-deploy-watch.sh
chmod +x ~/bin/dashboard-deploy-watch.sh
cp "$REPO/deploy-watch/com.alfredo.dashboard-deploy-watch.plist" \
   ~/Library/LaunchAgents/com.alfredo.dashboard-deploy-watch.plist
launchctl bootstrap gui/$(id -u) \
   ~/Library/LaunchAgents/com.alfredo.dashboard-deploy-watch.plist
launchctl list | grep dashboard-deploy-watch   # confirm loaded
```

> Prerequisite: the python.org Python (`polar/.venv/bin/python3`) must have Full
> Disk Access granted in System Settings → Privacy & Security → Full Disk Access.
> This is the same one-time machine-setup step polar-sync depends on.
