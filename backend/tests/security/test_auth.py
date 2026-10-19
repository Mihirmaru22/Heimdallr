"""Authentication, sessions, CSRF and admin surface."""

from fastapi.testclient import TestClient


def test_requires_login(app_env):
    client = TestClient(app_env)
    assert client.get("/api/v1/orgs").status_code == 401
    assert client.get("/api/v1/auth/me").status_code == 401


def test_csrf_required_for_writes(make_user):
    alice = make_user("alice@example.com")
    r = alice.client.post(alice.org("/projects"), json={"name": "x"})  # no X-CSRF-Token
    assert r.status_code == 403 and r.json()["code"] == "csrf_failed"
    r = alice.client.post(alice.org("/projects"), json={"name": "x"}, headers={"X-CSRF-Token": "wrong"})
    assert r.status_code == 403
    assert alice.post(alice.org("/projects"), json={"name": "x"}).status_code == 201


def test_session_cookie_flags_and_storage(make_user):
    alice = make_user("alice@example.com")
    cookie = next(c for c in alice.client.cookies.jar if c.name == "wd_session")
    assert cookie.has_nonstandard_attr("HttpOnly") or cookie._rest.get("HttpOnly") is not None
    from sqlalchemy import select

    from app.db import session_scope
    from app.models import AuthSession

    with session_scope() as db:
        stored = [s.token_hash for s in db.execute(select(AuthSession)).scalars()]
    assert cookie.value not in stored  # only a hash of the token is stored


def test_login_logout_and_bad_password(make_user, app_env):
    make_user("alice@example.com", password="correct horse battery")
    client = TestClient(app_env)
    bad = client.post("/api/v1/auth/login", json={"email": "alice@example.com", "password": "wrong password"})
    assert bad.status_code == 401
    unknown = client.post("/api/v1/auth/login", json={"email": "nobody@example.com", "password": "whatever123"})
    assert unknown.status_code == 401 and unknown.json()["detail"] == bad.json()["detail"]
    ok = client.post("/api/v1/auth/login", json={"email": "ALICE@example.com", "password": "correct horse battery"})
    assert ok.status_code == 200
    csrf = ok.json()["csrf_token"]
    assert client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf}).status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401


def test_login_rate_limit(make_user, app_env):
    make_user("alice@example.com")
    client = TestClient(app_env)
    codes = [client.post("/api/v1/auth/login", json={"email": "alice@example.com", "password": "bad-password"}
                         ).status_code for _ in range(12)]
    assert codes[-1] == 429


def test_duplicate_registration(make_user, app_env):
    make_user("alice@example.com")
    r = TestClient(app_env).post("/api/v1/auth/register", json={"email": "alice@example.com",
                                                                "password": "another password"})
    assert r.status_code == 409


def test_admin_routes_hidden_from_non_admins(make_user):
    alice = make_user("alice@example.com")
    assert alice.get("/api/v1/admin/orgs").status_code == 404
    assert alice.get("/api/v1/admin/users").status_code == 404


def test_admin_can_lower_limits_and_block_domains(make_user, crawl_env):
    from sqlalchemy import update

    from app.db import session_scope
    from app.models import User

    admin = make_user("admin@example.com")
    alice = make_user("alice@example.com")
    with session_scope(bypass=True) as db:
        db.execute(update(User).where(User.email == "admin@example.com").values(is_platform_admin=True))
    r = admin.patch(f"/api/v1/admin/orgs/{alice.org_id}", json={"limits": {"max_active_jobs_per_org": 0}})
    assert r.status_code == 200 and r.json()["limits"]["max_active_jobs_per_org"] == 0
    project = alice.post(alice.org("/projects"), json={"name": "p"}).json()
    spec = {"fields": [{"name": "page_title", "type": "string", "semantic": "page_title"}],
            "crawl": {"start_urls": [crawl_env["url"]("acme-security.test")]}}
    schema = alice.post(alice.org(f"/projects/{project['id']}/schemas"), json={"spec": spec}).json()
    r = alice.post(alice.org("/jobs"), json={"schema_id": schema["id"]})
    assert r.status_code == 429 and r.json()["code"] == "quota_active_jobs"

    admin.patch(f"/api/v1/admin/orgs/{alice.org_id}", json={"limits": {}})
    assert admin.post("/api/v1/admin/domain-policies", json={"domain": "acme-security.test",
                                                            "reason": "opt-out"}).status_code == 201
    job = alice.post(alice.org("/jobs"), json={"schema_id": schema["id"]}).json()
    assert job["state"] == "failed"
    urls = alice.get(alice.org(f"/jobs/{job['id']}/urls")).json()["items"]
    assert urls and all(u["status"] == "blocked_policy" for u in urls)
