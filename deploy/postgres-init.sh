#!/bin/sh
# Runs once, when the Postgres volume is first created. The app connects as a role that is NOT a
# superuser and cannot bypass row-level security; superusers would silently skip tenant isolation.
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<SQL
CREATE ROLE webdata LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD '${WEBDATA_DB_PASSWORD}';
CREATE DATABASE webdata OWNER webdata;
SQL
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname webdata -c "CREATE EXTENSION IF NOT EXISTS citext;"
