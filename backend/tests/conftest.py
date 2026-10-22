"""Shared fixtures. Database tests use the webdata_test database (migrated with Alembic) and are
skipped when Postgres is not reachable, so the pure unit tests still run anywhere."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("WEBDATA_ENV", "test")
os.environ.setdefault("WEBDATA_DATABASE_URL", "postgresql+psycopg://webdata:webdata@localhost:5432/webdata_test")
os.environ.setdefault("WEBDATA_DATA_DIR", tempfile.mkdtemp(prefix="webdata-test-"))
os.environ.setdefault("WEBDATA_PER_DOMAIN_DELAY_SECONDS", "0")
os.environ.setdefault("WEBDATA_SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("WEBDATA_COOKIE_SECURE", "false")

import email_validator  # noqa: E402
import pytest  # noqa: E402

# The local test websites use the reserved .test TLD; real crawls keep rejecting it in emails.
email_validator.SPECIAL_USE_DOMAIN_NAMES = [d for d in email_validator.SPECIAL_USE_DOMAIN_NAMES if d != "test"]

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "test-sites"))


def _db_available() -> bool:
    from sqlalchemy import text

    from app.db import engine

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:  # noqa: BLE001
        return False


@pytest.fixture(scope="session")
def database():
    if not _db_available():
        pytest.skip("Postgres test database is not reachable")
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "migrations"))
    command.upgrade(cfg, "head")
    return True


@pytest.fixture
def db_clean(database):
    """Empty every table before the test (TRUNCATE is not subject to row-level security)."""
    from sqlalchemy import text

    from app.db import Base, engine

    names = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture(scope="session")
def sites():
    """The local test websites, served on 127.0.0.1 with Host-based virtual hosting."""
    import server

    srv, port = server.start(0)
    yield {"port": port, "server": server}
    srv.shutdown()


def test_resolver(host: str, port: int) -> list[str]:
    from app.crawl.netguard import BlockedDestination

    if host.endswith(".test"):
        return ["127.0.0.1"]
    raise BlockedDestination(f"DNS lookup failed for {host} (offline test resolver)")


@pytest.fixture
def crawl_env(sites, monkeypatch):
    """Let the crawler reach the *.test sites on the local port, and nothing else private."""
    from app.config import get_settings

    port = sites["port"]
    hosts = ["acme-security.test", "acme-mirror.test", "globex.test", "blocked.test", "flaky.test", "initech.test",
             "hooli.test", "acme-old.test", "loader.test"]
    monkeypatch.setattr(get_settings(), "allow_private_targets", [f"{h}:{port}" for h in hosts])
    sites["server"].Handler.requests_seen.clear()
    return {"port": port, "resolver": test_resolver, "requests": sites["server"].Handler.requests_seen,
            "url": lambda host, path="/": f"http://{host}:{port}{path}"}


class Api:
    """A signed-in browser: keeps the session cookie and sends the CSRF header on writes."""

    def __init__(self, client, csrf: str, me: dict) -> None:
        self.client, self.csrf, self.me = client, csrf, me
        self.org_id = me["organizations"][0]["id"]

    def _h(self, headers=None):
        return {"X-CSRF-Token": self.csrf, **(headers or {})}

    def get(self, path, **kw):
        return self.client.get(path, **kw)

    def post(self, path, json=None, headers=None, **kw):
        return self.client.post(path, json=json, headers=self._h(headers), **kw)

    def put(self, path, json=None, **kw):
        return self.client.put(path, json=json, headers=self._h(), **kw)

    def patch(self, path, json=None, **kw):
        return self.client.patch(path, json=json, headers=self._h(), **kw)

    def delete(self, path, **kw):
        return self.client.delete(path, headers=self._h(), **kw)

    def org(self, path=""):
        return f"/api/v1/orgs/{self.org_id}{path}"


@pytest.fixture
def app_env(db_clean, monkeypatch):
    """The FastAPI app with background tasks run inline (jobs use the offline test resolver)."""
    from app.crawl import netguard
    from app.services import exports, pipeline
    from app.worker import tasks

    monkeypatch.setattr(netguard, "resolve", test_resolver)

    monkeypatch.setattr(tasks.run_job, "delay",
                        lambda job_id: pipeline.run_job(__import__("uuid").UUID(job_id), resolver=test_resolver))
    monkeypatch.setattr(tasks.build_export, "delay",
                        lambda export_id: exports.build(__import__("uuid").UUID(export_id)))
    from app.main import create_app

    return create_app()


@pytest.fixture
def make_user(app_env):
    from fastapi.testclient import TestClient

    def _make(email: str, password: str = "correct horse battery", org: str = "") -> Api:
        client = TestClient(app_env)
        r = client.post("/api/v1/auth/register", json={"email": email, "password": password,
                                                       "organization_name": org})
        assert r.status_code == 201, r.text
        body = r.json()
        return Api(client, body["csrf_token"], body)

    return _make
