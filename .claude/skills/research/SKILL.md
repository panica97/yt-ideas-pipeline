---
name: research
description: Orchestrate the full research pipeline - fetch YouTube videos by topic, extract strategies via NotebookLM, and save to database
---

# Research Pipeline Orchestrator

When the user invokes `/research <topic>`, orchestrate the full pipeline by launching sequential sub-agents. Each agent has a specific role, tools, and output format.

## Input

- `$ARGUMENTS` — the topic to research (must match a topic in `data/channels/channels.yaml`)

## Pipeline Steps

Execute these steps **sequentially**. Each step depends on the previous one's output.

### Step 1: YouTube Scraper Agent

Launch an Agent with this prompt:

```
Read your instructions from agents/research/youtube_scraper/CLAUDE.md and follow them.

TASK: Fetch recent videos for topic "$ARGUMENTS".
```

**If the agent returns `NO_VIDEOS_FOUND`**: Stop the pipeline and tell the user no recent videos were found for the topic. Suggest they check the channels database with `/yt-channels`.

**Otherwise**: Collect the list of URLs for Step 2.

### Step 2: NotebookLM Analyst Agent

Launch an Agent with this prompt:

```
Read your instructions from agents/research/notebooklm/CLAUDE.md and follow them.

TASK: Analyze these YouTube videos and extract ALL trading strategies you can find.
Notebook title: "Research: $ARGUMENTS"

VIDEO URLS:
{URLs from Step 1}
```

**If the agent returns `NO_STRATEGIES_FOUND`**: Stop the pipeline and tell the user no strategies were found in the videos.

**Otherwise**: Collect the YAML output for Step 3.

### Step 3: DB Manager Agent

Launch an Agent with this prompt:

```
Read your instructions from agents/research/db_manager/CLAUDE.md and follow them.

TASK: Save these strategies to the database.

STRATEGIES TO SAVE:
{YAML from Step 2}
```

### Step 4: Summary

After all agents complete, present a summary to the user:

```
## Research Complete: <topic>

**Videos analyzed:** <count>
**Strategies found:** <count>
**New strategies saved:** <list>
**Duplicates skipped:** <list>

### Strategies

For each strategy, show:
- Name
- Source channel
- Brief description
- Key entry/exit rules
```

## Error Handling

- If any agent fails unexpectedly, report the error and which step failed
- Do NOT continue to the next step if the current step failed
- Always ensure NotebookLM notebooks are cleaned up (deleted) even on failure
