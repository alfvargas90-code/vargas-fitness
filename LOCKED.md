---
name: dashboard-locked
description: Lunar Performance Dashboard — locked state as of 2026-06-05. Canonical journey retrospective + current spec + acceptable residuals + what's parked for later. Read this first when picking up the project cold.
---

# Lunar Performance Dashboard — LOCKED 2026-06-05

## ⚡ COLOR OVERRIDE — 2026-06-24

> Alfredo explicitly overrode the 2026-06-05 color lock to ship the **Eclipse** palette (black + gold variant 4). Approved in Dispatch.

**Old (overridden):** Strain coral · Recovery cyan · Sleep violet · cyan-from-left + coral-from-right wave field

**New (Eclipse, locked 2026-06-24):**
- Background: near-pure black (`#000`)
- No wave field (Layer 2 removed)
- Three concentric arcs: hairline gold (`#F0B429` family, graduated)
- Moon: thin-corona treatment, photographic LRO texture preserved
- Cards: "engraved" treatment (gold hairline borders, no glass blur)
- Accents: gold-only (no coral, cyan, violet)

**Backups:** `index.html.bak-2026-06-24-pre-eclipse`, `app.js.bak-2026-06-24-pre-eclipse`, `data.js.bak-2026-06-24-pre-eclipse` — preserved alongside the new canonical for rollback.

**Source of override:** `design_exploration_2026-06-23_black_gold/eclipse_full/` — promoted to canonical 2026-06-24 02:28 UTC.

---



> **You have a dashboard.** This file captures what it is, how we got here, what's protected, and what's parked.

---

## The journey in three acts

