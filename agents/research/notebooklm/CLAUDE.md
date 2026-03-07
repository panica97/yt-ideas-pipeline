# NotebookLM Agent

Usa NotebookLM para analizar vídeos de YouTube y extraer estrategias de trading estructuradas.

## Workflow

1. Crear notebook con el tema de investigación
2. Añadir vídeos como fuentes (URLs de YouTube)
3. Hacer preguntas para extraer reglas de entrada, salida, gestión de riesgo y parámetros
4. Estructurar la estrategia en formato YAML

## Tools

- `.claude/skills/notebooklm/SKILL.md` — Referencia completa del CLI
- `/notebooklm` — Slash command

## Outputs

- Estrategia estructurada para `data/strategies/strategies.yaml`
