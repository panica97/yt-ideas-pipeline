# Strategy Pipeline Refinement — 05: DraftViewer, Variants & Translator

**Status:** Done
**Completed:** 2026-03-21
**Commits:** 852c44d..6c9553a (7 commits)

---

## What Was Built
- Visual DraftViewer replacing raw JSON display, with condition display fixes
- Conversation saving option in research flow
- Strategy-variants skill: purify, split long/short, propose market/timeframe variants
- Improved notebooklm-analyst: structured extraction with 3-round questions, market/timeframe context
- Translator scoped to pure strategies (entry/exit only, no SL/TP generation)
- Pipeline updated: analyst -> variants -> translator flow
- Bug fixes: SAR indicator not valid for unidirectional variants, RiskSection crash on null stop_loss_mgmt

## Key Files
- `.claude/skills/strategy-variants/` — Variants skill
- `.claude/skills/notebooklm-analyst/` — Improved analyst
- `.claude/skills/strategy-translator/` — Scoped translator
- `frontend/src/components/DraftViewer` — Visual strategy viewer

## Decisions Made
- Translator simplified to literal translation (no creative strategy proposals — reverted from Phase 4)
- Strategy-variants as a separate pipeline step between analyst and translator
- Three-round question extraction in NotebookLM analyst for better strategy coverage
- Pipeline order: analyst -> variants -> translator (variants inserted as new step)

## Notes
- This phase corrected the Phase 4 decision to make translator "creative" — went back to pure translation
- The variants skill handles the creativity (long/short splits, market/timeframe proposals)
- DraftViewer was a major UX improvement, making strategy data visually scannable
