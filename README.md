# Bayt

Real estate search that gives buyers clarity before they purchase.
See the [product brief](docs/product-brief.md) for goals, users, and features.

## Quick start

You need [Docker Desktop](https://www.docker.com/products/docker-desktop/) (running) and Node.js 20.9+ (24 recommended, see `frontend/.nvmrc`).

```bash
git clone https://github.com/kkamilahmed/bayt.git
cd bayt
./start.sh
```

Then open:

- Frontend: http://localhost:3000
- API docs: http://localhost:8000/docs

The first run builds the backend image, creates the database, runs migrations, and seeds about 2,300 Toronto listings.
Later runs reuse the database and start in seconds.

## How it fits together

| Part | Tech | Runs in |
|---|---|---|
| `frontend/` | Next.js 16 (App Router, Tailwind) | Your machine, via `./start.sh` |
| `backend/` | FastAPI, SQLAlchemy 2, Alembic | Docker (`backend` service) |
| Database | Postgres 17 | Docker (`db` service), data in the `pgdata` volume |

The Next.js dev server runs outside Docker on purpose.
Next.js recommends against running it in Docker on macOS and Windows, because file watching through Docker Desktop makes Fast Refresh slow or unreliable.
The backend source is mounted into its container, so Python changes reload automatically.

The frontend talks to the API from the server side only, using `BACKEND_URL` (set by `./start.sh`).

## Everyday commands

```bash
./start.sh                     # start everything
./start.sh backend             # start only Postgres + API
./start.sh down                # stop Postgres + API (data is kept)
./start.sh reset               # wipe your local database and reseed
./start.sh logs                # follow backend logs
./start.sh psql                # open a Postgres shell
./start.sh help                # list all commands
```

If a port is already taken on your machine, change it in `.env` (created from `.env.example` on first run).
Postgres is exposed on 5433 by default so it does not clash with a local Postgres on 5432.

## Changing the database

1. Edit the models in `backend/app/models.py`.
2. Generate and apply a migration:
   ```bash
   ./start.sh migration "add rent estimate to listings"
   ```
3. Review the new file in `backend/alembic/versions/` and commit it with your model change.

Teammates get it automatically: the backend runs `alembic upgrade head` every time it starts.
If two people add migrations at the same time, Alembic will report multiple heads.
Fix it by pulling, then running `docker compose exec backend alembic merge heads -m "merge"`.

## Seed data

`backend/seed/*.json.gz` holds raw REALTOR.ca listing exports from Apify (`igolaizola/realtor-canada-scraper-ppe`).
On startup the backend seeds them into an empty database (`backend/app/seed.py`).
Vacant land and placeholder prices are skipped, and the full source payload is kept in the `raw` column.

To add a newer export:

1. Export the Apify dataset as JSON (all fields).
2. `gzip -9 -c export.json > backend/seed/<date>.json.gz`
3. `./start.sh reset`

If the same listing appears in several files, the newest file wins.

Photos are not stored locally.
The database keeps REALTOR.ca's photo URLs, which stop working when a listing comes off the market.

This data is scraped from REALTOR.ca for internal prototyping only.
Keep the repo private, and do not publish the data or photos.
