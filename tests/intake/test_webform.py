"""The browser form: one page from the same fields, one run at a time, honest about failures."""

import json
import threading
import urllib.error
import urllib.request

import pytest

from argus.intake.brief import FIELDS, ResearchBrief
from argus.intake.webform import RunState, form_page, make_handler, serve
from http.server import ThreadingHTTPServer


@pytest.fixture
def server(tmp_path):
    """A live form on a free port, with a runner the test controls."""
    calls: list[ResearchBrief] = []
    release = threading.Event()
    state = RunState()

    def runner(brief):
        calls.append(brief)
        release.wait(timeout=5)
        if brief.criterion == "fail":
            raise RuntimeError("the run broke")
        return ["/tmp/report.xlsx"]

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(state, runner, tmp_path))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", calls, release, state, tmp_path
    release.set()
    httpd.shutdown()
    httpd.server_close()


def post(url, data):
    body = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in data)
    request = urllib.request.Request(f"{url}/run", data=body.encode(), method="POST")
    return urllib.request.urlopen(request, timeout=5)


import urllib.parse  # noqa: E402  (used by post)

FILLED = [("looking_for", "hospitals"), ("criterion", "use Epic"), ("where", "Ohio"),
          ("attributes", "website"), ("evidence_floor", "quoted"), ("depth", "quick")]


def test_the_page_shows_every_field_and_what_it_changes():
    from html import escape

    page = form_page()
    for f in FIELDS:
        assert escape(f.label) in page and escape(f.effect) in page
    assert 'name="looking_for"' in page and "<select name=\"depth\">" in page
    assert "this machine only" in page


def test_submitting_the_form_starts_one_run_and_saves_the_brief(server):
    url, calls, release, state, brief_dir = server
    response = post(url, FILLED)
    assert response.status == 200  # followed the redirect to /status
    assert "Researching" in response.read().decode()

    for _ in range(50):
        if calls:
            break
        threading.Event().wait(0.05)
    assert calls and calls[0].looking_for == "hospitals"
    assert calls[0].attributes == ["website"]
    saved = list(brief_dir.glob("*.json"))
    assert saved and json.loads(saved[0].read_text())["criterion"] == "use Epic"

    status = json.loads(urllib.request.urlopen(f"{url}/status.json", timeout=5).read())
    assert status["state"] == "running" and "hospitals" in status["question"]

    release.set()
    for _ in range(60):
        status = json.loads(urllib.request.urlopen(f"{url}/status.json", timeout=5).read())
        if status["state"] == "done":
            break
        threading.Event().wait(0.05)
    assert status["state"] == "done" and status["files"] == ["/tmp/report.xlsx"]


def test_a_second_run_is_refused_while_one_is_going(server):
    url, calls, release, _, _ = server
    post(url, FILLED)
    for _ in range(50):
        if calls:
            break
        threading.Event().wait(0.05)
    with pytest.raises(urllib.error.HTTPError) as caught:
        post(url, FILLED)
    assert caught.value.code == 409
    assert "already going" in caught.value.read().decode()


def test_an_unusable_form_comes_back_with_the_reason_not_a_crash(server):
    url, calls, _, _, _ = server
    with pytest.raises(urllib.error.HTTPError) as caught:
        post(url, [("looking_for", "hospitals"), ("depth", "quick")])
    assert caught.value.code == 400
    assert "What must be true of them? is required" in caught.value.read().decode()
    assert not calls


def test_a_run_that_breaks_says_so_on_the_page(server):
    url, calls, release, _, _ = server
    post(url, [("looking_for", "hospitals"), ("criterion", "fail"), ("depth", "quick")])
    for _ in range(50):
        if calls:
            break
        threading.Event().wait(0.05)
    release.set()
    for _ in range(60):
        status = json.loads(urllib.request.urlopen(f"{url}/status.json", timeout=5).read())
        if status["state"] == "failed":
            break
        threading.Event().wait(0.05)
    assert status["state"] == "failed" and "the run broke" in status["detail"]


def test_serving_beyond_this_machine_needs_saying_so():
    from argus.terminal import serve_brief_form

    with pytest.raises(ValueError, match="allow-remote"):
        serve_brief_form(host="0.0.0.0", port=0)


def test_the_server_binds_this_machine_only_by_default(tmp_path):
    httpd = serve(lambda brief: [], host="127.0.0.1", port=0, brief_dir=tmp_path, serve_forever=False)
    try:
        assert httpd.server_address[0] == "127.0.0.1"
    finally:
        httpd.server_close()
