FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy API source
COPY . /app/api/

# tools/db/ is mounted as a volume via docker-compose in dev.
# For production, uncomment and use a multi-stage build or COPY from context.
# Ensure tools is a proper package
RUN mkdir -p /app/tools && touch /app/tools/__init__.py

# Alembic runs from /app/api/ directory
WORKDIR /app/api

CMD ["sh", "-c", "cd /app/api && alembic upgrade head && uvicorn api.main:app --host 0.0.0.0 --port 8000 --app-dir /app"]
