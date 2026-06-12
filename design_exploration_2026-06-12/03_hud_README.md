# 03 · Athlete Cockpit / HUD — "RDY.HUD"

**One-line POV:** Your body as a glass cockpit. Every system on one panel, monospace and tick-marked, with a master-caution lamp that lights red the moment recovery degrades.

## The point of view
Maximum information density, zero ambiguity. This direction treats the body like an aircraft: a **PRIMARY FLIGHT DISPLAY** (readiness gauge + HRV / resting HR / sleep bar meters), an **AIRFRAME** section (body comp), a **POWERPLANT** (energy out), a **FUEL SYSTEM** (macros), and an **ALL SYSTEMS** status column — all visible without hiding anything behind a tap.

Design language:
- **Monospace throughout**, UPPERCASE labels, right-aligned values in aligned columns — everything reads as instrumentation.
- **Status-light semantics everywhere**: green nominal / amber caution / red alert. Today the **MASTER CAUTION** banner is lit red ("RECHARGE COMPROMISED · ANS BELOW BASELINE · −4.2").
- HUD chrome — corner brackets, reticle lines, tick-marked SVG gauges and bar meters, a phosphor-cyan tactical palette.
- Readiness rendered as a partial arc gauge (36%, LOW) rather than a clean ring — deliberately more "instrument" than "app."

## What user it serves best
The **operator who wants the whole machine on one screen** and trusts himself to read instruments. It rewards scanning: colour tells you where to look, the columns tell you the exact value. This is the most "System-Architect-adjacent" of the conventional directions — it exposes a lot of state at once — but it frames the body as a *vehicle to fly*, not a *pipeline to trust.*

## Trade-offs
- High cognitive load; intimidating to a casual glance. The aesthetic is a strong flavour that can read as gimmick if the data underneath isn't genuinely rich.
- Monospace + dense gauges is the hardest of the four to keep legible and uncluttered as metrics are added.
