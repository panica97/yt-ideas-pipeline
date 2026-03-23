# Audit 04 - Phase 10.2: Research Pipeline Flexibility

**Date:** 2026-03-23
**Scope:** Phase 10.2 changes (commits fd5481d, 0d1788c) — 3 entry points (TOPIC, VIDEO URL, IDEA), `topic_slug` optionality, todo-review skill, pipeline documentation
**Method:** Full code review of all changed files, cross-referencing AGENT.md instructions against Python implementations and DB schema
**Status:** Complete

---

## Tracking

### Issue Status

| # | Issue | Severity | Status | Resolved In | Commit/PR |
|---|-------|----------|--------|-------------|-----------|
| 1 | `add_history()` missing `classification` parameter | MEDIUM | Resolved | audit_04 batch fix | pending |
| 2 | `total_steps=6` hardcoded, but pipeline now has 8 steps | MEDIUM | Resolved | audit_04 batch fix | pending |
| 3 | Preflight runs for IDEA entry point unnecessarily | LOW | Resolved | audit_04 batch fix | pending |
| 4 | VIDEO entry point dedup weakness with NULL topic_id | MEDIUM | Resolved | audit_04 batch fix | pending |
| 5 | Research SKILL.md not updated for new entry points | MEDIUM | Resolved | audit_04 batch fix | pending |
| 6 | VIDEO entry point session-history correlation is fragile | MEDIUM | Resolved | audit_04 batch fix | pending |
| 7 | `_resolve_topic_id` used as public API from AGENT.md | LOW | Resolved | audit_04 batch fix | pending |
| 8 | No URL validation for VIDEO entry point | MEDIUM | Resolved | audit_04 batch fix | pending |
| 9 | IDEA entry point: no minimum-length or content validation | LOW | Resolved | audit_04 batch fix | pending |

**Status values:** Open, Resolved, Won't Fix, Deferred

### Implementation History

| Date | Action | Issues Addressed | Notes |
|------|--------|------------------|-------|
| — | — | — | — |

---

## Key Findings

### HIGH Priority

_No HIGH severity issues found. The Phase 10.2 changes are architecturally sound._

### MEDIUM Priority

**M-01: `add_history()` missing `classification` parameter**
File: `tools/db/research_repo.py:162-192`

AGENT.md (line ~115) and the pipeline docs both show calling `add_history()` with `classification="irrelevant"` for filtered videos in Step 1.5. However, `add_history()` does not accept a `classification` parameter. The `ResearchHistory` model does have a `classification` column (models.py:142), but the function never sets it. The agent will get a `TypeError` at runtime when trying to record irrelevant videos.

**M-02: `total_steps=6` hardcoded in `create_session()`**
File: `tools/db/research_repo.py:65`

`create_session()` hardcodes `total_steps=6`, but the pipeline now has 8 logical steps (0, 1, 1.5, 2, 3, 4, 4.5, 5, 6, 7). The frontend Live page uses this value for progress bars. Different entry points skip different steps, so the total varies: TOPIC=8, VIDEO=6, IDEA=5. The hardcoded value will show inaccurate progress for TOPIC and IDEA entry points.

**M-04: VIDEO entry point dedup weakness with NULL topic_id**
File: `tools/db/research_repo.py:175-178`, `tools/db/models.py:148`

The unique constraint `uq_history_video_topic` is on `(video_id, topic_id)`. For VIDEO entry points, `topic_id=None`. PostgreSQL treats each `NULL` as distinct, so the same video URL researched multiple times via the VIDEO entry point will create duplicate history rows. The `add_history()` dedup check (`WHERE video_id = X AND topic_id = NULL`) uses `==` which translates to `= NULL` and will never match, bypassing dedup entirely.

**M-05: Research SKILL.md not updated for new entry points**
File: `.claude/skills/research/SKILL.md`

The skill still shows `Usage: /research <topic>` and describes "Launches the research agent to investigate trading strategies for a topic." It doesn't mention VIDEO URL or IDEA entry points. The early stop signals list is also incomplete (missing `NO_NEW_VIDEOS`... actually it is listed). The description should reflect all 3 entry points since this is the user-facing trigger.

**M-06: VIDEO entry point session-history correlation is fragile**
File: `api/services/research_session_service.py:43-63`

The `get_sessions()` function correlates sessions with history items by time window (`researched_at >= started_at` and `researched_at <= completed_at`) and `topic_id`. For VIDEO sessions where `topic_id=None`, the query at line 56-59 skips the `topic_id` filter entirely, which means it will pick up ALL history items within the time window across all entry points. If two sessions overlap in time, videos from one session could appear in the other.

