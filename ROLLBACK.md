# Rollback options

## Option 2 — undo the color-semantics review (2026-06-03)
To restore the state before the color-semantics refinement:
  git reset --hard pre-color-semantics-2026-06-03
  git push -f origin main

## Option 1 — undo the council fixes (2026-06-02)
To restore the pre-council-fix state:
  git reset --hard pre-council-fixes-2026-06-02
  git push -f origin main

Both tags were pushed to origin/tags before their changes landed.
