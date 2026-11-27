# Heimdallr (WebData AI) — Requirements & Prerequisites

This document outlines everything needed to set up, run, test, and develop **Heimdallr (WebData AI Phase 1)**.

---

## 1. System & Hardware Requirements

| Resource | Minimum | Recommended | Notes |
|---|---|---|---|
| **Operating System** | macOS, Linux, or Windows (WSL2) | macOS (Apple Silicon/Intel) or Linux | Docker Engine / Docker Desktop supported |
| **CPU** | 2 Cores | 4+ Cores | Crawler is I/O & network bound, not CPU bound |
| **RAM** | 4 GB free | 8 GB+ | If using Docker Desktop, allocate at least 4 GB |
| **Disk Space** | 3 GB free | 10 GB free | For Docker images, PostgreSQL volume, and exported `.xlsx` files |
| **Network** | Outbound HTTP/HTTPS (ports 80, 443) | Stable broadband | Access to target crawl sites and Wikidata SPARQL endpoint |

---

## 2. Software Prerequisites

You can run Heimdallr in one of two modes: **Docker Compose (Recommended)** or **Native Local Development**.

### Option A: Docker Setup (Recommended)
* **Docker Engine** (v24.0+) or **Docker Desktop**
* **Docker Compose v2** (`docker compose` CLI)

### Option B: Native Setup (Without Docker)
* **Python**: 3.12 or higher (`python3 --version`)
* **uv**: Astral's Python package and environment manager
  * Install: `curl -LsSf https://astral.sh/uv/install.sh | sh` (or `brew install uv`)
* **Node.js**: v20.x or higher (`node --version`)
* **npm**: v10.x or higher (`npm --version`)
* **PostgreSQL**: v14+ (v16 recommended) with the `citext` extension
* **Redis**: v6+ (v7 recommended) for task queuing and crawl rate-limiting

---

## 3. Required Environment Variables (`.env`)

Copy `.env.example` to `.env` in the project root and configure the following variables:

```sh
cp .env.example .env
```

