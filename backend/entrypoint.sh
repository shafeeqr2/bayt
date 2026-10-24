#!/bin/sh
set -e

alembic upgrade head
python -m app.seed
python -m app.city.match --if-needed
python -m app.city.coa --if-needed
python -m app.strategy.estimate
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