### Act 1 — Foundation (2026-06-04)
- Role-router shim `~/bin/llm` built with `--lane reasoning|implementation`
- **Claude+Codex playbook** locked: Claude reasoning / Codex implementation / PVR gates / builder ≠ validator
- Silent-401 notifier + stale-lock sweep + Cowork watchdog fixes (WHEN_HOME #4, #5, #9)
- Council router (`octopus`) wired for high-stakes decisions only

### Act 2 — Visual iteration (2026-06-05 day)
- 3-layer hero architecture (atmosphere / waves / moon) — structural refactor
- Currents card: Q&A → **state-interpreter** (State + Read + optional close)
- 60s polling + `data_hash` refresh → card regenerates on any data change
- Hero composition: Recovery TL · Sleep TR · Strain BR
- Lunar context block under moon with live `next_sign_change` data
- Multiple PVR cycles caught oversells; surfaced the **deploy gap** ("shipped but never pushed")
- ARV skill authored as pre-build review gate (bookends PVR)

### Act 3 — Infrastructure + lock (2026-06-05 evening)
- **Deploy gate rule** locked: code tasks must commit + push + verify origin before "done"
- **Deploy watcher** LaunchAgent built — auto-commits + pushes dashboard meta files every 5 min
- **Codex-primary in production** — launchd plist PATH patched (nvm node prepended) so Codex serves autonomous fires
- 17:30 train-1 fire validated Fix A end-to-end (Codex served, no manual intervention)
- ARCHITECTURE.md elevated: dashboard is the first workload, not the only design assumption

---

## What's LOCKED — the dashboard right now

### Visual / hero
- **3-layer rendering pipeline:** Layer 1 (stars + deep-space gradient) · Layer 2 (cyan-from-left + coral-from-right wave field, converges beneath moon) · Layer 3 (moon with volumetric bloom + shadow halo)
- **Moon:** dynamic phase rendering from real lunar data (engine UNTOUCHABLE), photographic LRO texture, 30%+ visual dominance
- **Three concentric arcs:** Strain (outer, coral) · Recovery (middle, cyan) · Sleep (inner, violet)
- **Metric overlay:** Recovery TL · Sleep TR · Strain BR (corner) with localized dark-seats for legibility
- **Lunar context block:** "Waning Gibbous / Moon in [current sign] / Enters [next sign] / [ingress time]" — all live from `lunar_stress.json.next_sign_change`
- **Cards:** glass treatment (subtle blur, navy surface, soft inner glow, thin border)
- **Header chrome:** removed (no "Lunar Performance Dashboard" title, no avatar)
- **Safe-area inset top** preserved for iOS notch handling

### Currents card (state-interpreter — DO NOT REGRESS TO COACH FORMAT)
```
STATE
[Word]
Recovery [N] • Sleep [N] • Strain [N]%

READ
[Single synthesized paragraph — Apple Weather / Oura / WHOOP register.
No headings, no bullets, no questions, no prescriptions.]

[Optional closing line — max 6 words]
```
- **Refresh:** 60s polling + `data_hash` fingerprint → re-renders on any data change
- **Voice:** observational, interpretive, decision-intelligence — NOT coach / FAQ / checklist

### Backend / autonomous prose
- **Reasoning lane primary:** Codex via `~/bin/llm --lane reasoning` (was Claude pre-2026-06-05)
- **Fallback:** Claude (when Codex hangs, 401, rate-limit)
- **7-fire schedule:** 04:00 · 07:00 · 11:30 · 15:00 · 17:30 · 20:00 · 21:45 (CDT)
- **launchd PATH includes nvm node dir** so Codex resolves (Fix A applied 2026-06-05)
- **Watchdog patterns:** silent-401 notifier · stale-lock sweep · Codex-hang detection · auto-fallback shim

### Data bindings (live — no fakes)
- Polar (recovery, HRV, RHR, sleep stages, activity calories) via `polar/sync.py` every 30 min
- VeSync (scale) via `vesync/sync.py` ad-hoc
- Lunar (phase, sign, ingress) via `polar/lunar_stress.py`
- `polar/metrics_history.jsonl` — append-only timeseries (foundation for future pattern engine)

### Deploy pipeline
- **Polar-sync auto-commit** grabs `polar/*.json` + `polar/summary.py` every 30 min
- **Deploy-watch LaunchAgent** auto-commits + pushes `index.html`, `app.js`, `WHEN_HOME.md` every 5 min if changed
- **Manual code tasks** must `commit + push + verify origin SHA` before declaring done (per `deploy-gate-rule`)
- **GitHub Pages** rebuilds in ~30-60s after push

### Locked decisions
| Decision | Locked | Where |
|---|---|---|
| Moon stays dynamic — never static image | 2026-06-05 | spec + lunar engine |
| Strain in BR corner with dark-seat | 2026-06-05 | index.html top:228 + scrim |
| Currents = state-interpreter, not coach | 2026-06-05 | summary.py prompt + app.js renderer |
| Codex-primary reasoning lane | 2026-06-05 | `~/bin/llm` + plist PATH |
| Header chrome removed | 2026-06-05 | index.html `<header>` deleted |
| 3-layer hero pipeline | 2026-06-05 | index.html `.hero-stack` |
| Builder ≠ validator (PVR) | 2026-06-04 | claude-codex-playbook |
| Deploy gate (push before READY) | 2026-06-05 | deploy-gate-rule |

---

## Acceptable residuals — DO NOT iterate (already at architectural ceiling)

| Residual | Why acceptable |
|---|---|
| Wave amplitude ~92% match | Currents card sits below hero — pushing waves further means compressing cards. PVR called this. |
| Moon phase doesn't match mockup's gibbous | Live data, not mockup. Mockup was design fiction. |
| Strain ring percentage varies | Live data — real strain, not dummy 100%. |
| Inner ring color "pure" cyan vs mockup gradient | Intentional — matches LPI palette decision. |

---

## Parked for the weekend fix sweep (see `weekend_fix_plan.md`)

| Item | Why parked |
|---|---|
| Codex SQLite hang root fix | Discipline + watchdog catches; analytics-off research pending |
| Claude OAuth multi-client collision | Keychain fix applied; `ANTHROPIC_CONFIG_DIR` isolation untested |
| Tier 3 Ollama fallback | Both-backends-fail still goes dark; Ollama install + wire (~7GB, $0) |
| `index.html` cache-bust | Only `app.js?v=` busts; index.html PWA cache can stay stale |
| Git-lock contention serialization | 4 auto-pushers racing; mutex / flock pass needed |
| Credential rotation (Polar, VeSync) | WHEN_HOME #6, your hands required |
| Monthly trend roll-up | WHEN_HOME #10 — needs 30 days of `metrics_history.jsonl` |
| PVR template baked into `start_code_task` | Discipline + memory rule applied; template not codified |

---

## Canonical docs / memories that survive this lock

**Skills:**
- [[arv]] — pre-build Architecture Review & Validation (just authored)
- [[pvr-production-readiness-verification]] — post-build production readiness
- [[pop-project-operating-principles]] — operational standards
- [[hold]] — anti-pattern friction layer

**Memory files (cross-session brain):**
- [[claude-codex-playbook]] — role split, lane assignments
- [[deploy-gate-rule]] — commit + push + verify before READY
- [[codex-subscription]] — $20/mo flat, Codex CLI workhorse
- [[likes-chatgpt-output]] — Codex voice validated
- [[fitness-dashboard-direction-locked]] — UNLOCKED 2026-06-05 for redesign; this file supersedes
- [[claude-oauth-setup-quirks]] — multi-client collision context
- [[claude-cli-silent-401-gap]] — notifier rationale

**Project docs:**
- `weekend_fix_plan.md` — prioritized $0 fixes to lock recurring failure modes
- `09_Reference/agent_workflow/role_router_spec.md` — shim spec
- `00_north_star_design_doc.md` + `00_north_star_spec.md` — pre-lock design intent

---

## How to pick this up cold

1. Read this file first (`LOCKED.md`)
2. Read `claude-codex-playbook` memory + `deploy-gate-rule` memory
3. Read `weekend_fix_plan.md` if working on infrastructure hardening
4. Open the dashboard URL: https://alfvargas90-code.github.io/vargas-fitness/
5. Check WHEN_HOME.md for the latest status block + any active dark-fires
6. Check `~/.local/state/llm/usage_$(date +%Y-%m-%d).jsonl` for backend health
7. ONLY iterate on visuals if PVR's ratings show <90% per element AND the change wouldn't break a locked decision above

---

## Done is done

The dashboard is not perfect. It is **locked**. The architectural decisions above are sticky.

Future iteration goes into the weekend fix list, the monthly trend roll-up, or pattern engine work — not back into the hero layout.

The platform is now the asset. The dashboard is its first proof.

*Locked 2026-06-05 by Alfie + Penny + Codex. Closing commit lineage: 2bfc65c.*
