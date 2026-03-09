# Research Quant Agent

Orchestrates the research pipeline: YouTube -> NotebookLM -> Strategy -> DB.

## Orchestration

The pipeline is invoked with the `/research <topic>` skill defined in `.claude/skills/research/SKILL.md`.

The skill launches 3 sequential sub-agents using Claude Code's Agent tool, each with its `CLAUDE.md` context injected into the prompt.

## Pipeline

```
/research <topic>
  -> YouTube Scraper Agent (fetch videos for the topic)
  -> NotebookLM Agent (extract strategies from videos)
  -> DB Manager Agent (save strategies to YAML)
  -> Summary to user
```

## Sub-agents

- `youtube_scraper/` — Fetch recent videos from DB channels by topic
- `notebooklm/` — Extract ALL strategies from videos using NotebookLM
- `db_manager/` — Save strategies to YAML database avoiding duplicates
- `backtester/` — (pending) Prepare and run backtests in Strategy Quant
