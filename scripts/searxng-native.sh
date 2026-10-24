#!/usr/bin/env bash
# Run the local SearXNG search (discovery source "searxng") without Docker, on macOS or Linux.
#
#   scripts/searxng-native.sh install   # once: download SearXNG and its Python packages
#   scripts/searxng-native.sh start     # run it in the background on http://127.0.0.1:8888
#   scripts/searxng-native.sh status    # is it up, and does it answer JSON searches?
#   scripts/searxng-native.sh stop
#
# Everything lives in ~/.webdata/searxng (override with WEBDATA_SEARXNG_HOME), outside this repo.
# It uses the same SearXNG version and settings file (deploy/searxng/settings.yml) as Docker Compose.
set -euo pipefail

SEARXNG_COMMIT=1c10abe2d3e4ab7ddcc4e9da1a7d07dc7ca7f8f4   # = image tag 2026.10.17-1c10abe2d in docker-compose.yml
PORT="${WEBDATA_SEARXNG_PORT:-8888}"
HOME_DIR="${WEBDATA_SEARXNG_HOME:-$HOME/.webdata/searxng}"
SRC="$HOME_DIR/src"
VENV="$HOME_DIR/venv"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SETTINGS="$REPO_ROOT/deploy/searxng/settings.yml"
PIDFILE="$HOME_DIR/searxng.pid"
LOG="$HOME_DIR/searxng.log"
URL="http://127.0.0.1:$PORT"

say() { printf '%s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

find_python() {
  for py in python3.13 python3.12 python3.11 python3.10 python3; do
    if command -v "$py" >/dev/null 2>&1 &&
       "$py" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
      echo "$py"; return
    fi
  done
  die "SearXNG needs Python 3.10 or newer (on a Mac: brew install python@3.12)"
}

running_pid() {
  [ -f "$PIDFILE" ] || return 1
  local pid; pid="$(cat "$PIDFILE")"
  kill -0 "$pid" 2>/dev/null && echo "$pid"
}

install() {
  command -v git >/dev/null 2>&1 || die "git is needed (on a Mac: xcode-select --install)"
  local py; py="$(find_python)"
  mkdir -p "$HOME_DIR"
  if [ ! -d "$SRC/.git" ]; then
    say "Downloading SearXNG..."
    git init -q "$SRC"
    git -C "$SRC" remote add origin https://github.com/searxng/searxng.git
  fi
  git -C "$SRC" fetch -q --depth 1 origin "$SEARXNG_COMMIT"
  git -C "$SRC" checkout -q --force "$SEARXNG_COMMIT"
  [ -x "$VENV/bin/python" ] || "$py" -m venv "$VENV"
  say "Installing its Python packages (a few minutes the first time)..."
  "$VENV/bin/pip" install -q -U pip setuptools wheel
  "$VENV/bin/pip" install -q -U pyyaml msgspec typing-extensions pybind11
  (cd "$SRC" && "$VENV/bin/pip" install -q --use-pep517 --no-build-isolation -e .)
  if [ ! -s "$HOME_DIR/secret" ]; then
    (umask 077; "$VENV/bin/python" -c 'import secrets; print(secrets.token_urlsafe(32))' > "$HOME_DIR/secret")
  fi
  say "Installed in $HOME_DIR. Next: scripts/searxng-native.sh start"
}

start() {
  [ -x "$VENV/bin/python" ] || die "not installed yet; run: scripts/searxng-native.sh install"
  if pid="$(running_pid)"; then say "Already running (pid $pid) on $URL"; return; fi
  say "Starting SearXNG on $URL (log: $LOG)..."
  (
    cd "$SRC"
    SEARXNG_SETTINGS_PATH="$SETTINGS" SEARXNG_SECRET="$(cat "$HOME_DIR/secret")" \
    SEARXNG_BIND_ADDRESS=127.0.0.1 SEARXNG_PORT="$PORT" SEARXNG_BASE_URL="$URL/" \
      nohup "$VENV/bin/python" -m searx.webapp >"$LOG" 2>&1 &
    echo $! > "$PIDFILE"
  )
  for _ in $(seq 1 30); do
    if curl -fsS -o /dev/null "$URL/healthz" 2>/dev/null; then
      say "Running. Add this line to backend/.env, then restart the API and the worker:"
      say "  WEBDATA_SEARXNG_URL=$URL"
      return
    fi
    running_pid >/dev/null || die "SearXNG stopped while starting; see $LOG"
    sleep 1
  done
  die "SearXNG did not answer on $URL after 30 seconds; see $LOG"
}

stop() {
  if pid="$(running_pid)"; then kill "$pid"; rm -f "$PIDFILE"; say "Stopped (pid $pid)."
  else rm -f "$PIDFILE"; say "Not running."; fi
}

status() {
  if pid="$(running_pid)"; then say "Running (pid $pid) on $URL"; else say "Not running."; return 1; fi
  local body
  body="$(curl -fsS "$URL/search?q=siemens&format=json" 2>/dev/null)" ||
    die "it is up but JSON search failed; see $LOG"
  local n
  n="$(printf '%s' "$body" | "$VENV/bin/python" -c 'import json,sys; print(len(json.load(sys.stdin).get("results", [])))')"
  if [ "$n" -gt 0 ]; then
    say "JSON search works: $n results for \"siemens\"."
  else
    say "JSON search answers, but with 0 results: the search engines it asks could not be reached or refused."
    say "Check your internet connection and the WARNING lines in $LOG."
    return 1
  fi
}

case "${1:-}" in
  install) install ;;
  start) start ;;
  stop) stop ;;
  status) status ;;
  *) say "usage: $0 install|start|status|stop"; exit 2 ;;
esac
