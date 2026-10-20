"""Which code each part of the app is running, so an API or worker left on old code is noticed.

Each process records the git commit it started from. The worker publishes its own to Redis on every
heartbeat; the API compares the API, the workers and the frontend with the commit currently checked
out on disk (when the code runs from a git checkout) and flags anything behind. In Docker images
there is no .git, so the commit comes from WEBDATA_BUILD_SHA / WEBDATA_BUILD_BRANCH build arguments.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import time
from pathlib import Path
from typing import Any

from app.config import get_settings

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKER_KEY = "webdata:version:worker:"
WORKER_TTL = 90  # seconds; a worker that stops heart-beating drops off the list


def _git(*args: str) -> str | None:
    try:
        # Fixed arguments, no user input.
        out = subprocess.run(["git", "-C", str(REPO_ROOT), *args],  # noqa: S603, S607
                             capture_output=True, text=True, timeout=3, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None if out.returncode == 0 else None


def code_on_disk() -> dict[str, Any] | None:
    """The commit checked out right now (None outside a git checkout)."""
    sha = _git("rev-parse", "HEAD")
    if not sha:
        return None
    return {"sha": sha, "branch": _git("rev-parse", "--abbrev-ref", "HEAD") or "",
            "committed_at": _git("log", "-1", "--format=%cI") or "", "dirty": bool(_git("status", "--porcelain"))}


def _started_from() -> dict[str, Any]:
    disk = code_on_disk()
    if disk:
        return {"sha": disk["sha"], "branch": disk["branch"], "committed_at": disk["committed_at"]}
    return {"sha": os.environ.get("WEBDATA_BUILD_SHA", "unknown"),
            "branch": os.environ.get("WEBDATA_BUILD_BRANCH", ""), "committed_at": ""}


# Computed once at import: this is the code this process loaded, whatever happens on disk later.
PROCESS = {**_started_from(), "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


def publish_worker_version(redis_client=None) -> None:
    import redis

    r = redis_client or redis.Redis.from_url(get_settings().redis_url, socket_timeout=2)
    r.setex(WORKER_KEY + socket.gethostname() + f":{os.getpid()}", WORKER_TTL,
            json.dumps({**PROCESS, "host": socket.gethostname()}))


def start_worker_heartbeat() -> None:
    """Called once when a Celery worker is ready: re-publish its version every 30 seconds."""
    import threading

    def loop() -> None:
        while True:
            try:
                publish_worker_version()
            except Exception:  # noqa: BLE001, S110 - Redis down: the API will report no worker
                pass
            time.sleep(30)

    threading.Thread(target=loop, name="version-heartbeat", daemon=True).start()


def worker_versions(redis_client=None) -> list[dict[str, Any]]:
    import redis

    try:
        r = redis_client or redis.Redis.from_url(get_settings().redis_url, socket_timeout=2)
        keys = list(r.scan_iter(WORKER_KEY + "*", count=100))
        return [json.loads(v) for v in r.mget(keys) if v] if keys else []
    except (redis.RedisError, ValueError):
        return []


def report(frontend_sha: str | None = None) -> dict[str, Any]:
    disk = code_on_disk()
    expected = disk["sha"] if disk else PROCESS["sha"]
    workers = worker_versions()
    problems = []
    if PROCESS["sha"] != expected:
        problems.append("The API is running older code than what is checked out. Restart the API.")
    if not workers and not get_settings().celery_eager:  # eager mode runs jobs inside the API
        problems.append("No worker is running (or it cannot reach Redis), so jobs will not start.")
    elif any(w.get("sha") != expected for w in workers):
        problems.append("A Celery worker is running older code than what is checked out. Restart the worker.")
    if frontend_sha and frontend_sha not in ("dev", expected):
        problems.append("This page was built from older code. Rebuild the frontend, then reload the page.")
    return {"expected": expected, "code_on_disk": disk, "api": PROCESS, "workers": workers,
            "frontend": frontend_sha, "up_to_date": not problems, "problems": problems}
