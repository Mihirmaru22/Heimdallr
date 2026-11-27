"""Passive technology fingerprints, compliance badges, DNS/MX SaaS signals, and job-ad tech into kb.company_tech."""

from __future__ import annotations

import asyncio
import json
import re
import time
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from app.config import get_settings
from app.evidence.fingerprints import RULES_MAX_AGE, RULES_URL, Rule, detect, parse_rule
from app.extract.deterministic import parse_page
from app.kb.homepages import PARSE_CHARS

SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS kb;
CREATE TABLE IF NOT EXISTS kb.company_tech (
    domain text NOT NULL,
    tech text NOT NULL,
    category text NOT NULL,
    source text NOT NULL,
    evidence text,
    detected_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (domain, tech, source)
);
CREATE INDEX IF NOT EXISTS company_tech_tech_idx ON kb.company_tech (tech);
CREATE INDEX IF NOT EXISTS company_tech_cat_idx ON kb.company_tech (category);
CREATE TABLE IF NOT EXISTS kb.company_dns_run (
    domain text PRIMARY KEY,
    mx_hosts text,
    checked_at timestamptz NOT NULL DEFAULT now()
);
"""

CATS_URL = "https://raw.githubusercontent.com/enthec/webappanalyzer/main/src/categories.json"
MAX_TEXT_SCAN = 200_000
MAX_INLINE_SCAN = 60_000

# Standardized security / quality certification patterns.
COMPLIANCE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("SOC 2", re.compile(r"\bSOC\s*[- ]?2\b(?:\s+Type\s+[I12]+)?", re.I)),
    ("SOC 1", re.compile(r"\bSOC\s*[- ]?1\b(?:\s+Type\s+[I12]+)?", re.I)),
    ("ISO 27001", re.compile(r"\bISO(?:/IEC)?\s*27001\b", re.I)),
    ("ISO 27701", re.compile(r"\bISO(?:/IEC)?\s*27701\b", re.I)),
    ("ISO 9001", re.compile(r"\bISO\s*9001\b", re.I)),
    ("HIPAA", re.compile(r"\bHIPAA\b")),
    ("PCI DSS", re.compile(r"\bPCI[- ]?DSS\b", re.I)),
    ("FedRAMP", re.compile(r"\bFedRAMP\b", re.I)),
    ("HITRUST", re.compile(r"\bHITRUST\b", re.I)),
    ("Cyber Essentials", re.compile(r"\bCyber\s+Essentials(?:\s+Plus)?\b", re.I)),
    ("TISAX", re.compile(r"\bTISAX\b")),
    ("GDPR", re.compile(r"\bGDPR\s+(?:compliant|compliance|certified|ready)\b", re.I)),
    ("CCPA", re.compile(r"\bCCPA\s+(?:compliant|compliance|certified|ready)\b", re.I)),
)

# Standardized MX host suffixes (provider mail / gateway hosts).
MX_PROVIDERS: tuple[tuple[tuple[str, ...], str, str], ...] = (
    ((".google.com", ".googlemail.com"), "Google Workspace", "Email hosting"),
    ((".mail.protection.outlook.com", ".eo.outlook.com"), "Microsoft 365", "Email hosting"),
    ((".zoho.com", ".zoho.in", ".zoho.eu", ".zohomail.com"), "Zoho Mail", "Email hosting"),
    ((".mimecast.com",), "Mimecast", "Email security"),
    ((".pphosted.com",), "Proofpoint", "Email security"),
    ((".barracudanetworks.com",), "Barracuda", "Email security"),
    ((".protonmail.ch", ".proton.ch"), "Proton Mail", "Email hosting"),
    ((".messagingengine.com", ".fastmail.com"), "Fastmail", "Email hosting"),
    ((".messagelabs.com",), "Broadcom Email Security", "Email security"),
    ((".yahoodns.net",), "Yahoo Mail", "Email hosting"),
    ((".yandex.net", ".yandex.ru"), "Yandex 360", "Email hosting"),
    ((".secureserver.net",), "GoDaddy Email", "Email hosting"),
    ((".emailsrvr.com",), "Rackspace Email", "Email hosting"),
    ((".ovh.net",), "OVH Mail", "Email hosting"),
)

# Standardized DNS TXT domain-verification prefixes published by SaaS vendors.
TXT_VERIFICATIONS: tuple[tuple[str, str, str], ...] = (
    ("google-site-verification=", "Google Search Console", "Analytics"),
    ("ms=", "Microsoft 365", "Productivity"),
    ("atlassian-domain-verification=", "Atlassian", "Collaboration"),
    ("hubspot-developer-verification=", "HubSpot", "CRM / Marketing"),
    ("hubspot-domain-verification=", "HubSpot", "CRM / Marketing"),
    ("docusign=", "DocuSign", "E-signature"),
    ("stripe-verification=", "Stripe", "Payments"),
    ("slack-domain-verification=", "Slack", "Collaboration"),
    ("adobe-idp-site-verification=", "Adobe", "Enterprise software"),
    ("apple-domain-verification=", "Apple Business Manager", "MDM / IT"),
    ("dropbox-domain-verification=", "Dropbox", "Cloud storage"),
    ("notion-domain-verification=", "Notion", "Collaboration"),
    ("openai-domain-verification=", "OpenAI", "AI"),
    ("miro-verification=", "Miro", "Collaboration"),
    ("canva-site-verification=", "Canva", "Design"),
    ("figma-domain-verification=", "Figma", "Design"),
    ("zoom-domain-verification=", "Zoom", "Communications"),
    ("zendesk-verification=", "Zendesk", "Customer support"),
    ("cisco-ci-domain-verification=", "Cisco Webex", "Communications"),
    ("facebook-domain-verification=", "Meta Business", "Advertising"),
    ("klaviyo-site-verification=", "Klaviyo", "CRM / Marketing"),
)

# Standardized RFC 7208 SPF include domains for SaaS mail / CRM / support platforms.
SPF_INCLUDES: tuple[tuple[str, str, str], ...] = (
    ("_spf.google.com", "Google Workspace", "Email hosting"),
    ("spf.protection.outlook.com", "Microsoft 365", "Email hosting"),
    ("servers.mcsv.net", "Mailchimp", "CRM / Marketing"),
    ("sendgrid.net", "SendGrid", "Email delivery"),
    ("_spf.salesforce.com", "Salesforce", "CRM / Marketing"),
    ("amazonses.com", "Amazon SES", "Email delivery"),
    ("mailgun.org", "Mailgun", "Email delivery"),
    ("hubspotemail.net", "HubSpot", "CRM / Marketing"),
    ("zendesk.com", "Zendesk", "Customer support"),
    ("freshdesk.com", "Freshdesk", "Customer support"),
    ("mktomail.com", "Marketo", "CRM / Marketing"),
    ("pardot.com", "Salesforce Pardot", "CRM / Marketing"),
    ("postmarkapp.com", "Postmark", "Email delivery"),
    ("sparkpostmail.com", "SparkPost", "Email delivery"),
    ("zoho.com", "Zoho Mail", "Email hosting"),
)

JOB_CATEGORIES = frozenset({
    "Analytics", "CRM", "Caching", "Cloud", "CMS", "Containers", "Customer data platform",
    "Database managers", "Databases", "Deployment", "Development", "DevOps", "Ecommerce",
    "Enterprise resource planning", "Hosting", "Issue trackers", "JavaScript frameworks",
    "LMS", "Load balancers", "Log management", "Marketing automation", "Message queues",
    "Monitoring", "Operating systems", "PaaS", "Payment processors", "Programming languages",
    "Real user monitoring", "Remote access", "Search engines", "Security", "SEO",
    "Single sign on", "Tag managers", "Web frameworks", "Web servers", "Webhooks",
})

_SPF_INC_RE = re.compile(r"include:([^\s]+)", re.I)


@dataclass(frozen=True)
class TechMatch:
    tech: str
    category: str
    source: str
    evidence: str


def detect_compliance(text: str) -> list[TechMatch]:
    """Explicit compliance standards mentioned in visible page text."""
    if not text:
        return []
    out: list[TechMatch] = []
    scan = text[:MAX_TEXT_SCAN]
    for name, pat in COMPLIANCE_PATTERNS:
        m = pat.search(scan)
        if m:
            lo = max(0, m.start() - 40)
            hi = min(len(scan), m.end() + 60)
            snippet = " ".join(scan[lo:hi].split())[:240]
            out.append(TechMatch(name, "Compliance", "compliance", snippet))
    return out


def dns_matches_from_records(mx_hosts: Sequence[str], txt_records: Sequence[str]) -> list[TechMatch]:
    """Derive email, SaaS verification, and SPF technologies from MX and TXT records."""
    found: dict[tuple[str, str], TechMatch] = {}
    for host in mx_hosts:
        h = host.rstrip(".").lower()
        for suffixes, tech, cat in MX_PROVIDERS:
            if any(h.endswith(s) or h == s.lstrip(".") for s in suffixes):
                key = (tech, "dns_mx")
                found.setdefault(key, TechMatch(tech, cat, "dns_mx", f"MX: {h}"[:200]))
                break
    for txt in txt_records:
        raw = txt.strip()
        low = raw.lower()
        for prefix, tech, cat in TXT_VERIFICATIONS:
            if low.startswith(prefix):
                key = (tech, "dns_txt")
                found.setdefault(key, TechMatch(tech, cat, "dns_txt", f"TXT: {prefix}..."[:200]))
                break
        if "v=spf1" in low:
            for inc in _SPF_INC_RE.findall(low):
                for suffix, tech, cat in SPF_INCLUDES:
                    if inc == suffix or inc.endswith("." + suffix):
                        key = (tech, "dns_txt")
                        found.setdefault(key, TechMatch(tech, cat, "dns_txt", f"SPF include:{inc}"[:200]))
                        break
    return list(found.values())


def _required_literal(pat: str) -> str | None:
    """Safest mandatory lowercase substring at regex depth 0 so pre-filtering never misses a match."""
    tokens: list[str] = []
    cur: list[str] = []
    i, n = 0, len(pat)
    depth_p = 0
    in_cls = False
    while i < n:
        ch = pat[i]
        if ch == "\\" and i + 1 < n:
            nxt = pat[i + 1]
            if depth_p == 0 and not in_cls:
                if nxt in "./_-:+@= ":
                    cur.append(nxt)
                else:
                    if cur:
                        tokens.append("".join(cur))
                        cur = []
            if nxt == "x":
                i += 4
            elif nxt == "u":
                i += 6
            elif nxt == "c":
                i += 3
            else:
                i += 2
            continue
        if in_cls:
            if ch == "]":
                in_cls = False
            i += 1
            continue
        if ch == "[":
            if cur:
                tokens.append("".join(cur))
                cur = []
            in_cls = True
            i += 1
            continue
        if ch == "(":
            if cur:
                tokens.append("".join(cur))
                cur = []
            depth_p += 1
            i += 1
            continue
        if ch == ")":
            depth_p = max(0, depth_p - 1)
            i += 1
            continue
        if depth_p == 0:
            if ch == "|":
                return None  # top-level alternation: no single mandatory literal
            if ch in "?*{":
                if ch in "?*" or pat[i:].startswith("{0"):
                    if cur:
                        cur.pop()
                if cur:
                    tokens.append("".join(cur))
                    cur = []
                if ch == "{":
                    end = pat.find("}", i)
                    i = end + 1 if end != -1 else i + 1
                    continue
                i += 1
                continue
            if ch in "^$.+":
                if cur:
                    tokens.append("".join(cur))
                    cur = []
                i += 1
                continue
            cur.append(ch)
        i += 1
    if cur:
        tokens.append("".join(cur))
    good = [t.lower() for t in tokens if len(t) >= 4]
    return max(good, key=len) if good else None


def _build_field_filter(rules: list[Rule], getter) -> tuple[list[tuple[str, int]], list[tuple[int, re.Pattern[str]]]]:
    lits: list[tuple[str, int]] = []
    nolits: list[tuple[int, re.Pattern[str]]] = []
    for idx, r in enumerate(rules):
        for p in getter(r):
            if not p.regex:
                continue
            lit = _required_literal(p.regex.pattern)
            if lit:
                lits.append((lit, idx))
            else:
                nolits.append((idx, p.regex))
    return lits, nolits


class TechIndex:
    """Fast pre-filtered matcher over webappanalyzer rules, keeping GPL rules purely external at runtime."""

    def __init__(self, rules: list[tuple[Rule, str]], job_terms: list[tuple[str, str]] | None = None) -> None:
        self.rules = [r for r, _ in rules]
        self.cats = [c or "Technology" for _, c in rules]
        self.by_header: dict[str, list[int]] = defaultdict(list)
        self.by_meta: dict[str, list[int]] = defaultdict(list)
        self.by_cookie: dict[str, list[int]] = defaultdict(list)
        for idx, r in enumerate(self.rules):
            for k in r.headers:
                self.by_header[k].append(idx)
            for k in r.meta:
                self.by_meta[k].append(idx)
            for k in r.cookies:
                self.by_cookie[k].append(idx)

        self.ss_lits, self.ss_nolits = _build_field_filter(self.rules, lambda r: r.script_src)
        self.sc_lits, self.sc_nolits = _build_field_filter(self.rules, lambda r: r.scripts)
        self.ht_lits, self.ht_nolits = _build_field_filter(self.rules, lambda r: r.html)

        self.job_terms = job_terms or []
        self._job_re: re.Pattern[str] | None = None
        self._job_cats: dict[str, str] = {}
        if self.job_terms:
            sorted_terms = sorted(self.job_terms, key=lambda x: -len(x[0]))
            self._job_cats = {name: cat for name, cat in sorted_terms}
            escaped = "|".join(re.escape(name) for name, _cat in sorted_terms)
            self._job_re = re.compile(rf"(?<![A-Za-z0-9_])({escaped})(?![A-Za-z0-9_])")

    @classmethod
    def load(cls, rules_dir: Path | None = None) -> TechIndex:
        base_dir = rules_dir or Path(get_settings().data_dir) / "kb" / "webappanalyzer"
        cats_path = base_dir / "categories.json"
        tech_dir = base_dir / "technologies"
        stale = (not cats_path.is_file()
                 or time.time() - cats_path.stat().st_mtime > RULES_MAX_AGE)
        if stale:
            tech_dir.mkdir(parents=True, exist_ok=True)
            with httpx.Client(timeout=30, headers={"User-Agent": get_settings().user_agent}) as client:
                r = client.get(CATS_URL)
                r.raise_for_status()
                cats_path.write_text(r.text)
                for ch in "abcdefghijklmnopqrstuvwxyz_":
                    p = tech_dir / f"{ch}.json"
                    if not p.is_file() or time.time() - p.stat().st_mtime > RULES_MAX_AGE:
                        resp = client.get(RULES_URL.format(file=ch))
                        resp.raise_for_status()
                        p.write_text(resp.text)

        cats_raw = json.loads(cats_path.read_text())
        cat_names = {int(k): str(v.get("name") or "") for k, v in cats_raw.items() if isinstance(v, dict)}
        rules: list[tuple[Rule, str]] = []
        job_terms: list[tuple[str, str]] = []
        for path in sorted(tech_dir.glob("*.json")):
            for name, entry in json.loads(path.read_text()).items():
                if not isinstance(entry, dict):
                    continue
                entry_cats = [cat_names.get(int(c), "") for c in (entry.get("cats") or []) if int(c) in cat_names]
                primary_cat = next((c for c in entry_cats if c), "Technology")
                rule = parse_rule(name, entry)
                if not rule.empty():
                    rules.append((rule, primary_cat))
                if len(name) >= 5 and any(c in JOB_CATEGORIES for c in entry_cats):
                    if name.lower() not in {"share", "scale", "craft", "ember", "ionic", "solid", "ghost", "prism"}:
                        job_terms.append((name, primary_cat))
        return cls(rules, job_terms)

    @staticmethod
    def _filter_field(lits: list[tuple[str, int]], nolits: list[tuple[int, re.Pattern[str]]],
                      text: str, candidates: set[int]) -> None:
        if not text:
            return
        low = text.lower()
        candidates.update(idx for lit, idx in lits if lit in low)
        for idx, pat in nolits:
            if pat.search(text):
                candidates.add(idx)

    def scan_page(self, url: str, html: str, headers: Sequence[tuple[str, str]]) -> list[TechMatch]:
        doc = parse_page(url, html[:PARSE_CHARS])
        hdr_lower = [(k.lower(), v) for k, v in headers]
        candidates: set[int] = set()
        for k, v in hdr_lower:
            if k == "set-cookie":
                cname = v.split("=", 1)[0].strip().lower()
                candidates.update(self.by_cookie.get(cname, ()))
            else:
                candidates.update(self.by_header.get(k, ()))
        for mname in doc.meta:
            candidates.update(self.by_meta.get(mname, ()))

        srcs_text = "\n".join(s.attributes.get("src") or "" for s in doc.tree.css("script[src]"))
        self._filter_field(self.ss_lits, self.ss_nolits, srcs_text, candidates)
        inline_text = "\n".join((s.text() or "")[:20_000] for s in doc.tree.css("script")
                                if not s.attributes.get("src"))[:MAX_INLINE_SCAN]
        self._filter_field(self.sc_lits, self.sc_nolits, inline_text, candidates)
        self._filter_field(self.ht_lits, self.ht_nolits, html[:MAX_TEXT_SCAN], candidates)

        out: list[TechMatch] = []
        for idx in sorted(candidates):
            ev = detect(self.rules[idx], doc, hdr_lower)
            if ev:
                out.append(TechMatch(self.rules[idx].name, self.cats[idx], "webappanalyzer", ev))
        out.extend(detect_compliance(f"{doc.title}\n{doc.text}"))
        return out

    def scan_job_text(self, text: str) -> list[TechMatch]:
        if not text or self._job_re is None:
            return []
        seen: dict[str, TechMatch] = {}
        scan = text[:MAX_TEXT_SCAN]
        for m in self._job_re.finditer(scan):
            term = m.group(1)
            if term not in seen:
                lo = max(0, m.start() - 35)
                hi = min(len(scan), m.end() + 45)
                seen[term] = TechMatch(term, self._job_cats[term], "job_ad", " ".join(scan[lo:hi].split())[:200])
        return list(seen.values())


_POOL_INDEX: TechIndex | None = None


def _pool_init() -> None:
    """Load TechIndex once inside each worker process so CPU regex scans bypass the GIL."""
    global _POOL_INDEX
    _POOL_INDEX = TechIndex.load()


def _pool_scan(url: str, html: str, headers: Sequence[tuple[str, str]]) -> list[TechMatch]:
    idx = _POOL_INDEX if _POOL_INDEX is not None else TechIndex.load()
    return idx.scan_page(url, html, headers)


def save_matches(conn, domain: str, matches: Sequence[TechMatch]) -> int:
    if not matches:
        return 0
    dedup: dict[tuple[str, str], TechMatch] = {}
    for m in matches:
        dedup.setdefault((m.tech, m.source), m)
    now = datetime.now(UTC)
    rows = [(domain, m.tech, m.category, m.source, (m.evidence or "").replace("\x00", "")[:240] or None, now)
            for m in dedup.values()]
    with conn.cursor() as cur:
        cur.executemany(
            """INSERT INTO kb.company_tech (domain, tech, category, source, evidence, detected_at)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (domain, tech, source) DO UPDATE SET
                   category = EXCLUDED.category, evidence = EXCLUDED.evidence,
                   detected_at = EXCLUDED.detected_at""",
            rows,
        )
    return len(rows)


async def _dns_one(resolver, domain: str) -> tuple[str, list[str], list[str]]:
    mx_hosts: list[str] = []
    txts: list[str] = []
    for rtype, out in (("MX", mx_hosts), ("TXT", txts)):
        try:
            ans = await resolver.resolve(domain, rtype, lifetime=3.0)
            for rdata in ans:
                if rtype == "MX":
                    out.append(str(rdata.exchange))
                else:
                    out.append("".join(s.decode("utf-8", "replace") if isinstance(s, bytes) else str(s)
                                       for s in getattr(rdata, "strings", [str(rdata)])))
        except Exception:  # noqa: BLE001 - NXDOMAIN, NoAnswer, timeout simply yield no records
            continue
    return domain, mx_hosts, txts


async def scan_dns_domains(domains: Sequence[str], concurrency: int = 256,
                           on_result: Any = None) -> tuple[int, int]:
    """Query DNS MX and TXT for `domains` asynchronously and emit TechMatch lists."""
    import dns.asyncresolver

    resolver = dns.asyncresolver.Resolver()
    resolver.timeout = 2.0
    resolver.lifetime = 3.0
    slots = asyncio.Semaphore(concurrency)
    checked = hits = 0

    async def worker(d: str) -> None:
        nonlocal checked, hits
        async with slots:
            domain, mx_hosts, txts = await _dns_one(resolver, d)
        matches = dns_matches_from_records(mx_hosts, txts)
        checked += 1
        if matches:
            hits += 1
        if on_result is not None:
            on_result(domain, mx_hosts, matches)

    for i in range(0, len(domains), concurrency * 4):
        batch = domains[i:i + concurrency * 4]
        await asyncio.gather(*(worker(d) for d in batch))
    return checked, hits
