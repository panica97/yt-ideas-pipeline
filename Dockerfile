# Pipeline runner container — executes research pipeline tools
# (yt-dlp scraping, NotebookLM extraction, strategy processing)
# Usage: docker compose run pipeline python -m tools.youtube.search "query"
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "-m", "tools"]
