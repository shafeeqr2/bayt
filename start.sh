#!/usr/bin/env bash
# One entry point for running Bayt locally. Run `./start.sh help` for commands.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

MIN_NODE_MAJOR=20
MIN_NODE_MINOR=9

info() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31mError:\033[0m %s\n' "$*" >&2; exit 1; }

compose() { docker compose "$@"; }

check_docker() {
  command -v docker >/dev/null 2>&1 || fail "Docker is not installed. Install Docker Desktop: https://www.docker.com/products/docker-desktop/"
  docker info >/dev/null 2>&1 || fail "Docker is installed but not running. Start Docker Desktop and try again."
  docker compose version >/dev/null 2>&1 || fail "Docker Compose v2 is missing. Update Docker Desktop."
}

check_node() {
  command -v node >/dev/null 2>&1 || fail "Node.js is not installed. Install Node $(cat frontend/.nvmrc) (e.g. 'nvm install' inside frontend/)."
  local version major minor
  version="$(node -p 'process.versions.node')"
  major="${version%%.*}"
  minor="$(echo "$version" | cut -d. -f2)"
  if (( major < MIN_NODE_MAJOR || (major == MIN_NODE_MAJOR && minor < MIN_NODE_MINOR) )); then
    fail "Node $version is too old. Need >= $MIN_NODE_MAJOR.$MIN_NODE_MINOR (recommended: $(cat frontend/.nvmrc))."
  fi
}

load_env() {
  if [[ ! -f .env ]]; then
    cp .env.example .env
    info "Created .env from .env.example"
  fi
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
}

install_frontend_deps() {
  # Reinstall whenever package-lock.json changes (e.g. after a teammate adds a package).
  local stamp=frontend/node_modules/.package-lock.json
  if [[ ! -f "$stamp" || frontend/package-lock.json -nt "$stamp" ]]; then
    info "Installing frontend dependencies"
    (cd frontend && npm ci)
  fi
}

start_services() {
  info "Starting Postgres and the API (first run builds images and seeds data, ~1 min)"
  compose up -d --build --wait || {
    compose logs --tail=50 backend
    fail "Backend failed to start. Logs above; full logs: ./start.sh logs"
  }
}

cmd_up() {
  check_docker
  check_node
  load_env
  start_services
  install_frontend_deps
  info "API:      http://localhost:${BACKEND_PORT}/docs"
  info "Frontend: http://localhost:${FRONTEND_PORT}"
  info "Ctrl+C stops the frontend. './start.sh down' stops Postgres and the API."
  cd frontend
  BACKEND_URL="http://localhost:${BACKEND_PORT}" exec npx next dev --port "${FRONTEND_PORT}"
}

cmd_backend() {
  check_docker
  load_env
  start_services
  info "API: http://localhost:${BACKEND_PORT}/docs"
}

cmd_down() {
  check_docker
  compose down
}

cmd_reset() {
  check_docker
  read -r -p "This deletes your local database and reseeds it. Continue? [y/N] " answer
  [[ "$answer" =~ ^[Yy]$ ]] || exit 0
  compose down -v
  info "City data was removed too; run './start.sh city-data' to reload it (downloads are cached)"
  cmd_up
}

cmd_logs() {
  check_docker
  compose logs -f "${@:-backend}"
}

cmd_migration() {
  [[ $# -ge 1 ]] || fail "Usage: ./start.sh migration \"describe the change\""
  check_docker
  load_env
  start_services
  compose exec backend alembic revision --autogenerate -m "$1"
  compose exec backend alembic upgrade head
  info "Migration created in backend/alembic/versions/ and applied. Review it, then commit it."
}

cmd_migrate() {
  check_docker
  load_env
  start_services
  compose exec backend alembic upgrade head
}

cmd_city_data() {
  check_docker
  load_env
  start_services
  mkdir -p data/city
  info "Loading City of Toronto open data (first run downloads ~1 GB and takes a few minutes)"
  compose run --rm importer python3 /importer/import_city_data.py "$@"
  compose exec backend python -m app.city.match
}

cmd_test() {
  check_docker
  load_env
  start_services
  compose exec backend python -m pytest "$@"
}

cmd_psql() {
  check_docker
  compose exec db psql -U bayt -d bayt
}

cmd_help() {
  cat <<'EOF'
Usage: ./start.sh [command]

  (no command)        Start everything: Postgres + API in Docker, Next.js dev server
  backend             Start only Postgres + API (no frontend)
  down                Stop Postgres + API (data is kept)
  reset               Delete the local database and reseed it from backend/seed/
  city-data [tables]  Download City of Toronto zoning, lots, addresses, permits and
                      heritage data, then match listings to it (re-run to refresh)
  test [args]         Run backend tests
  logs [service]      Follow logs (default: backend)
  migration "msg"     Autogenerate an Alembic migration from model changes and apply it
  migrate             Apply pending migrations
  psql                Open a Postgres shell
  help                Show this help
EOF
}

command="${1:-up}"
shift || true
case "$command" in
  up) cmd_up ;;
  backend) cmd_backend ;;
  down) cmd_down ;;
  reset) cmd_reset ;;
  logs) cmd_logs "$@" ;;
  migration) cmd_migration "$@" ;;
  migrate) cmd_migrate ;;
  city-data) cmd_city_data "$@" ;;
  test) cmd_test "$@" ;;
  psql) cmd_psql ;;
  help | -h | --help) cmd_help ;;
  *) cmd_help; exit 1 ;;
esac
