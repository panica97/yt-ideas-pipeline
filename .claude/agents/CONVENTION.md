# Agent Convention

Standard for defining and organizing agents in the IRT project.

## Directory Structure

Every agent lives in its own directory under `.claude/agents/`:

```
.claude/agents/
  {agent-name}/
    AGENT.md          # Front-matter (metadata) + instructions + behavior
```

The `AGENT.md` file is the single source of truth for each agent. No separate manifest files.

## Front-Matter Format

Every `AGENT.md` starts with a YAML front-matter block delimited by `---`. This block contains machine-readable metadata used by Managers for sequencing and by developers for understanding the agent's contract.

```yaml
---
name: agent-name
description: One-line description of what this agent does
domain: research | backtesting | shared
role: ceo | manager | agent
inputs:
  - name: param_name
    type: string | integer | object | "TypeName[]"
    required: true | false       # default: false
    default: value               # optional
outputs:
  - name: output_name
    type: string | "TypeName[]" | "TypeName{}"
skills_used:
  - skill-name                   # references .claude/skills/{skill-name}/
dependencies:
  - agent-name                   # other agents this one depends on
---
```

### Required Fields

Every AGENT.md must have: `name`, `description`, `domain`, `role`, `inputs`, `outputs`.

### Optional Fields

`skills_used` and `dependencies` default to empty lists `[]`.

## Role Types

| Role | Description | Can Spawn Agents | Example |
|------|-------------|-----------------|---------|
| `ceo` | The Claude Code main session. Routes user intent to Managers or agents. | Yes | The user's session (not a file) |
| `manager` | Orchestrates a sequence of agents for a domain pipeline. | Yes | Research Manager |
| `agent` | Leaf worker. Performs a single responsibility. Does not spawn other agents. | No | Video Discovery |

The CEO is not a file-based agent -- it is the user's Claude Code session. Its routing rules live in the project `CLAUDE.md`.

## Domain Types

| Domain | Description |
|--------|-------------|
| `research` | Strategy discovery pipeline: videos, extraction, processing |
| `backtesting` | Strategy validation: simple/complete backtests, Monte Carlo, monkey tests, stress tests |
| `shared` | Cross-domain capabilities used by multiple domains (e.g., DB persistence) |

## Agent-Skill Relationship

Agents USE skills -- they do not replace them. The skill layer (`.claude/skills/`) contains stable, tested tools. Agents provide the orchestration logic, context passing, and decision-making on top.

- An agent's `skills_used` field lists which skills it invokes.
- Skills remain unchanged by the agent migration.
- Multiple agents can use the same skill.

## Adding a New Agent

1. Create `.claude/agents/{name}/AGENT.md` using `TEMPLATE.md` as a starting point.
2. Fill in the YAML front-matter with all required fields.
3. Write the agent's instructions in the body (below the front-matter).
4. If the agent is part of a Manager's pipeline, update that Manager's `AGENT.md` to include it in the sequence.
5. If the agent should be directly routable by the CEO, add a routing rule to the project `CLAUDE.md`.

## Existing Agents

See `DATA_FORMATS.md` for the data types referenced in agent inputs/outputs (Video, Strategy, Draft, etc.).
