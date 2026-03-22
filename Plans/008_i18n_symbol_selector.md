# i18n & Symbol Selector — 08: English Translation & Symbol Dropdown

**Status:** Done
**Completed:** 2026-03-22
**Commits:** 51f2ac0..e6d8a1f (3 commits)
**SDD Change:** symbol-selector

---

## What Was Built
- Full i18n: translated all UI and API text from Spanish to English
- Symbol selector dropdown for strategies (linked to instruments table)
- Indicators table in the frontend
- Draft save fixes
- Updated project docs and added symbol-selector SDD artifacts

## Key Files
- `openspec/changes/symbol-selector/` — SDD artifacts (exploration, proposal, design, specs, tasks)
- `frontend/src/` — Symbol selector component, indicators table
- `api/` — Updated API responses in English

## Decisions Made
- English as the UI language (internationalized from Spanish)
- Symbol selector backed by the instruments reference table (Phase 6)
- SDD used for symbol-selector due to cross-cutting nature (instruments + strategies + UI)

## Notes
- The i18n was a bulk translation, not a proper i18n framework — all strings changed in-place
- Symbol selector ties together Phases 6 (instruments table) and 7 (inline editing) into a cohesive UX
- This was the last feature phase before the audit
