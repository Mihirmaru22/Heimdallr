"""How often each kind of page gives proof, measured, so candidate pages are read in order of what they are likely
to give.

A page's kind comes from general words in its address and search title (a customer story, a dated news item, a job
ad, a blog post or guide, a service or product page), never from which site it is on. The yield of each kind is
data: seeded from the measured runs (page_yield_seed.json) and updated with every job's outcome in
data_dir/page_yield.json, so the order follows what pages actually give. Measured 2026-10-30: customer stories gave
proof on 65% of reads, news 42%, job ads 24%, blog posts 20%, other pages 17%, service and product pages 4%.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from app.config import get_settings

SEED = Path(__file__).with_name("page_yield_seed.json")
KINDS = {
    "story": r"case[-_ ]?stud|customer|success|stories|story|testimonial|reference|client",
    "jobs": r"\bjobs?\b|career|vacanc|hiring|stellenangebot",
    "news": r"/20\d\d/|\bnews\b|newsroom|press|release|announce",
    "article": r"\bblog\b|insight|article|resource|guide|learn|knowledge|webinar|event|podcast|whitepaper|ebook",
    "offer": r"service|solution|product|pricing|feature|module|partner|implementation|consult",
}


def page_kind(url: str, title: str = "") -> str:
    """The kind of page, from its address's path and its search title; the first kind that matches, in KINDS
    order (a customer story in a news section is a story)."""
    path = url.split("://", 1)[-1].split("/", 1)[1] if "/" in url.split("://", 1)[-1] else ""
    text = f"/{path.lower()} {title.lower()}".replace("-", " ").replace("_", " ")
    return next((kind for kind, pattern in KINDS.items() if re.search(pattern, text)), "other")


class Yields:
    """Pages read and pages with proof, per kind: the seed plus every run since."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path if path is not None else Path(get_settings().data_dir) / "page_yield.json"
        self.counts = self._load()
        self.new: dict[str, dict[str, int]] = {}

    def _load(self) -> dict[str, dict[str, int]]:
        for source in (self.path, SEED):
            try:
                data = json.loads(source.read_text())
            except (OSError, ValueError):
                continue
            return {k: {"read": int(v["read"]), "proof": int(v["proof"])} for k, v in data.items()
                    if isinstance(v, dict)}
        return {}

    def rate(self, kind: str) -> float:
        c = self.counts.get(kind, {"read": 0, "proof": 0})
        return (c["proof"] + 1) / (c["read"] + 2)  # an unseen kind starts at one half

    def record(self, kind: str, proof: bool) -> None:
        c = self.new.setdefault(kind, {"read": 0, "proof": 0})
        c["read"] += 1
        c["proof"] += int(proof)

    def save(self) -> None:
        """Adds this job's outcomes to the stored counts (read again first: another job may have saved since)."""
        if not self.new:
            return
        counts = self._load()
        for kind, c in self.new.items():
            total = counts.setdefault(kind, {"read": 0, "proof": 0})
            total["read"] += c["read"]
            total["proof"] += c["proof"]
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(counts, indent=1))
        except OSError:
            return
        self.counts, self.new = counts, {}
