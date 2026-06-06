# claude-handoff — kill the desktop app before Terminal claude

Permanent fix for the Claude OAuth multi-client collision: the desktop app and a
Terminal `claude` CLI signed into the same account fight over one refresh token
and auth dies. This makes the **Terminal the exclusive owner** — launching
`claude` in a Terminal evicts the desktop first. The `cowork-watchdog`
LaunchAgent brings the desktop back (~5 min) after the Terminal session ends, so
the iMessage bridge self-heals. Alfie never has to think about it.

## What's installed

| Piece | Location | Role |
|---|---|---|
| Logic | `~/bin/claude-handoff` | detect + evict desktop, then `exec` real claude |
| Source of truth | `04_Projects/fitness-dashboard/bin/claude-handoff` | git-tracked original |
| Interceptor | `claude()` function in `~/.zshrc` | calls the handoff in interactive shells |
| Real CLI | `~/.local/bin/claude` → `…/versions/<v>` | what the script execs (absolute path) |
| Log | `~/.local/state/claude-handoff.log` | one line per eviction |

## Why a zsh function and not `~/bin/claude`

`~/.local/bin` (the real claude) sits **ahead of** `~/bin` on `$PATH`, so a
`~/bin/claude` wrapper would never win the lookup — the spec's assumption there
was wrong (verified `which claude` → `~/.local/bin/claude`, PATH #2 vs `~/bin`
#14). A zsh function defined in `~/.zshrc` wins over PATH for interactive shells,
which is exactly — and only — the case we want to intercept.

## Transparency for automated fires (intentional)

`~/.zshrc` is sourced by **interactive** shells only. launchd jobs, the
`~/bin/llm` reasoning fallback, and subagents run non-interactive shells, never
see the function, and hit the real CLI directly via PATH. They do **not** kill
the desktop — correct, since those are the jobs that need the bridge alive.

## Detection notes

- `pgrep -f` does **not** match the desktop main process on this machine
  (returns no PID) — avoided. Detection mirrors the watchdog: `ps -axo … | awk`.
- Match is **exact** on the command line (`/Applications/Claude.app/Contents/
  MacOS/Claude`, bare or `+ args`). Plain `grep -F` substring is unsafe — it also
  matches Helpers, the disclaimer shim, and any script that merely mentions the
  path. awk exact/prefix isolates the one real main process.
- SIGTERM, wait ≤3s, then one SIGKILL escalation. Re-entry guard
  (`CLAUDE_HANDOFF_DONE`) + absolute exec path = no possible loop.

## Smoke test — run from a STANDALONE Terminal.app window

> Do NOT run this from inside a Claude desktop agent session — that shell is a
> child of the desktop app, so killing it kills your session. Use Terminal.app.

```bash
open -a Claude; sleep 20                 # ensure desktop is up
ps -axo command= | grep -F '/Applications/Claude.app/Contents/MacOS/Claude' | grep -v grep
                                         # → shows the main process (alive)
claude --version                         # function fires: evicts desktop, prints version
tail -3 ~/.local/state/claude-handoff.log    # → shows the kill event
ps -axo command= | grep -F '/Applications/Claude.app/Contents/MacOS/Claude' | grep -v grep
                                         # → now empty (desktop gone)
# wait up to 5 min for the watchdog, then:
ps -axo command= | grep -F '/Applications/Claude.app/Contents/MacOS/Claude' | grep -v grep
                                         # → main process back (bridge self-healed)
```

## Known limitation — >5 min Terminal sessions

The `cowork-watchdog` relaunches the desktop every 5 min **regardless** of an
active Terminal session, so a Terminal session longer than 5 min gets the desktop
relaunched under it → collision returns mid-session. The handoff alone does not
cover this. Fix (pending validation): make the watchdog terminal-aware — skip the
relaunch while a real CLI claude (`~/.local/share/claude/versions/…`) is running.
See the handoff report / ask before editing the deployed watchdog plist.

## Rollback

```bash
# remove the interceptor
cp ~/.zshrc.bak.<TIMESTAMP> ~/.zshrc      # backups written at install time
# or delete just the `claude()` block from ~/.zshrc
rm ~/bin/claude-handoff
```
