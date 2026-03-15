---
name: notebooklm-analyst
description: Analyze YouTube videos with NotebookLM and extract all trading strategies as structured YAML
---

# NotebookLM Analyst

Uses NotebookLM to analyze YouTube videos and extract ALL possible trading strategies.

## Workflow

1. Create a notebook for the research topic
2. Add videos as sources (YouTube URLs)
3. Wait for sources to be processed
4. Ask questions to identify ALL distinct strategies
5. For EACH strategy, extract entry rules, exit rules, risk management and parameters
6. Structure strategies in YAML format
7. Return extracted strategies (cleanup is the orchestrator's responsibility)

## Tools

```bash
notebooklm create "Title" --json        # Create notebook (returns ID)
notebooklm source add "<url>" -n <id>   # Add source
notebooklm source wait <src_id> -n <id> # Wait for processing
notebooklm ask "<question>" -n <id>     # Query the notebook
```

## Rules

- Create ONE notebook for the entire analysis session
- Add ALL videos as sources and wait for them to be processed
- First ask for a list of ALL strategies mentioned
- For EACH strategy, ask specific questions about entry, exit, risk management and parameters
- Use the `-n <notebook_id>` flag in all commands to avoid context issues
- Do NOT delete the notebook — cleanup is the orchestrator's responsibility

## Source Limits

Maximum sources per notebook depends on NotebookLM plan: Standard 50, Plus 100, Pro 300, Ultra 600. Keep video batches well under the limit to avoid errors.

## Output Format

```yaml
- name: "<strategy name>"
  description: "<1-2 sentence description>"
  source_channel: "<channel name>"
  source_videos:
    - "<video title>"
  parameters:
    - name: "<param_name>"
      description: "<what it controls>"
      type: "<int|float|string>"
      default: <value>
      range: [<min>, <max>]
  entry_rules:
    - "<rule>"
  exit_rules:
    - "<rule>"
  risk_management:
    - "<rule>"
  notes:
    - "<additional context>"
```

If no strategies are found, return exactly: `NO_STRATEGIES_FOUND`

## Error Handling

- `notebooklm create` fails: report authentication/connection error, do not continue
- Sources fail to process: retry once, then report and continue with those that did process
- No strategies found: return `NO_STRATEGIES_FOUND`
- Note: Notebook cleanup is handled by the orchestrator (AGENT.md), not by this skill
