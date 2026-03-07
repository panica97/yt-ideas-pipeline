# YouTube Scraper Agent

Busca vídeos recientes en canales monitoreados y por keywords usando yt-dlp.

## Tools

- `tools/youtube/search.py` — Búsqueda por keyword
- `tools/youtube/fetch_topic.py` — Fetch por topic desde channels DB
- `tools/youtube/channels.py` — CRUD de canales

## Inputs

- `data/channels/channels.yaml` — Base de datos de canales por topic

## Outputs

- Lista de vídeos con URLs para procesar en NotebookLM
