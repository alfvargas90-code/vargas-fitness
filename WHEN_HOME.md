---
name: when-home
description: User-action-required queue for when Alfie is back at his Mac. Items here need physical access, password entry, or his judgment — Penny can't do them remotely. Penny references this list when he gets home.
---

# When Alfie gets home — action queue

> **How to use this list:** everything here is **user-action-required** — it
> needs physical access to the Mac, a password/credential entry, or Alfie's
> judgment call. Penny cannot complete these remotely. Work top-to-bottom or
> cherry-pick; check items off as done. Penny references this when he's back.

_Last updated: 2026-06-05 (octopus / Claude Code)._

---

## 🌙 STATUS 2026-06-05 (latest) — v2 lunar-details pass (redesign6)

New reference `design_refs/chatgpt_hero_v2_with_lunar_details.jpeg`. Three changes,
all via Codex implementation lane, PVR-verified by screenshot + DOM eval:

1. **Header removed ENTIRELY** — eyebrow, "Dashboard" h1, AV avatar, AND the date
   line all gone (you confirmed: header goes fully). The `<header>` element +
   `#header-sub` + `#profile-strip` are deleted; app.js's `renderHeader` /
   `renderProfileStrip` were already null-guarded (`if (!el) return`), so no
   console errors. Hero now starts at the rings; first content is the Recovery
   metric. Added `padding-top: max(2px, env(safe-area-inset-top))` so the bare top
   clears the iPhone status bar / Dynamic Island in the standalone PWA (0 on
   desktop, exact notch height on device — not chrome, just not hiding under it).
2. **All 3 metrics now orbit the moon** — Recovery top-left, **Sleep moved up
   bottom-center → top-right**, **Strain top-right → lower-right**. None below the
   moon anymore. Matches the earlier `chatgpt_lunar_mockup.png` (Rec TL / Sleep TR
   / Strain BR).
3. **Lunar details restored UNDER the moon** (overrides the old "no hero text"
   rule) — 4-line block from **REAL `lunar_stress.json` data**, not hardcoded:
   "Waning Gibbous / **Moon in Aquarius** / Leaves Aquarius / 6/6 · 7:42 PM".
   The mockup's "Capricorn / 8:45 AM" was dummy data; live data is Aquarius →
   Pisces ingress 6/6 7:42 PM (from `lunar.next_sign_change.at`). New renderer
   added to `renderRings` in app.js — **phase/terminator/illumination engine still
   untouched** (verified `node --check` + grep).