**M-08: No URL validation for VIDEO entry point**
File: `.claude/agents/research/AGENT.md` (Entry Point Detection)

The URL detection only checks for `youtube.com/watch` or `youtu.be/` substrings. There's no validation that the URL is well-formed, that the video ID is extractable, or that the video actually exists. A malformed URL like `youtube.com/watch?v=` (empty video ID) or an input like `"I like youtube.com/watch videos"` would be misclassified as a VIDEO entry point. Since the agent uses `yt-dlp` for metadata extraction, this would fail at that step, but with a confusing error.

### LOW Priority

**L-03: Preflight runs for IDEA entry point unnecessarily**
File: `.claude/agents/research/AGENT.md` (Step 0)

The IDEA entry point skips Steps 1, 1.5, and 2 (NotebookLM). The preflight check verifies NotebookLM authentication. For IDEA input, NotebookLM is never used, so the preflight check is wasted work and could block the pipeline if NotebookLM auth is expired (even though it's not needed).

**L-07: `_resolve_topic_id` used as public API from AGENT.md**
File: `.claude/agents/research/AGENT.md` (Step 1.5 code sample), `tools/db/research_repo.py:32`

AGENT.md imports `_resolve_topic_id` (prefixed with `_`, conventionally private) from `research_repo`. This should either be made public (drop the underscore) or a public wrapper should be provided.

**L-09: IDEA entry point: no minimum-length or content validation**
File: `.claude/agents/research/AGENT.md` (Entry Point Detection)

The IDEA entry point is a catch-all: anything that's not a URL or topic slug becomes an IDEA. Very short inputs like `/research "RSI"` or `/research "yes"` would proceed through the pipeline with insufficient strategy information, likely producing meaningless variants. There's no guidance on minimum content expectations.

### Recurring Patterns

1. **Schema-code drift** — The `ResearchHistory` model has columns (`classification`, `title`) that aren't fully wired into the `add_history()` repository function. The model was updated but the repo function wasn't. This is the same pattern of incremental model changes not propagating to helper functions.

2. **Hardcoded constants not adapted for flexibility** — `total_steps=6` was correct for the single TOPIC entry point but wasn't updated when the pipeline became flexible. Constants that depend on pipeline shape should be parameterized.

3. **NULL-unsafe dedup** — The `(video_id, topic_id)` unique constraint and the Python dedup check both fail when `topic_id=None` due to SQL NULL semantics. This pattern could recur in any future nullable foreign key used as part of a unique constraint.

---

## Action Items

**HIGH Priority:**

_None._

**MEDIUM Priority:**

1. **Add `classification` and `title` params to `add_history()`** — Effort: small
   Route: quick fix
   Update `tools/db/research_repo.py:add_history()` to accept and pass `classification` and `title` to the `ResearchHistory` constructor.

2. **Make `total_steps` dynamic in `create_session()`** — Effort: small
   Route: quick fix
   Accept `total_steps` as a parameter (default 8) and let the agent pass the correct value based on entry point (TOPIC=8, VIDEO=6, IDEA=5).

3. **Fix VIDEO entry point dedup with COALESCE or separate logic** — Effort: small
   Route: quick fix
   Use `IS NOT DISTINCT FROM` or `COALESCE(topic_id, -1)` in the dedup check, and update the unique index to use a partial index or `COALESCE` expression.

4. **Update research SKILL.md for all entry points** — Effort: small
   Route: quick fix
   Update usage section to show `/research <topic|url|idea>` and describe all three modes.

5. **Fix session-history correlation for non-topic sessions** — Effort: medium
   Route: quick fix
   Add a `session_id` foreign key to `ResearchHistory` to directly link history items to their session, instead of relying on time-window correlation.

6. **Add basic URL validation for VIDEO entry point** — Effort: small
   Route: quick fix
   Add regex validation for YouTube URL format and video ID extraction before proceeding.

**LOW Priority:**

1. **Skip preflight for IDEA entry point** — Effort: small
   Route: quick fix
   Add a condition in AGENT.md Step 0 to skip preflight when entry point is IDEA.

2. **Make `_resolve_topic_id` public or provide wrapper** — Effort: small
   Route: quick fix

3. **Add IDEA minimum content guidance** — Effort: small
   Route: quick fix
   Document minimum expectations (e.g., must contain at least entry or exit rules) and add a warning if the idea text is under ~20 characters.

---

## Statistics

- Total items audited: 15 files across skills, agents, repos, services, models, migrations, docs
- HIGH severity issues: 0
- MEDIUM severity issues: 6
- LOW severity issues: 3
- Patterns identified: 3
