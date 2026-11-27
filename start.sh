#!/usr/bin/env bash
set -e

# Heimdallr (WebData AI) - All-In-One Runner Script
# Launches Backend API, Celery Worker, and Frontend in a single terminal.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

# ANSI Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m' # No Color

echo -e "${BOLD}${BLUE}====================================================${NC}"
echo -e "${BOLD}${BLUE}   Starting Heimdallr (WebData AI) Stack            ${NC}"
echo -e "${BOLD}${BLUE}====================================================${NC}"

# Display current git commit so you know exactly which code is being run
if git rev-parse --is-inside-work-tree &>/dev/null; then
  BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
  COMMIT=$(git log -1 --format="%h - %s (%cr)" 2>/dev/null || echo "unknown")
  echo -e "  ${BOLD}Branch:${NC}  ${GREEN}$BRANCH${NC}"
  echo -e "  ${BOLD}Commit:${NC}  ${GREEN}$COMMIT${NC}"
  echo -e "${BLUE}----------------------------------------------------${NC}"
fi

# 1. Helper functions for thorough process cleanup
cleanup_port() {
  local port=$1
  local pids
  pids=$(lsof -ti :"$port" 2>/dev/null || true)
  if [ -n "$pids" ]; then
    echo -e "${YELLOW}Port $port is in use. Stopping process(es): $pids...${NC}"
    kill $pids 2>/dev/null || true
    sleep 0.5
    # Force kill if still holding the port
    pids=$(lsof -ti :"$port" 2>/dev/null || true)
    if [ -n "$pids" ]; then
      kill -9 $pids 2>/dev/null || true
    fi
  fi
}

stop_celery() {
  local pids
  pids=$(pgrep -f "app.worker.celery_app" 2>/dev/null || true)
  if [ -n "$pids" ]; then
    echo -e "${YELLOW}Stopping existing Celery worker(s): $pids...${NC}"
    kill $pids 2>/dev/null || true
    # Wait up to 3 seconds for graceful shutdown
    for _ in {1..6}; do
      if ! pgrep -f "app.worker.celery_app" &>/dev/null; then
        break
      fi
      sleep 0.5
    done
    # Force kill any lingering worker processes
    pkill -9 -f "app.worker.celery_app" 2>/dev/null || true
  fi
}

clean_redis_version_keys() {
  if redis-cli ping &>/dev/null; then
    redis-cli eval "for _,k in ipairs(redis.call('keys','webdata:version:worker:*')) do redis.call('del',k) end" 0 2>/dev/null || true
  fi
}

echo -e "${BLUE}[1/4] Stopping any existing services...${NC}"
cleanup_port 8000
cleanup_port 5173
stop_celery
pkill -f "node.*vite" 2>/dev/null || true
clean_redis_version_keys

# 2. Check and ensure PostgreSQL, Redis & SearXNG services are running
echo -e "${BLUE}[2/4] Checking PostgreSQL, Redis, and SearXNG services...${NC}"
if ! pg_isready -q 2>/dev/null; then
  echo -e "${YELLOW}Starting PostgreSQL via Homebrew...${NC}"
  brew services start postgresql@16 2>/dev/null || brew services start postgresql 2>/dev/null || true
  sleep 2
fi

if ! redis-cli ping &>/dev/null; then
  echo -e "${YELLOW}Starting Redis via Homebrew...${NC}"
  brew services start redis 2>/dev/null || true
  sleep 1
fi

if [ -f "$ROOT_DIR/scripts/searxng-native.sh" ]; then
  if [ -x "$HOME/.webdata/searxng/venv/bin/python" ]; then
    "$ROOT_DIR/scripts/searxng-native.sh" start 2>/dev/null || true
    if [ -f "$ROOT_DIR/backend/.env" ] && ! grep -q "WEBDATA_SEARXNG_URL" "$ROOT_DIR/backend/.env"; then
      echo 'WEBDATA_SEARXNG_URL=http://127.0.0.1:8888' >> "$ROOT_DIR/backend/.env"
    fi
  else
    echo -e "${YELLOW}Note: SearXNG not installed natively yet. (Run './scripts/searxng-native.sh install' if needed)${NC}"
  fi
fi
echo -e "${GREEN}✓ Auxiliary services (PostgreSQL, Redis, SearXNG) are active.${NC}"

