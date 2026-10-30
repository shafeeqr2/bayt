#!/bin/sh
set -e

alembic upgrade head
python -m app.seed
python -m app.city.match --if-needed
python -m app.city.coa --if-needed
python -m app.strategy.estimate
# Development reloads on file changes (the source is bind-mounted). Production
# sets UVICORN_RELOAD=0 in docker-compose.prod.yml: the image never changes.
if [ "${UVICORN_RELOAD:-1}" = "0" ]; then
  exec uvicorn app.main:app --host 0.0.0.0 --port 8000
fi
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
