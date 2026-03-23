---
name: research
description: Trigger the research agent to investigate trading strategies
---

# Research

Launches the research agent to investigate trading strategies. Supports three entry points.

## Usage

```
/research <topic>            # Research strategies for a topic (searches YouTube channels)
/research <youtube-url>      # Research strategies from a specific YouTube video
/research "<idea text>"      # Research strategies from a raw idea/description
```

This activates the research agent (`.claude/agents/research/AGENT.md`) which owns the full pipeline.

## Pre-launch

Before launching the agent, ask the user:

> Quieres que guarde las conversaciones con NotebookLM para esta sesion?

Pass the answer as `save_conversations: true/false` in the agent prompt.

## Early Stop Signals

NO_VIDEOS_FOUND, NO_NEW_VIDEOS, NO_STRATEGIES_FOUND, AUTH_ERROR, ERROR
