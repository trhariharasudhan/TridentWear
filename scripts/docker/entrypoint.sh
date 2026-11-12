#!/bin/sh
# Container entrypoint: apply DB migrations (SQL mode only), then start the API.
set -e
if [ "${DB_MODE:-json}" = "postgres" ]; then
  echo "[entrypoint] DB_MODE=postgres -> alembic upgrade head"
  alembic -c /app/alembic.ini upgrade head
fi
cd /app/backend
exec python -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers "${WEB_CONCURRENCY:-2}" --proxy-headers
