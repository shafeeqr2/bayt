# Postgres + PostGIS from the official Postgres image and the PGDG package.
# postgis/postgis only publishes amd64 images, which run emulated (slowly) on
# Apple Silicon; this builds natively on both.
FROM postgres:17

RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-17-postgis-3 postgresql-17-pgvector \
    && rm -rf /var/lib/apt/lists/*
