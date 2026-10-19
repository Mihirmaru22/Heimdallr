# Running WebData AI locally

Everything runs on your machine. No cloud account, paid API key or AI model is needed for
Phase 1: discovery uses your start URLs or Wikidata (free, no key), extraction is rule-based,
and the Excel file is generated locally.

## Hardware

| | Minimum | Comfortable |
|---|---|---|
| CPU | 2 cores | 4 cores |
| RAM | 4 GB free (Docker Desktop: give it 4 GB) | 8 GB |
| Disk | 3 GB for images + data | 10 GB |

The crawler is network-bound, not CPU-bound. A 500-site job at the default politeness settings
(1 request per second per site, 2 workers) takes tens of minutes, mostly waiting on websites.

## Option A: Docker Compose (recommended)

Requirements: Docker with Compose v2 (Docker Desktop on macOS/Windows, or Docker Engine on Linux).

```sh
cp .env.example .env
# edit .env: replace every CHANGE-ME value (see "Environment variables" below)
docker compose up --build -d
docker compose exec api python -m app.cli create-admin you@example.com   # optional: platform admin
```

Open <http://localhost:8080>, create an account, create a project, describe what you want,
review the generated fields, run the crawl, then export to Excel.

Services (all bound to 127.0.0.1 only):

| Service | What it does | Port |
|---|---|---|
| `web` | the React app, served by nginx, which also proxies `/api` | 8080 |
| `api` | FastAPI; runs database migrations on start | 8000 (API docs at `/api/docs`) |
| `worker` | Celery worker: crawling, extraction, Excel files | – |
| `beat` | re-queues stalled jobs every 2 min, deletes expired exports and old jobs | – |
| `postgres` | Postgres 16; the app uses a non-superuser role so row-level security applies | 5432 |
| `redis` | task queue and per-site politeness locks | – |

### Trying it offline with the bundled test websites

```sh
echo 'WEBDATA_ALLOW_PRIVATE_TARGETS=["test-sites:8765"]' >> .env
docker compose --profile demo up -d
```

Then use `http://test-sites:8765/` as a start URL. The test site has structured data, a contact
page, a pricing page, a robots.txt that disallows `/private/`, and broken links.

## Option B: without Docker

Requirements: Python 3.12+, [uv](https://docs.astral.sh/uv/), Node 20+, Postgres 14+, Redis 6+.

```sh
# 1. Database: an app role that is NOT a superuser (superusers bypass row-level security)
sudo -u postgres psql -c "CREATE ROLE webdata LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD 'webdata'"
sudo -u postgres psql -c "CREATE DATABASE webdata OWNER webdata"
sudo -u postgres psql -d webdata -c "CREATE EXTENSION IF NOT EXISTS citext"

# 2. Backend
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000              # terminal 1
uv run celery -A app.worker.celery_app worker --loglevel=INFO  # terminal 2
uv run celery -A app.worker.celery_app beat                    # terminal 3 (optional)

# 3. Frontend
cd ../frontend
npm ci
npm run dev                                                    # http://localhost:5173
```

Settings are read from environment variables or `backend/.env` (same names as `.env.example`;
`WEBDATA_DATABASE_URL` defaults to `postgresql+psycopg://webdata:webdata@localhost:5432/webdata`).
For a single-process demo without a worker, set `WEBDATA_CELERY_EAGER=true`; jobs then run
inside the API request.

### Running the tests

```sh
sudo -u postgres psql -c "CREATE DATABASE webdata_test OWNER webdata"
sudo -u postgres psql -d webdata_test -c "CREATE EXTENSION IF NOT EXISTS citext"
cd backend && uv run pytest -q
```

The tests start the local test websites themselves and point the crawler at them through a test
DNS resolver; they make no internet requests. Tests that need Postgres are skipped if it is not
reachable.

## Environment variables

All backend settings use the `WEBDATA_` prefix. The important ones:

| Variable | Default | Notes |
|---|---|---|
| `WEBDATA_SECRET_KEY` | dev placeholder | Signs download links. Must be long and random; startup refuses the placeholder when `WEBDATA_ENV=production`. |
| `WEBDATA_DATABASE_URL` | local `webdata` DB | Set by Compose. |
| `WEBDATA_REDIS_URL` | `redis://localhost:6379/0` | Set by Compose. |
| `WEBDATA_COOKIE_SECURE` | `false` | `true` only when served over HTTPS. |
| `WEBDATA_USER_AGENT` | WebDataAI/0.1 | Put a real contact address here; site owners use it. |
| `WEBDATA_RESPECT_ROBOTS` | `true` | Leave on. |
| `WEBDATA_PER_DOMAIN_DELAY_SECONDS` | `1.0` | Minimum gap between requests to one host (robots.txt `Crawl-delay` can raise it, up to 30 s). |
| `WEBDATA_PER_DOMAIN_CONCURRENCY` | `2` | |
| `WEBDATA_MAX_PAGES_PER_JOB`, `WEBDATA_MAX_DEPTH`, `WEBDATA_MAX_ACTIVE_JOBS_PER_ORG`, `WEBDATA_MAX_PAGES_PER_ORG_MONTH`, `WEBDATA_MAX_RECORDS_PER_JOB`, `WEBDATA_MAX_EXPORT_ROWS` | see `.env.example` | Platform ceilings; admins can lower them per organization. |
| `WEBDATA_EXPORT_TTL_HOURS` | `24` | Export files are deleted after this. |
| `WEBDATA_RETENTION_DAYS` | `90` | Finished jobs and their data are deleted after this (per-org override). |
| `WEBDATA_ALLOW_PRIVATE_TARGETS` | `[]` | `host:port` pairs the crawler may reach even though they are private. Only for local test sites. |
| `WEBDATA_CRAWL_PROXY` | empty | Send crawler traffic through an HTTP proxy (sandboxes). Destinations are still checked, but the proxy does the final DNS lookup, so do not use it in production. |
| `WEBDATA_CELERY_EAGER` | `false` | Run tasks inline (tests, demos). |

## Troubleshooting

- **`password authentication failed for user "webdata"`** – the Postgres volume was created with a
  different password. Either restore the old value in `.env` or reset: `docker compose down -v`
  (deletes all data).
- **Every start URL is "blocked"** – the plan preview shows why. Private, loopback and cloud-metadata
  addresses are refused on purpose, as are ports other than 80/443. For local test sites use
  `WEBDATA_ALLOW_PRIVATE_TARGETS`.
- **Pages show "blocked robots"** – the site's robots.txt disallows them, or robots.txt returned a
  5xx error or could not be reached (treated as "disallow everything", per RFC 9309).
- **Job stuck in "queued"** – the worker is not running or cannot reach Redis:
  `docker compose logs worker`.
- **Wikidata discovery fails with a rate-limit message** – Wikidata's public endpoint limits heavy
  use; wait a minute and retry the job, or supply start URLs instead.
- **Download link says expired** – links last five minutes; reload the job page for a fresh one.
- **Port already in use** – change the left side of the `ports:` mapping in `docker-compose.yml`.
