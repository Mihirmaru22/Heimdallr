"""The brief filled in in a browser: `osint-terminal --web`.

A single page, served from this machine only, built from the same ``FIELDS`` as the terminal form.
Submitting it starts one research run; the page then polls until the reports are written and links
them. Python's own http.server, so there is nothing to install and no traffic leaves the machine.

    osint-terminal --web                 # http://127.0.0.1:8765
    osint-terminal --web --port 9000
    osint-terminal --web --host 0.0.0.0  # only with --allow-remote, and only on a network you trust

One run at a time: while a run is going the form says so rather than starting a second.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dataclass_field
from html import escape
import json
import logging
from pathlib import Path
import threading
from typing import Any, Callable
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from argus.intake.brief import DEPTHS, EVIDENCE_FLOORS, FIELDS, FormField, ResearchBrief

logger = logging.getLogger(__name__)

PAGE_CSS = """
:root { color-scheme: light dark; --bg:#fbfbfa; --fg:#1b1b19; --muted:#6b6b66; --line:#dededa;
        --accent:#1f3864; --field:#fff; }
@media (prefers-color-scheme: dark) { :root { --bg:#17181a; --fg:#ececeb; --muted:#9a9a95;
        --line:#333436; --accent:#9fc0ff; --field:#1f2124; } }
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--fg); font:16px/1.55 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif; }
main { max-width: 46rem; margin:0 auto; padding:2.5rem 1rem 5rem; }
h1 { font-size:1.6rem; margin:0 0 .3rem; letter-spacing:-.01em; }
.lede { color:var(--muted); margin:0 0 2rem; }
fieldset { border:1px solid var(--line); border-radius:10px; margin:0 0 1.1rem; padding:1rem 1.1rem 1.2rem; background:var(--field); }
legend { font-weight:600; padding:0 .4rem; }
.help { color:var(--muted); font-size:.9rem; margin:.1rem 0 .2rem; }
.effect { color:var(--accent); font-size:.82rem; margin:0 0 .7rem; }
input[type=text], input[type=number], textarea, select { width:100%; padding:.55rem .6rem; font:inherit;
  color:inherit; background:var(--bg); border:1px solid var(--line); border-radius:7px; }
textarea { min-height:5.2rem; resize:vertical; }
.choices { display:flex; flex-wrap:wrap; gap:.4rem .9rem; }
.choices label { display:flex; gap:.4rem; align-items:center; font-size:.95rem; }
button { font:inherit; font-weight:600; padding:.7rem 1.4rem; border:0; border-radius:8px;
  background:var(--accent); color:#fff; cursor:pointer; }
@media (prefers-color-scheme: dark) { button { color:#13203a; } }
.note { border-left:3px solid var(--accent); padding:.4rem .8rem; color:var(--muted); margin:1.4rem 0; }
.err { color:#b3261e; font-weight:600; }
a { color:var(--accent); }
code { background:var(--field); border:1px solid var(--line); border-radius:4px; padding:.05rem .3rem; font-size:.9em; }
"""


def _field_html(f: FormField) -> str:
    label = escape(f.label) + (' <span class="err">*</span>' if f.required else "")
    body = ""
    if f.kind in ("text", "number"):
        kind = "number" if f.kind == "number" else "text"
        body = (f'<input type="{kind}" name="{f.name}" value="{escape(str(f.default or ""))}" '
                f'placeholder="{escape(f.placeholder)}"{" required" if f.required else ""}>')
    elif f.kind == "long_text":
        body = f'<textarea name="{f.name}" placeholder="{escape(f.placeholder)}"></textarea>'
    elif f.kind == "choice":
        options = "".join(
            f'<option value="{escape(c)}"{" selected" if c == f.default else ""}>{escape(c)}'
            + (f" — {escape(EVIDENCE_FLOORS[c])}" if c in EVIDENCE_FLOORS else "")
            + (f" — about {DEPTHS[c]} steps" if c in DEPTHS else "") + "</option>"
            for c in f.choices
        )
        body = f'<select name="{f.name}">{options}</select>'
    elif f.kind == "multi_choice":
        boxes = "".join(
            f'<label><input type="checkbox" name="{f.name}" value="{escape(c)}">{escape(c)}</label>'
            for c in f.choices
        )
        body = f'<div class="choices">{boxes}</div>'
    return (f'<fieldset><legend>{label}</legend>'
            f'<p class="help">{escape(f.help)}</p>'
            f'<p class="effect">What it changes: {escape(f.effect)}</p>{body}</fieldset>')


def form_page(error: str = "", busy_question: str = "") -> str:
    """The form itself. ``busy_question`` replaces the submit button while a run is going."""
    if busy_question:
        action = (f'<div class="note">A run is already going: <strong>{escape(busy_question)}</strong>.<br>'
                  f'<a href="/status">Watch it</a>, and fill in another form when it finishes.</div>')
    else:
        action = '<button type="submit">Start the research</button>'
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Heimdallr research brief</title><style>{PAGE_CSS}</style></head>
<body><main>
<h1>Research brief</h1>
<p class="lede">Answer what matters and leave the rest empty. Every field changes the run, and what
it changes is written under it. The filled-in form is saved beside the results, so a run can be
repeated exactly.</p>
{f'<p class="err">{escape(error)}</p>' if error else ''}
<form method="post" action="/run">
{"".join(_field_html(f) for f in FIELDS)}
{action}
</form>
<div class="note">Served from this machine only. Nothing on this page is sent anywhere but your own
Heimdallr run.</div>
</main></body></html>"""


def status_page() -> str:
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Heimdallr is researching</title><style>{PAGE_CSS}</style></head>
<body><main>
<h1 id="head">Researching…</h1>
<p class="lede" id="question"></p>
<div class="note" id="detail">Starting.</div>
<p id="links"></p>
<p><a href="/">Back to the form</a></p>
<script>
async function poll() {{
  const r = await fetch('/status.json');
  const s = await r.json();
  document.getElementById('question').textContent = s.question || '';
  document.getElementById('detail').textContent = s.detail || '';
  if (s.state === 'done' || s.state === 'failed') {{
    document.getElementById('head').textContent = s.state === 'done' ? 'Done' : 'It stopped with an error';
    document.getElementById('links').innerHTML = (s.files || [])
      .map(f => '<div><code>' + f + '</code></div>').join('');
    return;
  }}
  setTimeout(poll, 1500);
}}
poll();
</script>
</main></body></html>"""


@dataclass
class RunState:
    """What the page polls: one run at a time, and what it produced."""

    state: str = "idle"  # idle | running | done | failed
    question: str = ""
    detail: str = ""
    files: list[str] = dataclass_field(default_factory=list)
    lock: threading.Lock = dataclass_field(default_factory=threading.Lock)

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {"state": self.state, "question": self.question, "detail": self.detail, "files": list(self.files)}

    def start(self, question: str) -> None:
        with self.lock:
            self.state, self.question, self.detail, self.files = "running", question, "Researching. This takes a while.", []

    def finish(self, detail: str, files: list[str]) -> None:
        with self.lock:
            self.state, self.detail, self.files = "done", detail, files

    def fail(self, detail: str) -> None:
        with self.lock:
            self.state, self.detail = "failed", detail

    @property
    def busy(self) -> bool:
        return self.snapshot()["state"] == "running"


def _parse_form(body: str) -> dict[str, Any]:
    """Form answers, with checkbox groups kept as lists."""
    parsed = urllib.parse.parse_qs(body, keep_blank_values=True)
    answers: dict[str, Any] = {}
    for f in FIELDS:
        values = parsed.get(f.name, [])
        answers[f.name] = values if f.kind == "multi_choice" else (values[0] if values else "")
    return answers


def make_handler(run_state: RunState, runner: Callable[[ResearchBrief], list[str]],
                 brief_dir: Path) -> type[BaseHTTPRequestHandler]:
    """The request handler, given what to do with a filled-in brief."""

    class Handler(BaseHTTPRequestHandler):
        server_version = "Heimdallr"

        def log_message(self, fmt: str, *args: Any) -> None:  # quiet: the terminal shows the run
            logger.debug("%s - %s", self.address_string(), fmt % args)

        def _send(self, body: str, content_type: str = "text/html; charset=utf-8", status: int = 200) -> None:
            raw = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self) -> None:
            if self.path.startswith("/status.json"):
                self._send(json.dumps(run_state.snapshot()), "application/json")
            elif self.path.startswith("/status"):
                self._send(status_page())
            elif self.path in ("/", "/form"):
                self._send(form_page(busy_question=run_state.question if run_state.busy else ""))
            else:
                self._send("Not found", "text/plain; charset=utf-8", 404)

        def do_POST(self) -> None:
            if not self.path.startswith("/run"):
                self._send("Not found", "text/plain; charset=utf-8", 404)
                return
            if run_state.busy:
                self._send(form_page(busy_question=run_state.question), status=409)
                return
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length).decode("utf-8", "replace")
            try:
                brief = ResearchBrief.from_answers(_parse_form(body))
            except ValueError as exc:
                self._send(form_page(error=str(exc)), status=400)
                return

            brief.save(brief_dir)
            run_state.start(brief.to_objective())

            def work() -> None:
                try:
                    files = runner(brief)
                    run_state.finish("The reports are written.", files)
                except Exception as exc:  # the browser must say what happened, not hang
                    logger.exception("research run failed")
                    run_state.fail(f"{type(exc).__name__}: {exc}")

            threading.Thread(target=work, daemon=True).start()
            self.send_response(303)
            self.send_header("Location", "/status")
            self.end_headers()

    return Handler


def serve(runner: Callable[[ResearchBrief], list[str]], host: str = "127.0.0.1", port: int = 8765,
          brief_dir: str | Path = "exports/briefs", serve_forever: bool = True) -> ThreadingHTTPServer:
    """Serve the form until interrupted. ``runner`` does the research and returns the files written."""
    handler = make_handler(RunState(), runner, Path(brief_dir))
    httpd = ThreadingHTTPServer((host, port), handler)
    if serve_forever:
        print(f"Research brief form: http://{host}:{port}  (Ctrl-C to stop)")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")
        finally:
            httpd.server_close()
    return httpd
