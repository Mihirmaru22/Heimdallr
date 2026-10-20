"""The version check that warns when the API, a worker or the page runs older code."""

import fnmatch

from fastapi.testclient import TestClient

from app import version


class FakeRedis:
    def __init__(self):
        self.data = {}

    def setex(self, key, _ttl, value):
        self.data[key] = value.encode() if isinstance(value, str) else value

    def scan_iter(self, pattern, count=None):
        return [k for k in self.data if fnmatch.fnmatch(k, pattern)]

    def mget(self, keys):
        return [self.data.get(k) for k in keys]

DISK = {"sha": "b" * 40, "branch": "claude/source-sec-edgar", "committed_at": "2026-10-20T10:00:00Z", "dirty": False}


def _setup(monkeypatch, api_sha, worker_shas):
    r = FakeRedis()
    monkeypatch.setattr(version, "code_on_disk", lambda: DISK)
    monkeypatch.setattr(version, "PROCESS", {"sha": api_sha, "branch": DISK["branch"], "committed_at": ""})
    for i, sha in enumerate(worker_shas):
        r.setex(f"{version.WORKER_KEY}host:{i}", 90, version.json.dumps({"sha": sha, "branch": DISK["branch"]}))
    monkeypatch.setattr(version, "worker_versions", lambda: version.__dict__["_real_worker_versions"](r))


version._real_worker_versions = version.worker_versions


def test_everything_current(monkeypatch):
    _setup(monkeypatch, DISK["sha"], [DISK["sha"]])
    report = version.report("dev")
    assert report["up_to_date"] and report["problems"] == []


def test_old_worker_api_and_page_are_named(monkeypatch):
    _setup(monkeypatch, "a" * 40, [DISK["sha"], "a" * 40])
    report = version.report("c" * 40)
    assert not report["up_to_date"]
    assert any("Restart the API" in p for p in report["problems"])
    assert any("Restart the worker" in p for p in report["problems"])
    assert any("Rebuild the frontend" in p for p in report["problems"])


def test_missing_worker_is_reported(monkeypatch):
    _setup(monkeypatch, DISK["sha"], [])
    monkeypatch.setattr(version, "get_settings", lambda: type("S", (), {"celery_eager": False})())
    assert any("No worker" in p for p in version.report()["problems"])


def test_worker_publishes_its_version():
    r = FakeRedis()
    version.publish_worker_version(r)
    (published,) = version.worker_versions(r)
    assert published["sha"] == version.PROCESS["sha"]


def test_endpoint_needs_login_and_reports(app_env, make_user, monkeypatch):
    assert TestClient(app_env).get("/api/v1/version").status_code == 401
    _setup(monkeypatch, DISK["sha"], [DISK["sha"]])
    body = make_user("v@example.test").get("/api/v1/version?frontend=dev").json()
    assert body["expected"] == DISK["sha"] and body["up_to_date"] is True