### Essential Credentials & Secrets
| Variable | Description | Example / How to generate |
|---|---|---|
| `POSTGRES_PASSWORD` | PostgreSQL root superuser password | Strong password string |
| `WEBDATA_DB_PASSWORD` | Dedicated non-superuser password for app | Letters, digits, `-`, and `_` only |
| `WEBDATA_SECRET_KEY` | Secret key used to sign temporary export download tokens | Run: `python3 -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `WEBDATA_USER_AGENT` | Contact identifier sent in HTTP crawl headers | `WebDataAI/0.1 (+mailto:your-email@example.com)` |

### Configuration & Policy Defaults
| Variable | Default | Purpose |
|---|---|---|
| `WEBDATA_ENV` | `development` | Set to `production` when deploying live |
| `WEBDATA_COOKIE_SECURE` | `false` | Set `true` only when HTTPS is enabled |
| `WEBDATA_CORS_ORIGINS` | `["http://localhost:5173"]` | Allowed frontend origins for CORS |
| `WEBDATA_RESPECT_ROBOTS` | `true` | Enforces RFC 9309 compliance for `robots.txt` |
| `WEBDATA_PER_DOMAIN_DELAY_SECONDS` | `1.0` | Minimum delay between crawl requests per domain |
| `WEBDATA_PER_DOMAIN_CONCURRENCY` | `2` | Max concurrent worker connections per domain |
| `WEBDATA_MAX_PAGES_PER_JOB` | `2000` | Safety limit on crawled pages per job |
| `WEBDATA_MAX_DEPTH` | `3` | Maximum crawl link recursion depth |
| `WEBDATA_MAX_ACTIVE_JOBS_PER_ORG` | `3` | Concurrency quota per organization |
| `WEBDATA_MAX_PAGES_PER_ORG_MONTH` | `50000` | Monthly page crawl limit |
| `WEBDATA_EXPORT_TTL_HOURS` | `24` | Auto-expiry time for generated `.xlsx` downloads |
| `WEBDATA_RETENTION_DAYS` | `90` | Data retention policy for finished jobs |
| `WEBDATA_ALLOW_PRIVATE_TARGETS` | `[]` | Whitelist for local test domains (e.g. `["test-sites:8765"]`) |
| `WEBDATA_OPENROUTER_API_KEY` | *(Empty)* | *(Phase 2 optional)* For optional free LLM models; not needed in Phase 1 |

---

## 4. Network Ports & Services

When running, the application binds to the following local ports:

| Service | Port | Bound Address | Purpose |
|---|---|---|---|
| **Web Frontend (Nginx / Vite)** | `8080` (Docker) / `5173` (Vite) | `127.0.0.1` | Main React dashboard UI |
| **API Backend (FastAPI)** | `8000` | `127.0.0.1` | REST API (`/api`) & OpenAPI docs (`/api/docs`) |
| **PostgreSQL** | `5432` | `127.0.0.1` | Primary database |
| **Redis** | `6379` | Internal Docker / `127.0.0.1` | Celery broker & rate-limit locks |
| **Celery Worker** | N/A | Background process | Executes crawl, extraction, and xlsx generation |
| **Celery Beat** | N/A | Background process | Maintenance scheduler (stalled jobs, TTL cleanup) |
| **Test Sites (Optional)** | `8765` | `127.0.0.1` | Bundled offline crawler sandbox |

---

## 5. Technology Stack & Key Dependencies

### Backend (`backend/pyproject.toml`)
* **API & Web**: `fastapi`, `uvicorn[standard]`, `pydantic`, `pydantic-settings`, `email-validator`
* **Database & Persistence**: `sqlalchemy`, `psycopg[binary]`, `alembic` (database migrations)
* **Asynchronous Jobs**: `celery[redis]`, `redis`
* **Crawling & HTML Parsing**:
  * `httpx`: Async HTTP client with SSRF IP-pinning security
  * `selectolax`: Fast HTML parsing via Lexbor
  * `extruct`: Microdata, JSON-LD, and OpenGraph metadata extractor
  * `protego`: RFC 9309 compliant `robots.txt` parser
  * `tldextract`: URL domain and suffix normalization
  * `phonenumbers`: International phone number validation and normalization
* **Spreadsheet Generation**: `xlsxwriter` (with formula injection protection)
* **Security & Auth**: `argon2-cffi` (password hashing)
* **Dev & Testing**: `pytest`, `pytest-asyncio`, `ruff`

### Frontend (`frontend/package.json`)
* **Framework**: React 19 (`react`, `react-dom`)
* **Routing**: React Router v7 (`react-router-dom`)
* **Server State**: TanStack React Query v5 (`@tanstack/react-query`)
* **Tooling**: Vite 7, TypeScript 5.9, Nginx (Docker image)

---

## 6. Quickstart Execution Checklist

### Via Docker (Fastest)
1. **Configure Environment**:
   ```bash
   cp .env.example .env
   # Edit .env with your generated WEBDATA_SECRET_KEY and passwords
   ```
2. **Build and Start Containers**:
   ```bash
   docker compose up --build -d
   ```
3. **Create Platform Admin Account (Optional)**:
   ```bash
   docker compose exec api python -m app.cli create-admin admin@example.com
   ```
4. **Access UI**:
   Open [http://localhost:8080](http://localhost:8080) in your browser.

---

### Via Native Installation
1. **Initialize Database & Redis**:
   ```bash
   sudo -u postgres psql -c "CREATE ROLE webdata LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD 'webdata'"
   sudo -u postgres psql -c "CREATE DATABASE webdata OWNER webdata"
   sudo -u postgres psql -d webdata -c "CREATE EXTENSION IF NOT EXISTS citext"
   ```
2. **Backend Setup**:
   ```bash
   cd backend
   uv sync
   uv run alembic upgrade head
   uv run uvicorn app.main:app --reload --port 8000
   ```
3. **Start Worker (In a separate terminal)**:
   ```bash
   cd backend
   uv run celery -A app.worker.celery_app worker --loglevel=INFO
   ```
4. **Frontend Setup (In a separate terminal)**:
   ```bash
   cd frontend
   npm ci
   npm run dev
   ```
   Open [http://localhost:5173](http://localhost:5173).
