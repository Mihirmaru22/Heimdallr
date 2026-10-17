"""Check which pages cited by an LLM answer (ChatGPT, Gemini, Claude...) Heimdallr can read.

Paste one or more LLM answers, with their source links, into a text file and run:

    python -m argus.evals.llm_citation_check answers.txt [--run exports/runs/<run>] [--out report.md]

For every cited URL the script asks the same questions Heimdallr's retriever asks, on the
user's machine: does robots.txt allow our agent, does the page load, does it contain readable
text. It also reports whether a recorded Heimdallr run (``--run``) found the same page. The
summary shows whether a gap to the LLM's answer comes from pages we may not read (blocked) or
from pages we could read but did not find or did not understand.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlparse

_URL_RE = re.compile(r"https?://[^\s)\]>\"'`]+")


def extract_urls(text: str) -> list[str]:
    """Distinct URLs in pasted answers (plain or markdown links), in order, trailing punctuation removed."""
    out: list[str] = []
    for u in _URL_RE.findall(text or ""):
        u = u.rstrip(".,;:!?")
        if u not in out:
            out.append(u)
    return out


def _canon(url: str) -> str:
    p = urlparse(url)
    return f"{p.netloc.lower().removeprefix('www.')}{p.path.rstrip('/')}"


def run_urls(run_dir: Path) -> tuple[set[str], set[str]]:
    """(URLs a recorded run saw in search results, URLs it read in full)."""
    seen, read = set(), set()
    calls = run_dir / "calls.jsonl"
    if not calls.exists():
        return seen, read
    for line in calls.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        for d in entry.get("docs") or []:
            seen.add(_canon(d.get("url", "")))
        doc = entry.get("doc")
        if doc and doc.get("url"):
            read.add(_canon(doc["url"]))
            seen.add(_canon(doc["url"]))
    return seen, read


def classify(record) -> str:
    """One outcome per fetch, in the user's terms."""
    err = (record.retrieval_error or "").lower()
    if record.extraction_method == "blocked":
        if "robots" in err:
            return "refused by robots.txt"
        return "refused by Heimdallr's safety policy"
    if record.http_status == 200 and len(record.extracted_text or "") >= 200:
        return "readable"
    if record.http_status == 200:
        return "loads but little text (likely needs JavaScript or login)"
    if record.http_status in (401, 403, 429):
        return f"site refused (HTTP {record.http_status})"
    if record.http_status == 0:
        return "no connection"
    return f"HTTP {record.http_status}"


def check(urls: list[str], run_dir: Path | None = None) -> list[dict[str, str]]:
    from argus.investigation.live_web.controller import ControlledLiveWebRetriever
    from argus.investigation.live_web.models import ControlledRetrievalLimits

    limits = ControlledRetrievalLimits.deep()
    limits.max_requests_per_task = max(limits.max_requests_per_task, 2 * len(urls) + 10)
    retriever = ControlledLiveWebRetriever(limits=limits)
    seen, read = run_urls(run_dir) if run_dir else (set(), set())
    rows = []
    for url in urls:
        record = retriever._run_async(retriever.fetch_url_content(url))
        key = _canon(url)
        rows.append({
            "url": url,
            "outcome": classify(record),
            "chars": str(len(record.extracted_text or "")),
            "heimdallr": ("read" if key in read else "found in search" if key in seen else "not found") if run_dir else "",
        })
    return rows


def render(rows: list[dict[str, str]], with_run: bool) -> str:
    counts = Counter(r["outcome"] for r in rows)
    lines = ["# Pages cited by the LLM answer: can Heimdallr read them?", ""]
    lines += [f"- {k}: {v}" for k, v in counts.most_common()]
    if with_run:
        h = Counter(r["heimdallr"] for r in rows)
        lines += ["", "Heimdallr's recorded run: " + ", ".join(f"{k} {v}" for k, v in h.most_common())]
    lines += ["", "| URL | Outcome | Text chars |" + (" Heimdallr run |" if with_run else ""),
              "|---|---|---|" + ("---|" if with_run else "")]
    for r in rows:
        lines.append(f"| {r['url']} | {r['outcome']} | {r['chars']} |" + (f" {r['heimdallr']} |" if with_run else ""))
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("answers", help="Text file with pasted LLM answers and their links")
    parser.add_argument("--run", help="Recorded Heimdallr run folder for the same question")
    parser.add_argument("--out", help="Write the Markdown report here as well")
    args = parser.parse_args(argv)
    urls = extract_urls(Path(args.answers).read_text(encoding="utf-8"))
    if not urls:
        print("No links found in the answers file.", file=sys.stderr)
        return 1
    report = render(check(urls, Path(args.run) if args.run else None), with_run=bool(args.run))
    if args.out:
        Path(args.out).write_text(report, encoding="utf-8")
    sys.stdout.write(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
