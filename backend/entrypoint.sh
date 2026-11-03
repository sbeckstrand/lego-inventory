#!/usr/bin/env bash
set -euo pipefail

# Wait for the database to accept connections before migrating.
python - <<'PY'
import sys, time
from sqlalchemy import create_engine, text
from app.config import get_settings

url = get_settings().database_url
for attempt in range(1, 31):
    try:
        engine = create_engine(url)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("Database is ready.")
        break
    except Exception as exc:  # noqa: BLE001
        print(f"Waiting for database... ({attempt}/30): {exc.__class__.__name__}")
        time.sleep(2)
else:
    print("Database never became reachable.", file=sys.stderr)
    sys.exit(1)
PY

echo "Running migrations..."
alembic upgrade head

echo "Starting app..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 ${UVICORN_RELOAD:+--reload}
