# Deploy

Bayt runs on one DigitalOcean droplet (Ubuntu 24.04, 2 vCPU, 4 GB) at https://bayt.andalsolutions.com.
Every push to `main` on GitHub redeploys it.

## What runs on the server

Docker Compose runs 4 containers from `docker-compose.yml` plus `docker-compose.prod.yml`:

| Service | Image | Reachable from |
|---|---|---|
| `caddy` | `caddy:2` | The internet, ports 80 and 443. Gets and renews the Let's Encrypt certificate on its own. |
| `frontend` | built from `frontend/Dockerfile` (Next.js standalone) | Caddy only, port 3000 |
| `backend` | built from `backend/Dockerfile` (FastAPI) | Caddy and the frontend only, port 8000 |
| `db` | built from `db/Dockerfile` (Postgres 17 + PostGIS + pgvector) | The backend only. Data in the `pgdata` volume. |

`deploy/Caddyfile` routes requests.
The 5 Next.js route handlers under `frontend/app/api/` go to the frontend.
The rest of `/api/*`, plus `/docs` and `/openapi.json`, go to FastAPI.
Everything else goes to the frontend.
If you add a route handler under `frontend/app/api/`, add its path to the `@next_api` matcher in the Caddyfile.

Differences from `./start.sh` on your machine:

- No host ports for Postgres or the API. `docker-compose.override.yml` adds those for development only.
- The backend has no bind mount and no file watcher (`UVICORN_RELOAD=0`).
- `CORS_ORIGINS` is the live site.
- Every service has `restart: unless-stopped`, so a reboot brings the site back.

The code lives in `/opt/bayt`, owned by the `deploy` user.
`/opt/bayt/.env` holds the settings and the model key. It is not in git.
It also sets `COMPOSE_FILE=docker-compose.yml:docker-compose.prod.yml`, so a plain `docker compose` command in `/opt/bayt` uses the production files.

## How the server was set up

Once, as root on a fresh droplet:

```bash
curl -fsSL https://raw.githubusercontent.com/shafeeqr2/bayt/main/deploy/bootstrap.sh \
  | sudo bash -s -- "ssh-ed25519 AAAA... you@laptop"
```

`deploy/bootstrap.sh` does these steps, and skips each one that is already done:

1. Installs Docker Engine and the Compose plugin from Docker's apt repository.
2. Turns on Docker log rotation and adds a 2 GB swap file.
3. Creates the `deploy` user in the `docker` group, with the SSH key you pass (or root's keys).
4. Enables `ufw` with ports 22, 80 and 443 open.
5. Clones the repo into `/opt/bayt` and writes `/opt/bayt/.env` from a template.

Then:

1. Put the model key in `/opt/bayt/.env` (`LLM_API_KEY=v1....`).
2. Point the DNS A record for `bayt.andalsolutions.com` at the droplet.
3. Run the first deploy: `sudo -iu deploy /opt/bayt/deploy/deploy.sh`.

The first deploy builds both images, starts the stack, and the backend creates the schema and seeds about 2,300 listings, the same as the first `./start.sh` run.
Expect 5 to 10 minutes.

## How auto-deploy works

`.github/workflows/deploy.yml` runs on every push to `main` (and by hand from the Actions tab):

1. `test`: installs `backend/requirements.txt` and runs `pytest`. The tests mock HTTP and the database, so no Postgres is needed.
2. `deploy`: logs in to the droplet over SSH as `deploy` and runs `/opt/bayt/deploy/deploy.sh`.

A concurrency group makes 2 pushes run one after the other, never at the same time.

`deploy/deploy.sh` is the same thing you run by hand on the server. It:

1. `git fetch` and `git reset --hard origin/main`.
2. `docker compose build --pull` and `docker compose up -d --remove-orphans`.
3. Waits for the backend health check, then runs `alembic upgrade head` (the backend already ran it on start; this confirms it).
4. `docker image prune -f` and prints the URL.

Caddy is not restarted by a deploy, so the certificate and open connections are kept.

### GitHub secrets

Set these under Settings > Secrets and variables > Actions:

| Secret | Value |
|---|---|
| `DEPLOY_HOST` | The droplet's IP address or hostname |
| `DEPLOY_USER` | `deploy` |
| `DEPLOY_SSH_KEY` | The private key whose public half is in `/home/deploy/.ssh/authorized_keys`. Make a key only for this: `ssh-keygen -t ed25519 -f bayt-deploy -N ""`. |

## Roll back

Revert the bad commit and push. The workflow deploys the revert like any other push.

```bash
git revert <sha>
git push origin main
```

To roll back without GitHub, on the server as `deploy` in `/opt/bayt`:

```bash
git reset --hard <good-sha>
docker compose up -d --build
```

The next push to `main` (or the next `deploy/deploy.sh` run) moves the server back to `origin/main`, so push the revert too.

Migrations are not undone by a rollback. Use `docker compose exec backend alembic downgrade -1` if a migration itself was the problem.

## Logs and a shell

As `deploy` in `/opt/bayt`:

```bash
docker compose ps                        # what is running and its health
docker compose logs -f                   # everything
docker compose logs -f backend           # one service (frontend, caddy, db)
docker compose exec db psql -U bayt -d bayt   # Postgres shell
```

## Backfills (the `./start.sh` subcommands)

`start.sh` is for your machine. On the server, run the same commands directly:

| On your machine | On the server, as `deploy` in `/opt/bayt` |
|---|---|
| `./start.sh profiles` | `docker compose exec backend python -m app.similar.backfill` |
| `./start.sh lot-analysis` | `docker compose exec backend python -m app.lot.backfill` then `docker compose exec backend python -m app.strategy.estimate --refresh` |
| `./start.sh estimates` | `docker compose exec backend python -m app.strategy.estimate --refresh` |
| `./start.sh city-data` | `mkdir -p data/city && docker compose run --rm importer`, then `docker compose exec backend python -m app.city.match`, `... python -m app.city.coa`, `... python -m app.strategy.estimate --refresh` |
| `./start.sh migrate` | `docker compose exec backend alembic upgrade head` |
| `./start.sh test` | `docker compose exec backend python -m pytest` |

Long jobs: run them under `nohup ... &` or in `tmux`, so an SSH drop does not stop them. The profile backfill is resumable.

## Copy your local database to the server

The house profiles, persona pitches, embeddings, photo labels, lot analyses and zoning answers take about 1 hour and a few dollars of model calls to compute.
Copy them up instead.
A full dump also carries the City of Toronto data (`city` schema, about 1 GB), so the server never needs to run the importer.

On your machine, with the local stack running:

```bash
docker exec bayt-db-1 pg_dump -U bayt -d bayt -Fc > bayt.dump
scp bayt.dump deploy@<DEPLOY_HOST>:/opt/bayt/
```

On the server, as `deploy` in `/opt/bayt`:

```bash
docker compose stop backend                    # nothing writes while we restore
docker compose cp bayt.dump db:/tmp/bayt.dump
docker compose exec db pg_restore --clean --if-exists --no-owner -U bayt -d bayt /tmp/bayt.dump
docker compose exec db rm /tmp/bayt.dump
docker compose up -d                           # the backend starts, runs alembic upgrade head, skips the seed
rm bayt.dump
```

`pg_restore` prints a few errors about extensions it cannot drop (`postgis`, `vector`). They are expected; the data is restored.
Check with:

```bash
docker compose exec db psql -U bayt -d bayt -c 'select count(*) from listing_profiles' -c 'select count(*) from lot_analyses'
```

To copy the app tables only (about 200 MB, no city data), add `--schema=public` to the `pg_dump` command. The server then needs `docker compose run --rm importer` and the match steps from the table above.

## Notes

- Docker publishes ports past `ufw`. Only Caddy publishes any, so this is fine. Do not add host ports to the production overlay.
- The frontend image build runs on the droplet. It needs about 1.5 GB of memory; the swap file covers the rest.
- To change the domain, edit `deploy/Caddyfile` and `CORS_ORIGINS` in `docker-compose.prod.yml`.
