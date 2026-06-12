# 04 · System Architect's View — "Observability Console"

**One-line POV:** The only dashboard that shows you the *machine behind the metrics* — every number carries its source, its sync time, its freshness, and an honest MEASURED-vs-DERIVED label. Trust by transparency.

## The point of view
Built directly on Alfredo's self-identity as a **System Architect**: someone who designs precise data systems (sources, ingest, derived fields, locked data) and trusts a number only when he can see where it came from. So this design makes *provenance a first-class citizen of the UI*, not a footnote.

Signature elements:
- **Data-lineage diagram** (inline SVG): `POLAR / VESYNC / NUTRI → INGEST (normalize·dedupe·stamp) → DERIVED` with status nodes, per-edge sync timestamps, and a `PIPE_RUN 12:30:04 · 0 errors · 1 source aging` log line. The pipeline *is* the hero.
- **System-health header**: `PIPELINES 3/3 OK · LAST FULL SYNC 12:30 · COMPLETENESS 96%`.
- **Every metric row carries**: value, a **source badge** (VESYNC / POLAR / NUTRI), last-sync time, and a **freshness dot** (green fresh / amber aging / grey stale).
- **MEASURED vs DERIVED** labelled explicitly — e.g. "Active kcal" is flagged DERIVED (Δ cumulative) because Polar gives no discrete workouts, so honesty about computed-vs-read is built in. This directly encodes the rule that recovery/burn must never be *fabricated*.
- Refined dark-slate console, electric-teal accent, monospace numerals, tabular alignment.

## What user it serves best
**Alfredo specifically.** It serves the builder who distrusts a metric he can't audit, who's been burned by stale syncs and fabricated sessions, and who finds *confidence in the plumbing* more reassuring than a pretty number. It's also the most defensible / monetizable framing — "personal health observability" is a product story the other three aren't.

## Trade-offs
- The most niche. To a normal user, surfacing sync times and lineage is noise — this only delights a systems thinker.
- Demands the pipeline metadata actually exist and stay accurate; the design makes any staleness *visible*, which is the point but also raises the bar on the backend.
