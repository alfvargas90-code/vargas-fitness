---
name: when-home
description: User-action-required queue for when Alfie is back at his Mac. Items here need physical access, password entry, or his judgment — Penny can't do them remotely. Penny references this list when he gets home.
---

# When Alfie gets home — action queue

> **How to use this list:** everything here is **user-action-required** — it
> needs physical access to the Mac, a password/credential entry, or Alfie's
> judgment call. Penny cannot complete these remotely. Work top-to-bottom or
> cherry-pick; check items off as done. Penny references this when he's back.

_Last updated: 2026-06-01 (Penny)._

---

## 1. Grant Full Disk Access to the venv pythons — UNBLOCKS AUTOSYNC ⚠️

The launchd-driven syncs (polar, nutrition, vesync) and the summary fires can't
run autonomously until the venv python binaries have **Full Disk Access**.
Today this also blocked the dashboard preview server from reading the
`/Volumes/Alfie&Co2` volume — same root cause.

**Heads-up — it's 2 binaries, not 3.** Verified against the .plist ExecStart
paths on 2026-06-01: polar and vesync each have their own `.venv`, but the
**nutrition** sync reuses `polar/.venv/bin/python3` (there is no
`nutrition/.venv`). So granting FDA to these two covers all three syncs:

```
/Volumes/Alfie&Co2/alfredo.v/04_Projects/fitness-dashboard/polar/.venv/bin/python3
/Volumes/Alfie&Co2/alfredo.v/04_Projects/fitness-dashboard/vesync/.venv/bin/python3
```

**Path:** System Settings → Privacy & Security → **Full Disk Access** → `+` →
⌘⇧G (Go to folder) → paste each path above → add it → toggle ON.

**Unblocks the summary fires at:** 4:15 AM · 9:05 · 12:30 · 16:45 · 20:00.

> **Note (2026-06-01):** morning summary moved **8:30 → 9:05** to clear the
> 30-min rolling `polar-sync` timer (which hits :00/:30 boundaries) — fixes the
> same-minute sync race that left "Today's Read" stale. **But the FDA grant
> above is still pending**, so these fires won't actually run autonomously until
> the two venv pythons get Full Disk Access. The schedule fix and the FDA grant
> are independent — both are required for a clean 9:05 read.

> ⚠️ If you ever give nutrition its own venv later, add
> `nutrition/.venv/bin/python3` to FDA too — until then the polar binary covers it.

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

## 4. Daily-transit-snapshot task — STOPPED FIRING since 2026-05-15 ⚠️

The scheduled task that feeds the astrology layer in **Section 12** summaries
stopped firing **2026-05-15**. Until restored, the astrology section of those
summaries runs **empty**.

**Action:** verify task status, then re-enable. Penny can help diagnose once
you confirm whether it's a launchd unload, an expired cron, or a script error —
but the re-enable likely needs your hands on the Mac.

---

## 5. Cowork bridge watchdog LaunchAgent — confirm loaded

Confirm the watchdog LaunchAgent is **loaded** and actually auto-relaunches the
Claude app every **5 min** if it dies (the bridge that keeps Penny ↔ Terminal
in sync).

**Action:** `launchctl list | grep -i cowork` (or the watchdog's label) and
confirm it's present + exit code 0. If absent, `launchctl load` the plist.

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

### Quick triage if you're short on time
1. **#1 (Full Disk Access)** — highest leverage, unblocks all autosync. Do this first.
2. **#4 (transit task)** — astrology summaries are degraded until fixed.
3. **#6 (rotate creds)** — security hygiene, do when you have a clear 20 min.
4. The rest are confirm-or-park.