# 3. Clean stale bytecode, sync dependencies, and apply migrations
echo -e "${BLUE}[3/4] Syncing dependencies & checking database schema...${NC}"
# Remove any stale bytecode (.pyc) that might reference deleted or renamed code
find "$ROOT_DIR/backend/app" -type f -name "*.pyc" -delete 2>/dev/null || true

# Sync python environment in case git pull added new dependencies
(cd "$ROOT_DIR/backend" && uv sync --quiet)

# Clean stale Vite pre-bundling caches
rm -rf "$ROOT_DIR/frontend/.vite" "$ROOT_DIR/frontend/node_modules/.vite" 2>/dev/null || true

# Ensure frontend dependencies exist
if [ ! -d "$ROOT_DIR/frontend/node_modules" ]; then
  echo -e "${YELLOW}Installing frontend dependencies (npm install)...${NC}"
  (cd "$ROOT_DIR/frontend" && npm install)
fi

# Run database migrations
if (cd "$ROOT_DIR/backend" && uv run alembic upgrade head); then
  echo -e "${GREEN}✓ Database schema is up to date.${NC}"
else
  echo -e "${RED}✗ Alembic database migration failed! Check error above.${NC}"
  exit 1
fi

# 4. Process tracking and graceful shutdown
API_PID=""
WORKER_PID=""
FRONTEND_PID=""
CLEANUP_CALLED=0

cleanup() {
  if [ "$CLEANUP_CALLED" -eq 1 ]; then
    return
  fi
  CLEANUP_CALLED=1
  trap - SIGINT SIGTERM EXIT

  echo ""
  echo -e "${YELLOW}Stopping all Heimdallr services...${NC}"

  for pid in "$API_PID" "$WORKER_PID" "$FRONTEND_PID"; do
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
  done

  stop_celery
  cleanup_port 8000
  cleanup_port 5173
  clean_redis_version_keys

  echo -e "${GREEN}All services stopped cleanly.${NC}"
  exit 0
}
trap cleanup SIGINT SIGTERM EXIT

# 5. Launch Backend, Celery Worker, and Frontend
# Note: 'exec' ensures the PID is the actual process (not a wrapper subshell)
echo -e "${BLUE}[4/4] Launching Backend, Celery Worker, and Frontend...${NC}"

# API and worker output is shown here and also appended to backend/var/logs/
LOG_DIR="$ROOT_DIR/backend/var/logs"
mkdir -p "$LOG_DIR"
for log in api worker; do
  echo "===== start.sh run $(date '+%Y-%m-%d %H:%M:%S %z') ${BRANCH:-} ${COMMIT:-} =====" >> "$LOG_DIR/$log.log"
done

# Backend API (port 8000)
(cd "$ROOT_DIR/backend" && exec > >(tee -a "$LOG_DIR/api.log") 2>&1 && exec uv run uvicorn app.main:app --reload --port 8000) &
API_PID=$!

# Celery Worker (with --pool=threads for macOS compatibility)
(cd "$ROOT_DIR/backend" && exec > >(tee -a "$LOG_DIR/worker.log") 2>&1 && exec uv run celery -A app.worker.celery_app worker --pool=threads --loglevel=INFO) &
WORKER_PID=$!

# Frontend (port 5173, with --force to ignore stale cache across branches)
(cd "$ROOT_DIR/frontend" && exec npm run dev -- --force) &
FRONTEND_PID=$!

sleep 2

echo -e ""
echo -e "${BOLD}${GREEN}====================================================${NC}"
echo -e "${BOLD}${GREEN}   Heimdallr is running!                            ${NC}"
echo -e "${BOLD}${GREEN}====================================================${NC}"
echo -e "  ${BOLD}Web UI:${NC}       ${BLUE}http://localhost:5173${NC}"
echo -e "  ${BOLD}API Docs:${NC}     ${BLUE}http://localhost:8000/api/docs${NC}"
echo -e "  ${BOLD}Backend API:${NC}  ${BLUE}http://localhost:8000${NC}"
if curl -fsS -o /dev/null "http://127.0.0.1:8888/healthz" 2>/dev/null; then
  echo -e "  ${BOLD}SearXNG:${NC}      ${BLUE}http://127.0.0.1:8888${NC}"
fi
echo -e "${YELLOW}Press Ctrl+C at any time to stop all services.${NC}"
echo -e "----------------------------------------------------"
echo -e ""

# Wait for processes
wait
