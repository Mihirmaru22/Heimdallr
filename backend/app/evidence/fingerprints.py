"""Proof in a website's own code: the scripts, markup, meta tags, headers and cookies a product leaves on the
sites that run it ("js.hs-scripts.com" means the site runs HubSpot).

The fingerprints are webappanalyzer's (github.com/enthec/webappanalyzer, the open continuation of Wappalyzer's
rules, ~7,000 technologies). They are GPL-3.0, so they are not shipped with this code: the one rule file a
product's name falls in ("h.json" for HubSpot) is downloaded when a question asks for that product, and
fetched again after RULES_MAX_AGE so new and changed fingerprints are used. A product is fingerprinted only
when its own name (or an alias) is a webappanalyzer technology; products that leave no trace on websites
(an ERP, a PLM system) have none, and this check then stays silent. Only pages the crawl already read are
checked, so no extra request reaches the company's site. Cookie values and header contents beyond the
matched part are never quoted or stored.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from app.config import get_settings
from app.evidence.products import Product
from app.extract.deterministic import PageDoc

log = logging.getLogger("webdata.evidence")
RULES_URL = "https://raw.githubusercontent.com/enthec/webappanalyzer/main/src/technologies/{file}.json"
RULES_MAX_AGE = 7 * 86400  # seconds before a rule file is fetched again
MAX_HTML = 300_000  # characters of a page's HTML the html patterns run over
FULL = 100  # webappanalyzer confidence: a match counts when its patterns' confidences add up to this


@dataclass
class Pattern:
    regex: re.Pattern[str] | None  # None: the item only has to be there (a meta tag, header or cookie)
    confidence: int = FULL


@dataclass
class Rule:
    name: str
    html: list[Pattern] = field(default_factory=list)
    script_src: list[Pattern] = field(default_factory=list)
    scripts: list[Pattern] = field(default_factory=list)
    meta: dict[str, list[Pattern]] = field(default_factory=dict)
    headers: dict[str, list[Pattern]] = field(default_factory=dict)
    cookies: dict[str, list[Pattern]] = field(default_factory=dict)

    def empty(self) -> bool:
        return not (self.html or self.script_src or self.scripts or self.meta or self.headers or self.cookies)


def rule_file(name: str) -> str:
    first = name[:1].lower()
    return first if "a" <= first <= "z" else "_"


def _pattern(raw: str) -> Pattern | None:
    """"\\.hs-scripts\\.com/\;confidence:50" -> Pattern; webappanalyzer's \;version and \;confidence tags."""
    parts = str(raw).split("\;")
    confidence = FULL
    for tag in parts[1:]:
        if tag.startswith("confidence:") and tag[11:].isdigit():
            confidence = int(tag[11:])
    if not parts[0]:
        return Pattern(None, confidence)
    try:
        return Pattern(re.compile(parts[0], re.I), confidence)
    except re.error:
        return None  # a JavaScript-only regex feature: that one pattern is skipped


def _patterns(value: Any) -> list[Pattern]:
    values = value if isinstance(value, list) else [value]
    return [p for p in (_pattern(v) for v in values if isinstance(v, str)) if p is not None]


def _named(value: Any) -> dict[str, list[Pattern]]:
    if not isinstance(value, dict):
        return {}
    return {str(k).lower(): _patterns(v) for k, v in value.items()}


def parse_rule(name: str, data: dict[str, Any]) -> Rule:
    return Rule(name, html=[p for p in _patterns(data.get("html", [])) if p.regex],
                script_src=[p for p in _patterns(data.get("scriptSrc", [])) if p.regex],
                scripts=[p for p in _patterns(data.get("scripts", [])) if p.regex],
                meta=_named(data.get("meta")), headers=_named(data.get("headers")),
                cookies=_named(data.get("cookies")))


def detect(rule: Rule, doc: PageDoc, headers: list[tuple[str, str]]) -> str:
    """What on the page matches the rule, as a sentence to quote, or "" when it does not match."""
    found: list[str] = []
    total = 0

    def hit(pattern: Pattern, text: str, say: str) -> bool:
        nonlocal total
        m = pattern.regex.search(text) if pattern.regex else None
        if pattern.regex is None or m:
            total += pattern.confidence
            found.append(say.format(match=(m.group(0) if m else "")[:120].strip()))
            return True
        return False

    srcs = [s.attributes.get("src") or "" for s in doc.tree.css("script[src]")]
    for p in rule.script_src:
        for src in srcs:
            if hit(p, src, f"the page loads the script {src[:160]}"):
                break
    inline = [s.text() or "" for s in doc.tree.css("script") if not s.attributes.get("src")]
    for p in rule.scripts:
        for code in inline:
            if hit(p, code[:MAX_HTML], "a script on the page contains \"{match}\""):
                break
    html = doc.html[:MAX_HTML]
    for p in rule.html:
        hit(p, html, "the page's HTML contains \"{match}\"")
    for name, patterns in rule.meta.items():
        if name in doc.meta:
            for p in patterns:
                hit(p, doc.meta[name], f"the page's meta tag {name} is \"{doc.meta[name][:120]}\"")
    values = {}
    cookies = set()
    for key, value in headers:
        if key == "set-cookie":
            cookies.add(value.split("=", 1)[0].strip().lower())
        else:
            values.setdefault(key, value)
    for name, patterns in rule.headers.items():
        if name in values:
            for p in patterns:
                hit(p, values[name], f"the site answers with the header {name}: " + "\"{match}\"")
    for name, patterns in rule.cookies.items():
        if name in cookies:
            for p in patterns[:1]:
                total += p.confidence
                found.append(f"the site sets a cookie named {name}")  # the value is never quoted
    if total < FULL:
        return ""
    return "; ".join(dict.fromkeys(found))[:400]


class Fingerprints:
    def __init__(self, rules_dir: Path | None = None, client: httpx.AsyncClient | None = None) -> None:
        self.rules_dir = rules_dir or Path(get_settings().data_dir) / "rules" / "webappanalyzer"
        self.client = client
        self.note = ""  # why no fingerprint is used, for the run's notes

    async def _file(self, file: str) -> dict[str, Any]:
        path = self.rules_dir / f"{file}.json"
        if path.is_file() and time.time() - path.stat().st_mtime < RULES_MAX_AGE:
            return json.loads(path.read_text())
        client = self.client or httpx.AsyncClient(timeout=30, headers={"User-Agent": get_settings().user_agent})
        try:
            resp = await client.get(RULES_URL.format(file=file))
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            if path.is_file():  # an older copy is still better than none
                return json.loads(path.read_text())
            raise RuntimeError(f"the webappanalyzer fingerprints could not be downloaded ({type(exc).__name__})"
                               ) from None
        finally:
            if self.client is None:
                await client.aclose()
        self.rules_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))
        return data

    async def rules_for(self, product: Product) -> list[Rule]:
        """The fingerprints whose technology name is one of the product's names (case aside)."""
        wanted = {n.lower(): n for n in product.names if n}
        rules: list[Rule] = []
        for file in sorted({rule_file(n) for n in wanted}):
            try:
                data = await self._file(file)
            except RuntimeError as exc:
                self.note = str(exc)
                log.warning("fingerprints: %s", exc)
                return []
            for name, entry in data.items():
                if name.lower() in wanted and isinstance(entry, dict):
                    rule = parse_rule(name, entry)
                    if not rule.empty():
                        rules.append(rule)
        if not rules:
            self.note = (f"{product.name} leaves no known trace in website code (no webappanalyzer fingerprint), "
                         "so websites were not checked for it")
        return rules
