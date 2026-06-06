# Self-healing cache busting

_Last updated 2026-06-06._

## The problem (what used to break)

Both dashboards are "Add to Home Screen" web apps (PWAs). When you save one to
your iPhone home screen, iOS aggressively caches the page's `index.html` and
never checks for a new copy. So every time we shipped an update, your phone kept
showing the **old** version — frozen in time.

Worse: the usual trick for forcing fresh code (`app.js?v=2`, `?v=3`, …) lives
*inside* `index.html`. If iOS won't refetch `index.html`, it never sees the new
`?v=` number either. The cache-buster was itself stuck behind the cache.

That's why your workaround existed: delete the home-screen icon and re-add it
every single time. That dance stops now.

## The fix (three layers)

**Layer 1 — a version stamp.** Each dashboard ships a tiny `version.json` file
that says "this is build X." Every time the dashboard's code actually changes,
that stamp is rewritten automatically (see below).

**Layer 2 — a check that runs before anything else.** At the very top of each
`index.html` is a small script. On every visit it quietly fetches `version.json`
(bypassing the cache) and compares it to the build this device last saw. If they
differ, it wipes the local caches, records the new build, and reloads **once** so
you land on the fresh version. First-ever visit never reloads (nothing to
compare against), so there's no loop. This works with or without Layer 3 — it's
the load-bearing part.

**Layer 3 — a service worker (`sw.js`).** A background helper that always tries
the network first for pages, code, and data (so a new deploy is seen
immediately) while keeping big images and icons cached for speed and offline
use. If it ever fails to install, Layer 2 still does the job.

## What this means for you

**Nothing.** You never touch any of it. Open the dashboard from your home screen
like always. Within a few seconds of any deploy, it notices the new build and
refreshes itself. No more delete-and-re-add.

## The escape hatch

If a dashboard ever looks stuck or weird, append `?clear=1` to its URL once and
open it. That nukes every cache, storage layer, and service worker on the device
and reloads completely clean:

- Fitness: `https://alfvargas90-code.github.io/vargas-fitness/?clear=1`
- Timing:  `https://alfvargas90-code.github.io/vargas-fitness/timing-weather/?clear=1`

You should basically never need this — it's the big red button, just in case.

## How the stamp stays fresh (automatic)

The existing deploy gate (`deploy-watch/`, runs every 5 minutes) was extended:
whenever a dashboard's `index.html` or `app.js` changes, it rewrites that
dashboard's `version.json` with a new timestamp and pushes it in the same
commit. It only does this when the code truly changed, so it never loops or
spams commits. No build step, no npm, no dependencies — plain files.

## Where the files live

```
fitness-dashboard/
├── index.html                 ← inline version check (Layer 2)
├── version.json               ← build stamp (Layer 1)
├── sw.js                      ← service worker (Layer 3)
├── deploy-watch/              ← auto-regenerates version.json + pushes
└── timing-weather/
    ├── index.html             ← same inline check
    ├── version.json           ← its own stamp
    └── sw.js                  ← its own service worker
```

Each dashboard has its own independent set, so they never step on each other.

## Note for the curious

The service worker uses a single, stable cache name plus "network-first," rather
than a new cache name per build. Network-first already guarantees fresh
HTML/JS/JSON on every deploy, so per-build cache names would add moving parts
without changing the outcome. Each service worker only ever clears *its own*
dashboard's caches, so the two dashboards stay isolated.
