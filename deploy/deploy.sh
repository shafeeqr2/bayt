#!/usr/bin/env bash
# Deploy the main branch on the server. Run as the `deploy` user:
#
#   /opt/bayt/deploy/deploy.sh
#
# GitHub Actions runs it on every push to main (.github/workflows/deploy.yml).
# Running it again at any time is safe. See docs/deploy.md.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BRANCH="${DEPLOY_BRANCH:-main}"
SITE_URL="https://bayt.andalsolutions.com"
HEALTH_TIMEOUT=900   # seconds. The first boot migrates and seeds the database.

info() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31mError:\033[0m %s\n' "$*" >&2; exit 1; }
compose() { docker compose -f docker-compose.yml -f docker-compose.prod.yml "$@"; }

# One deploy at a time on this server.
exec 9>/tmp/bayt-deploy.lock
flock -n 9 || fail "Another deploy is running."

[[ -f .env ]] || fail "$ROOT/.env is missing. Run deploy/bootstrap.sh first."

info "Updating the code to origin/$BRANCH"
git fetch --prune origin
git reset --hard "origin/$BRANCH"
git log -1 --format='    %h %s'

info "Building images"
compose build --pull

info "Starting services"
compose up -d --remove-orphans

info "Waiting for the API (up to $HEALTH_TIMEOUT s; the first boot seeds about 2,300 listings)"
container="$(compose ps -q backend)"
deadline=$((SECONDS + HEALTH_TIMEOUT))
until [[ "$(docker inspect -f '{{.State.Health.Status}}' "$container")" == "healthy" ]]; do
  if (( SECONDS >= deadline )); then
    compose logs --tail=50 backend
    fail "The API did not become healthy in $HEALTH_TIMEOUT s. Logs above."
  fi
  sleep 5
done

# The backend already runs this when it starts (backend/entrypoint.sh). Running
# it again confirms the schema is at head and prints nothing when it is.
info "Applying migrations"
compose exec -T backend alembic upgrade head

info "Removing old images"
docker image prune -f >/dev/null

info "Deployed $(git rev-parse --short HEAD): $SITE_URL"
