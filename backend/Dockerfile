# CRISIS AGENTS backend. Single worker by design: simulation state lives in-process.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 ENV=prod HOST=0.0.0.0 PORT=8000 WEB_CONCURRENCY=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini main.py ./
COPY migrations ./migrations
COPY app ./app

RUN useradd --create-home --uid 10001 crisis && chown -R crisis /app
USER crisis
EXPOSE 8000

# Outside dev the app refuses to start without strong COMMANDER_AUTH_TOKEN / ADMIN_AUTH_TOKEN,
# and applies Alembic migrations on startup (DB_AUTO_CREATE=false).
CMD ["python", "main.py"]
