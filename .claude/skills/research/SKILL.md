---
name: research
description: Trigger the research agent for a given topic
---

# Research

Launches the research agent to investigate trading strategies for a topic.

## Usage

```
/research <topic>
```

This activates the research agent (`.claude/agents/research/AGENT.md`) which owns the full pipeline.

## Early Stop Signals

NO_VIDEOS_FOUND, NO_NEW_VIDEOS, NO_STRATEGIES_FOUND, AUTH_ERROR, ERROR