Legibility: enlarged/darkened the under-moon scrim so the lunar lines read over the
waves (also gives the mockup's clearer dark space under the moon); lifted Strain
clear of the bright wave band; dark-seated the purple lunar lines.

**Locked features verified:** Currents state-interpreter, 60s polling, all Polar/
VeSync/lunar bindings (Rec 73 / Sleep 75 / Strain 56% live), cards below hero
unchanged. **Cache → `redesign7`.** No console errors. Not pushed (traveling).
Hard-refresh / re-add to home screen to bust the cache.

---

## 🌙 STATUS 2026-06-05 — Hero = explicit 3-layer artwork (redesign5)

**Structural refactor, not parameter tweaks.** The hero is now an explicit layered
artwork pipeline instead of everything stacked inline. Claude orchestrated +
screenshot-verified each batch; **Codex authored every file edit** via
`llm --lane implementation`. Cache bumped `redesign4 → redesign5`.

**New z-order inside `#lpi-hero` → `.hero-stack`:**
1. `.hero-layer-1` (z1) — star field + deep-space nebula + containment vignette
2. `.hero-layer-2` (z2) — full-width wave bands: cyan/blue from LEFT (Recovery),
   coral/orange from RIGHT (Strain), converging beneath the moon, cradling it
3. `#rings-wrap` (z3) — metric rings composite (moon+rings SVG, **untouched**)
4. `.hero-layer-3` (z4) — moon volumetric bloom + shadow-halo seat (moon dominant)
5. `.hero-metrics-overlay` (z5) — Recovery/Sleep/Strain numbers + labels

**Deliberate architecture call:** moon + rings stay ONE composite SVG (the lunar
engine renders them together into `#rings-orbit-svg`). Splitting the moon into its
own layer would mean editing `renderOrbit` — out of bounds. The z-order intent
(rings behind moon) is preserved because the composite already draws the moon last.
Layer 3 adds bloom/halo *around* that composite, not inside it.

**Codex scorecard:** 7 calls, **7/7 edits landed clean, 0 fallbacks, 0 corruption.**
3 of 7 returned exit=124 (B1, B3b, B6... B6 exit=0 actually) — the watchdog killed
Codex *after* the edits wrote, while it hung on its summary. Edits were verified by
diff + screenshot every batch, not by Codex's stdout, so the hangs cost nothing.
Wall times 22–93s; the bigger the paste, the closer to the 90s ceiling.

**Locked features verified intact:** lunar engine (`phaseToIllum`/`moonSVG`/
`renderOrbit`) — app.js **0 lines changed**; Currents state-interpreter; 60s
data_hash polling; all Polar/VeSync bindings (Recovery 73 / Sleep 75 / Strain 52%
all live). Cards below hero unchanged.

**PVR iteration (strict, per Alfie 2026-06-05):** pushed past the first pass with
4 more Codex rounds against the reference JPEG. Hero **grown 252→330px** (layer
viewBoxes 260→341 to hold scale) so the waves got real vertical room; Layer 2 fully
**rebuilt** as distinct separated luminous ribbons (cyan/blue/purple from left,
coral/orange/red from right) with high amplitude + a full-width flow-through +
woven particles + higher side-sweeps for vertical spread; **atmosphere cleaned**
(killed the cyan-left/coral-right corner washes → reference's clean dark navy).

**Honest element match vs `chatgpt_hero_artwork.jpeg` (final):** waves ~92,
atmosphere ~92, moon render ~95, particles ~88, rings ~82, metric-glow ~95.
**Residual sub-95% is mostly NOT closeable:** moon phase (~50% lit today) ≠ the
mockup's gibbous and strain arc (56%) ≠ 100% — both **live data**, can't match a
static mockup without faking; moon size, Sleep-bottom-center, and pure-cyan recovery
ring are **your own prior deliberate decisions** the reference predates. The only
real structural ceiling: even at 330px the wave band is ~140px vs the mockup's
~250px (Currents card sits below) — so waves top out ~92, not 100, without making
the hero eat the whole first screen. **Decision for you:** the mockup has Sleep
top-right + a moon-context line bottom-center; we have Sleep bottom-center. Say the
word and I'll match the mockup layout (or keep your remap).

**Action for you:** none required — review on your phone (hard-refresh to bust the
app.js cache). Backups left at `.index.html.pre-redesign.bak` + per-batch `.bN.bak`.
Not pushed to git (you're traveling).

---

## 🎨 STATUS 2026-06-05 — Lunar Performance redesign shipped (Codex-built)

First real load test of the Codex-primary flip on a substantial build job. The
dashboard hero was rebuilt to pixel-match `design_refs/chatgpt_lunar_mockup.png`.
**Claude orchestrated + reviewed; Codex authored every file edit** (builder ≠
validator). Verified via Claude Preview at 375px after each batch.

**What landed (7 batches → 6 Codex calls):**
- **B1 Atmosphere** — star field opacity .16→.34 + 3rd bright-star layer; energy
  fields cleaned to cyan-LEFT / violet-CENTER / coral-RIGHT.
- **B2 Waves** — +40% presence (opacities .62/.68→.9, strokes +40%), extra
  lower-third streamer.
- **B3a Arcs** — the big one: inactive tracks now dark-navy `#243056` (were
  hue-tinted glowing full-rings = the "tangle"); recovery gradient → pure cyan
  (stopped bleeding into the purple sleep ring); strain ring + corner → coral
  (was gold); glow restrained to stop inter-ring bleed. Now reads as 3 clean
  concentric orbits.
- **B3b Corners** — remapped to mockup layout: Recovery TL · **Strain TR** ·
  **Sleep bottom-center** (was Recovery TL / Sleep TR / Strain BR).
- **B4 Moon** — earthshine on the shadow side (`#070B16` @ .86) so crescents keep
  crater detail + dimensionality and never vanish; stronger atmospheric halo.
  **Terminator / phase math untouched.**
- **B6+7 Polish** — tempered the central violet bloom for deeper OLED corners;
  restrained 9s glow-breathing on the energy fields (reduced-motion guarded).
- **B5 Typography** — HELD on a webfont. App already uses `-apple-system` = native
  SF Pro on your iPhone PWA, which *is* the mockup typeface. Inter/Geist would
  regress iOS fidelity + add a FOUT/network dep. No change = correct.

**Locked features verified intact:** Currents state-interpreter, 60s data_hash
polling, all Polar/VeSync/lunar_stress bindings, terminator/waning logic.

**Codex scorecard (the point of the exercise):** 6 rounds, **6/6 exit=0, all
model=codex, 0 fallbacks, 0 new incidents.** Flip held under load.
- Arch concern: B2 ran **76s vs the 90s watchdog** — big multi-element edits
  crowd the ceiling. Splitting B3 into 3a/3b kept calls at ~21s. **Keep Codex
  batches surgical** (≤ a handful of find/replace) or they'll start tripping the
  watchdog and forcing fallbacks.
- Cache gotcha (not Codex): `app.js?v=` must be bumped or the browser serves
  stale JS — wasted one verify cycle before I caught it. Bumped to `redesign2`.

**Action for you:** none required — review the look on your phone (hard-refresh /
re-add to home screen to bust the app.js cache). If the bottom-center Sleep label
crowds the moon on your device, say so and I'll nudge it down a few px.

---

## ⚙️ STATUS 2026-06-05 (later) — reasoning lane FLIPPED to Codex-primary

**The real fix, not another patch.** Reversed the lane priority in `~/bin/llm`:
the reasoning lane is now **Codex primary, Claude fallback** (was Claude primary /
Codex fallback from the earlier-today auto-fallback ship below). Net effect: $0
incremental cost (Codex runs on the existing ChatGPT Plus sub) + the dashboard no
longer goes dark when Claude OAuth dies overnight, because Claude was the flaky
piece and is now only the safety net.

- **What changed in `~/bin/llm`:** lane map `reasoning → codex` (was `claude`);
  fallback direction reversed to `codex → claude`; new fallback log shape
  `{primary:"codex", fallback:"claude", trigger:"hang|auth|rate|other"}`; Codex
  401/auth detected via `Not authenticated`/`401`/`Unauthorized`, rate via
  `429`/`rate limit`/`too many`; `[FALLBACK] codex→claude (trigger=…)` stderr line.
  90s watchdog preserved on both backends. Header/USAGE/inline comments updated to
  say codex-primary. `polar/summary.py` comment corrected (prose is now Codex-authored).
- **Overrides intact:** `--model claude` and `--model codex` still force a backend,
  and a forced `--model` now disables the fallback (pinned backend).
- **5/5 tests passed:** (1) real reasoning → codex, exit 0, `model:codex`, no
  fallback. (2) mock codex hang → watchdog killed at 90s → fallback to claude,
  exit 0, `trigger:hang`. (3) mock codex 401 → fallback to claude, `trigger:auth`.
  (4) `--model claude` → claude direct, no fallback. (5) `summary.py --slot recovery`
  → valid summary.json, schema intact, usage log shows `model:codex`.
- **Bootstrap exception used (documented):** per `claude-codex-playbook`, this is
  implementation work that should route to Codex. But `codex exec` **refuses to
  edit `~/bin`** ("Not inside a trusted directory") — it structurally cannot modify
  its own calling shim. Gave it one round, it hard-failed (exit 1, not even a hang),
  so I implemented directly (Claude builds, Claude reviews against the 5-test gate).
- **Rollback:** pre-flip snapshots at `~/bin/llm.bak.*` and `/tmp/llm.preflip.*`.
  To revert the lane only: `reasoning) DEFAULT_BACKEND=claude` and restore the
  prior dispatch block.
- **Not pushed** (Alfie's on the road) — polar-sync will absorb `polar/summary.py`;
  `~/bin/llm` lives outside the repo so it's local-only either way.
- **Playbook memory updated** with a dated note (dashboard reasoning lane now
  Codex-default; flip edit was Claude-direct via the bootstrap exception).

---

## ⚙️ STATUS 2026-06-05 — claude→codex auto-fallback SHIPPED (dark-dashboard fix, option 1)

**This closes the dashboard-goes-dark-on-auth failure mode.** When the reasoning
lane (`claude -p`) fails recoverably, `~/bin/llm` now auto-retries the same prompt
on `codex exec` and returns Codex's answer transparently — exit 0, caller none the
wiser. claude OAuth dying still leaves a `[FALLBACK]` breadcrumb (so you know to
reauth: `claude /login`), but the dashboard keeps writing in Codex voice meanwhile.

- **Trigger matrix** (only when primary backend is claude — forced `--model codex`
  never double-falls-back): **auth** (exit 1 + 401/"Failed to authenticate"/"Invalid
  authentication credentials") · **rate** (exit 1 + 429/rate limit/quota) · **hang**
  (rc=124 from the perl watchdog — the primary claude call is now wrapped in the same
  90s watchdog codex always had). **Any other non-zero (e.g. exit 2 syntax) does NOT
  fall back** — behaves exactly as before.
- **Audit trail:** each fallback appends `{ts,primary,fallback,trigger,excerpt}` to
  `~/.local/state/llm/fallbacks.jsonl`; usage log records `model:codex,exit:0` so
  billing/usage stays accurate.
- **Builder ≠ validator:** Codex built it via `llm --lane implementation` (1 round,
  clean). **One orchestrator deviation:** testing in a non-tty context exposed that
  `codex exec` blocks reading stdin ("Reading additional input from stdin…") →
  watchdog killed it at 90s. Fixed directly (2-line `</dev/null` on both backend
  calls) rather than burning a Codex round. **This matters for launchd** — the real
  dashboard path — though launchd's stdin is already /dev/null, so it's belt-and-braces.
- **Tests — all 5 pass:** (1) mock 401 → fallback, codex returns token, exit 0 ·
  (2) **REAL claude (still 401) → live fallback**, exit 0 · (3) mock 429 → fallback ·
  (4) mock hang sleep 120 → watchdog 90s → fallback · (5) mock exit 2 → **no** fallback,
  exit 2 preserved.
- **Live summary.py verified via fallback:** `summary.py --slot recovery --out /tmp/…`
  with claude 401 → produced valid JSON via Codex (`model:codex,exit:0,14.5s` in usage
  log) where the 04:00 dark-fire was `model:claude,exit:1`. Real `summary.json`
  untouched (hash unchanged). Not pushed to git.
- Backup before edit: `~/bin/llm.bak.20260605-062846`. **Reauth claude when you can:
  `claude /login`** — fallback covers you until then but Codex voice ≠ claude voice.

---

## ⚙️ STATUS 2026-06-04 (late) — Codex hang watchdog + visual refinement bundle

Replacement session (prior task `local_42aa…` got stuck on a blocking prompt — abandoned).
Builder ≠ validator held throughout (Codex built via `llm --lane implementation`,
Claude reviewed + verified). Nothing pushed manually — auto-push picks it up.

- **✅ Task 1 — Codex hang root-cause + watchdog (PRIORITY).** Root cause: **SQLite
  WAL-mode lock contention** on `~/.codex/logs_*.sqlite` — Codex.app's `app-server`
  (analytics-enabled) holds the db open continuously; the `codex exec` CLI writes the
  same WAL db and blocks intermittently when the app-server holds the lock (WAL had
  grown ~4MB un-checkpointed vs an 85MB db). Often hangs at the *end* of an otherwise-
  successful run, so edits still apply. **Fix shipped INTO `~/bin/llm`:** 90s perl
  timeout (no `timeout`/`gtimeout` on this box; perl already a dep) → on rc=124/any
  non-zero exit, appends a JSON line to `~/.local/state/llm/codex_incidents.jsonl`
  {ts,lane,prompt_excerpt,exit_code,theory(hang|auth|rate|other),codex_app_running,
  sqlite_size_mb}, prints `[CODEX-HANG]`/`[CODEX-FAIL]` to stderr, exits non-zero
  (loud — same lesson as silent-401). **Tested:** simulated auth-fail → theory=auth;
  real 90s hang (mock) → rc=124,theory=hang at 93s; normal `say ok` still works <90s.
  Then caught a **real** Codex hang during Task B/A dispatches. Backup: `~/bin/llm.bak.*`.
  **1 Codex round.** Workaround if it hangs hard: quit Codex.app (releases the lock).
- **✅ Task C — Sleep colors cache-bust.** `index.html` `app.js` ref bumped to
  `?v=2026-06-04-3` (was `-2`; bumped again after B+A2 changed app.js). New palette
  (`#2E1F6B / #DCCBFF / #7B4DE0`) confirmed rendering. No service worker exists, so the
  query-string change forces the PWA to refetch. **0 Codex rounds (already in working tree).**
- **✅ Task B — Currents Card reframe (Q&A → declarative briefing).** `summary.py`
  `block_header` now returns **TRAINING / NUTRITION / RECOVERY** (was "Should you…?");
  the workout/eat/rest instruction prompts rewritten to declarative Mission-Control
  conclusions (no verdict-word-first). Internal parse labels (`Workout:/Eat:/Rest:`)
  kept, so parsing is intact. `app.js` `BRIEF_HEADERS` extended with the 3 new headers
  (old ones kept → **backward compat**: current summary.json keeps rendering until the
  next slot fire regenerates it). Verified both formats render. (Claude reverted one
  out-of-scope hunk: Codex had also rewritten the dead-code `OUTPUT_SECTIONS` constant.)
  **1 Codex round + 1 manual revert.**
- **✅ Task A — 8-area atmospheric refinement.** Split into 2 Codex passes to fit the
  90s cap and isolate risk. **A1 (CSS, index.html):** denser/raised star field, brighter
  hero-zone blooms, +20% recovery/sleep glows & +25% strain glow, more glass blur +
  layered card edges (upper highlight / lower shading). **A2 (app.js render):** moon
  halo radius 1.65→1.90 + brighter ambient bloom + image brightness ×1.12 + softer/
  wider ground shadow; arc thickness 4→4.3 + stronger inner/outer bloom; hero metric
  number glow 14→18px; Currents conclusions brightened (neutral-200→100, labels stay
  muted); Recovery-Window active node brighter + glow trail + dominant "Now". **🛑 Lunar
  engine untouched — verified:** terminator/shadow path, illum/waning, phase geometry,
  moon image href all unchanged; live render still shows the correct phase shadow.
  **1 Codex round each (2 total), both clean.**

---

## ⚙️ STATUS 2026-06-04 — bundled implementation drop (4 tasks; Codex built 1-3, Claude verified)

Second Claude+Codex playbook run. Codex (`codex exec`, implementation lane) wrote
Tasks 1-3; Claude orchestrated, fixed the sandbox flag, and verified each. Builder ≠
validator held (Codex built → Claude validated). Independent PVR (Penny) still pending.

- **✅ Task 1 — Moon natal-house line.** `app.js` `renderLunarStress` now leads the
  moon context with `Moon is currently in your {N}H ({Sign})`, mapping the transit
  sign → natal house via a Whole Sign lookup (Capricorn ASC: Aquarius→2H … etc.).
  Detail row (sign · degree · phase) kept below. Live render confirmed:
  *"Moon is currently in your 2H (Aquarius)"*. Note: this intentionally overrides
  `lunar_stress.json`'s `moon_house_natal:1` (different house system) per spec. **1 Codex round.**
- **✅ Task 2 — Sleep stage contrast.** `app.js` `renderPolarSleep` bar + legend recolored
  to the locked purple set: Deep `#2E1F6B`, Light `#DCCBFF`, REM `#7B4DE0`. WCAG
  adjacent-contrast (bar order deep|light|rem): Deep–Light **9.2:1**, Light–REM **3.52:1**
  — both ≥3:1. No "Awake" stage exists in the data, so none added. **1 Codex round.**
- **✅ Task 3 — Metric persistence (pattern-engine foundation).** New `_append_metric_snapshot()`
  in `polar/summary.py`, called just before the `summary.json` write on the normal path.
  Appends one line to `polar/metrics_history.jsonl` (append-only, `'a'` mode, try/except
  non-fatal). Test fire wrote a valid line with all 7 metrics:
  `{recovery, hrv_delta_pct, rhr, sleep_min, sleep_quality, strain_pct, active_cal}` + ts/slot.
  File is git-tracked (not ignored) so it persists via auto-push. **1 Codex round.**
- **📋 Task 4 — Grammar/clarity pass (Claude reasoning lane).** Issues list produced and
  handed to Penny for review — **no edits applied** pending greenlight (see report).

---

## ⚙️ STATUS 2026-06-04 — stale-lock sweep LIVE in summary.py (first Claude+Codex playbook run)

`polar/summary.py` now self-heals the failure that pinned the dashboard at 17:37
today: a crashed git process left a 0-byte `.git/HEAD.lock` that silently blocked
every future push. New helper `_sweep_stale_git_locks()` runs as the first line of
both push paths (`git_push()` and the day-review push in `generate_day_review()`).
It removes a lock only when **all three** hold: file exists, mtime > 10 min old,
and no live process holds it open (`lsof -- <path>`). Fresh or held locks are left
alone (logged `[stale-lock] held, skipping`); removals log `[stale-lock] removed
<name> (age=…m, mtime=…)`. Defensive — never raises into the caller. Stdlib only,
BSD `lsof`, launchd-safe (no GUI). Verified in a temp repo: stale-unheld→removed,
fresh→kept, old-but-held→kept, no-lock→no-op. Real `.git` never touched in test.

> **Playbook note:** first real exercise of the **Claude+Codex implementation
> lane** — Codex (`llm --lane implementation`) wrote the helper, Claude reviewed +
> applied + verified. Landed in **1 Codex round** (first pass was correct; only
> macOS-specific risk checked was `lsof --` separator + held/unheld return codes,
> both confirmed). **Bootstrap caveat:** Codex-implemented but reviewed only by
> Claude — no independent PVR gate yet. True PVR review (Penny) is a v0.2 add.

---

## ⚙️ STATUS 2026-06-04 — role-router shim v0.1 is LIVE

`~/bin/llm` (lane-aware LLM router, [role_router_spec.md](../../09_Reference/agent_workflow/role_router_spec.md))
is built and wired in. **Migrated caller:** `polar/summary.py` `call_claude()` →
now routes through `llm --lane reasoning` (still dispatches to `claude -p`, so
behavior is unchanged). Original body kept commented out for one rollback cycle.
Usage logs land in `~/.local/state/llm/usage_YYYY-MM-DD.jsonl`. All 6 acceptance
criteria passed on the build machine (reasoning + implementation lanes both
return; no-lane errors loud; summary.json schema unchanged vs the 18:53 train-2
baseline).

> **Bootstrap caveat (one-time, per spec §"Bootstrap caveat"):** this first
> build broke the builder ≠ validator rule — Claude Code built *and* self-tested
> it because there's no Codex review channel inside Cowork/Dispatch yet. Known,
> accepted compromise. All *future* router changes must be reviewed by the other
> specialist. **End-to-end validation still pending:** the next real launchd fire
> (evening-1, 20:00 CDT) is the first autonomous run through the shim — confirm it
> wrote summary.json + pushed without regression.

---

## ~~1. Grant Full Disk Access to the venv pythons — UNBLOCKS AUTOSYNC~~ ✅ DONE 2026-06-01

> **RESOLVED 2026-06-01.** The FDA-on-CommandLineTools-python approach was a
> dead end — Apple's CLT python (3.9) shares one TCC identity across all its
> children, so launchd jobs off `/Volumes/Alfie&Co2` still died with
> `Operation not permitted` on `.venv/pyvenv.cfg`. **Fix that worked:** installed
> **python.org Python 3.12.10**, granted Full Disk Access to its own bundle
> (`/Library/Frameworks/Python.framework/Versions/3.12/Resources/Python.app`),
> and rebuilt both venvs (`polar/.venv`, `vesync/.venv`) on it.
>
> **Verified the same day (~20:16, all LaunchAgents exit 0):** launchd-fired
> `polar-sync` rewrote `manifest.json`; `polar-summary` ran a full `claude -p`
> pass → wrote `summary.json` → git commit + push; `vesync-sync` logged in, read
> the scale, saved its daily json. **Autonomous syncs are LIVE.**
>
> **Going forward:** use python.org python for anything launchd fires off the
> external volume — never rebuild these venvs on Apple's CommandLineTools python.

---

## 2. Hard-refresh the dashboard on your phone — confirm Energy panel placement

You found the **Energy throughout day** panel — it's there, just lower than you
expected (it sits *below* the Latest scale snapshot + new Scale history table,
above Training & Recovery). Hard-refresh (pull-to-refresh, or close/reopen the
PWA) to confirm it's showing.

**Decision for Penny:** do you want it **moved up** — between "Today's read" and
the KPI stat row? Say the word and Penny reorders the sections. (Right now order
is: Today's read → KPIs → Snapshot → Scale history → Energy → Training → Nutrition.)

---

## 3. VeSync history — Option A: one-tap iOS Shortcut (PARKED)

A "Scale screenshot → Penny" iOS Shortcut would make uploads one tap. **Parked**
— weekly-ish cadence doesn't justify the build yet. Current flow (text the
screenshot to Penny in Dispatch, she OCRs + pushes) is fine at this volume.
**Revisit if cadence increases** (e.g. you start weighing daily).

---

## ~~4. Daily-transit-snapshot task — STOPPED FIRING since 2026-05-15~~ ✅ RESTORED 2026-06-04

> **RESOLVED 2026-06-04 (octopus/Claude Code).** Root cause: the task lived in the
> **legacy** scheduler location (`~/Documents/Claude/Scheduled/daily-transit-snapshot/`)
> which the current Claude scheduler (`~/.claude/scheduled-tasks/`) no longer reads —
> orphaned on the scheduler migration, hence dark since 2026-05-15. **Fix:** re-registered
> as a live scheduled task `daily-transit-snapshot`, cron `30 5 * * *` (daily ~5:39am),
> enabled, next run 2026-06-05. Prompt carries the full natal chart + R1–R8 tightening
> rules; runs `ephemeris.py` (Swiss Ephemeris, graceful fallback if the build fails).
> **Two corrections vs the old task:** (1) snapshot now saves to the path summary.py
> actually reads (`~/Documents/Claude/Scheduled/daily-transit-snapshot/<date>-transit-snapshot.md`),
> not the old mismatched `transit-snapshots/` folder; (2) the daily **auto-iMessage was
> DROPPED** per the hard-stop-before-outbound rule — say the word to add it back.
>
> **TWO THINGS FOR ALFIE:** (a) hit **"Run now"** on the task once in the Scheduled
> sidebar to pre-approve its Bash/file-write tools — otherwise tomorrow's 5:39am
> unattended run may pause on a permission prompt. (b) NOTE: summary.py's 2026-06-03
> direct-data reframe means transits are **not currently injected into dashboard prose**
> anyway — this restores the snapshot *data layer* so it's ready if/when you re-enable
> injection.

---

## ~~5. Cowork bridge watchdog LaunchAgent — confirm loaded~~ ✅ FIXED 2026-06-04

> **RESOLVED 2026-06-04 (octopus/Claude Code).** `com.alfredo.cowork-watchdog` was
> present + loaded (exit 0) — BUT its liveness check `pgrep -fx 'Claude'` **never
> matched** (macOS `pgrep -f` won't match the full `.app` path), so it logged
> `RELAUNCHED` and re-ran `open -a Claude` **every 5 min** — pointless focus-stealing,
> and not a real death check. **Fix:** swapped the check to
> `ps -axo command | grep -Fq '/Applications/Claude.app/Contents/MacOS/Claude'`
> (matches ONLY the main app, not helper processes), reloaded, kickstarted — now
> logs `alive` correctly and will relaunch ONLY on a genuine death. Old plist backed
> up to `com.alfredo.cowork-watchdog.plist.backup-2026-06-04`. (Note: a second
> watchdog `com.alfredo.claude-watchdog` also runs the same 5-min keep-alive — belt
> and suspenders; both loaded exit 0.)

---

## 6. Rotate credentials — pasted-in-chat exposure 🔐

These were pasted in chat at some point and should be rotated:

- **Polar client secret** — still in local env. Rotate.
- **GitHub PAT** — ✅ already moved to osxkeychain. Rotate on next cycle for hygiene.
- **VeSync password** — still in local env (`vesync/.env`). Rotate.

**Action:** consider a full rotation cycle. PAT is the lowest-risk (already in
keychain); Polar + VeSync secrets still sit in local-env files. Rotating needs
you to log into each provider — **Penny will not log in or enter passwords on
your behalf.**

---

## 7. htmlaudit publish decision — PAUSED (no action until Mon 2026-06-08)

Publish decision is paused. **Reminder fires Mon 2026-06-08, 9 AM CST.** No
action needed before then — listed here only so it's not forgotten.

---

## 8. Decide fate of `polar/next_steps.md` (gitignored local note)

- Doc was edited today (2026-06-01) to fix stale schedule lines: "daily 7 AM" →
  "30-min rolling sync via `StartInterval 1800` + `RunAtLoad`". Edits live on
  disk only.
- File is currently in `.gitignore` (line 19, grouped under "local-only notes /
  source artifacts — not part of the public dashboard"), so the doc fix can't
  propagate via the public repo.
- **Decision needed:** leave it local-only (current state) **OR** force-track it
  (`git add -f`) so future-you / future Penny on a fresh checkout sees the
  corrected schedule. If forcing, also un-ignore by removing the line from
  `.gitignore`.
- Penny's lean: leave it local — keeps the public repo clean and consistent with
  the surrounding `.env` / machine-specific entries.

---

## ~~9. Wire silent-401 notifier into `summary.py` — RELIABILITY GAP~~ ✅ DONE 2026-06-04

> **RESOLVED 2026-06-04 (octopus/Claude Code).** Patch applied + tested. Added
> `_notify_dark_fire()` to `summary.py`; the outer `FATAL` handler now calls it
> before `sys.exit(0)`. On any dark AI-prose fire it appends a one-line ⚠️ alert to
> WHEN_HOME.md (timestamp · slot · claude exit code · theory: **auth/rate/other** ·
> 200-char excerpt) and fires a best-effort `osascript` banner (silent no-op under
> launchd). Also hardened `call_claude()` to fold **stdout** into the raised error —
> `claude -p` writes 401s to stdout, so without this an expired token misclassified
> as "other"; now it correctly reads `theory: auth — re-auth: run claude, then
> backfill the slot`. Verified with a simulated 401 (exit 1, OAuth-expired on stdout)
> → correct auth-tagged alert written. `sys.exit(0)` preserved (not silent ≠ spin
> launchd). Auto-fired alerts land at the bottom of this file under "Dark-fire log".

---

### Original spec (for reference)

## 9. Wire silent-401 notifier into `summary.py` — RELIABILITY GAP (added 2026-06-03)

**Discovered 2026-06-03:** the 04:15 AM overnight slot didn't write because
`claude -p` exited 1 (OAuth token expired → 401). The error went to **stdout**
(not stderr), `summary.py`'s outer `FATAL: claude exited` handler caught it
and `sys.exit(0)`'d to placate launchd. **No `summary.json` written, no
notification, no log alert.** Dashboard stayed pinned to yesterday's 8 PM
evening slot. You only noticed at ~7 AM by checking your phone. The 9:05,
12:30, 16:45, 20:00, 21:45 fires would have all failed identically until
re-auth.

**The gap:** every AI-prose fire (5 summary slots + 1 day-review) silently
fails dark when the Anthropic OAuth token expires/revokes. You find out by
accident, hours later. Weekly `11_MTG/maintenance_check.md` (Step E: Polar
sync recency >6 hrs) catches it on Sundays — but that's once a week, not
real-time.

**Proposed fix (NOT applied — needs your go):**

1. In `polar/summary.py`, find the `FATAL: claude exited` branch in
   `call_claude()`'s outer except (around line 1137).
2. Before `sys.exit(0)`, append a one-line entry to this file (`WHEN_HOME.md`)
   with: timestamp, slot, claude exit code, theory (auth/rate/other), plus
   short stdout/stderr excerpt.
3. Optionally fire an `osascript -e 'display notification ...'` banner — only
   useful if Mac is graphical-logged-in at the time (skip from launchd if it
   would be invisible).
4. Keep `sys.exit(0)` — goal is **not silent**, not "spin launchd".

**Decision needed:** greenlight the patch? Penny won't touch `summary.py`
without your go. If yes, ~10 lines of Python, no schema change.

**Related context:** the immediate fix today was for you to run `claude` /
re-auth manually, then Penny re-runs `summary.py --slot overnight` to
backfill. That recipe is captured in agent memory for next time
(`claude_cli_silent_401_gap` memory note).

---

## 10. Monthly trend summary — month-end roll-up across all slots (NEW 2026-06-03)

**Ask:** at month end, generate a summary that aggregates ALL slot data
across the month so trends are visible per timeframe — e.g. how recovery
mornings (7 AM) trended, how nutrition windows (11:30 / 3 PM) shaped energy,
how workout windows (5:30 / 8 PM) played out. Replace the Polar app entirely
as the analysis surface.

**Open questions** (decide when you have a clear 20 min):

1. **Surface** — dashboard card? Email PDF? Gmail draft (per your standard
   delivery pattern)? Multiple?
2. **Cadence** — fixed last day of month? Rolling 30-day every Sunday?
   Triggered manually?
3. **Slices** — per-slot trend lines (sleep, recovery, fuel, train) +
   correlations (e.g. did high-fuel midday → better evening workout window)?
4. **AI prose vs. data-only** — full narrative wrap-up, or just the
   charts/numbers with a 1-paragraph synth at the top?
5. **Where it lives** — `04_Projects/fitness-dashboard/monthly/` folder,
   or somewhere else?

**Penny's lean:** Gmail draft + dashboard card combo. Last day of month
fires a scheduled task; AI prose synth at the top (5-7 sentences pulling
the month's biggest deltas/streaks/regressions), charts beneath. Save PDF
+ raw JSON to vault for trend archive.

**Status:** PARKED. No build until you ratify the framing.

---

### Quick triage if you're short on time
1. ~~**#1 (Full Disk Access)**~~ — ✅ DONE 2026-06-01, autosync is live.
2. ~~**#9 (silent-401 notifier)**~~ — ✅ DONE 2026-06-04, patched + tested.
3. ~~**#4 (transit task)**~~ — ✅ RESTORED 2026-06-04 (hit "Run now" once to pre-approve tools).
4. ~~**#5 (cowork watchdog)**~~ — ✅ FIXED 2026-06-04 (was relaunch-spamming; now correct).
5. **#6 (rotate creds)** — security hygiene, 20 min when you have a clear window. ⬅ only open user-action item.
6. The rest are confirm-or-park (#2 Energy-panel placement, #7/#8/#10 parked).

---

## Dark-fire log

_Auto-appended by `summary.py` `_notify_dark_fire()` (WHEN_HOME.md #9) whenever an
AI-prose fire dies. If you see a fresh ⚠️ line here, the dashboard went stale — most
often an expired Anthropic OAuth token: run `claude` to re-auth, then have Penny
backfill the slot (`python3 polar/summary.py --slot <slot>`). Empty = healthy._

- ⚠️ **2026-06-05 04:00 CDT** — AI-prose fire went DARK · slot=`sleep` · claude_exit=`1` · theory: auth — re-auth: run `claude`, then backfill the slot · excerpt: `claude exited 1: Failed to authenticate. API Error: 401 Invalid authentication credentials [AUTH] backend=claude exit=1`

> **As of 2026-06-05** the claude→codex auto-fallback (STATUS above) means a
> claude auth/rate/hang failure no longer goes dark — `~/bin/llm` retries on Codex
> and the slot still writes (in Codex voice). A NEW dark-fire entry below this line
> now means **both** claude AND codex failed, or the fallback regressed. Check
> `~/.local/state/llm/fallbacks.jsonl` for the silent-but-handled claude failures.
