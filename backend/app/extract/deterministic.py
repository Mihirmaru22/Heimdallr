"""Deterministic extraction: structured data, metadata, patterns and labels. No model involved.

Every candidate value carries the method that found it, a confidence and an evidence snippet
taken from the page, so a reviewer can see where it came from. A field with no candidate is
reported as missing, never filled with a guess.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import unquote, urlsplit

import extruct
import phonenumbers
from selectolax.lexbor import LexborHTMLParser as HTMLParser
from selectolax.lexbor import LexborNode as Node

from app.crawl.urlnorm import has_public_suffix, normalize_url, registered_domain
from app.spec.models import FieldSpec, Semantic

EMAIL_RE = re.compile(r"(?<![\w.+-])[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,253}\.[A-Za-z]{2,24}(?![\w-])")
IMAGE_SUFFIX = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")
PRICE_RE = re.compile(
    r"(?:(?:[$€£¥]|USD|EUR|GBP|CHF)\s?\d[\d,.]*(?:\s?(?:k|K))?|\d[\d,.]*\s?(?:[$€£]|USD|EUR|GBP|CHF))"
    r"(?:\s?(?:/|per)\s?(?:user|seat|month|mo|year|yr|annum|endpoint|device)(?:\s?(?:/|per)\s?(?:month|mo|year|yr))?)?"
)
CONTACT_SALES_RE = re.compile(r"\b(contact (?:us|sales)|request (?:a )?(?:quote|demo|pricing)|custom pricing)\b", re.I)
YEAR_RE = re.compile(r"\b(1[89]\d\d|20[0-4]\d)\b")
COPYRIGHT_RE = re.compile(r"(?:©|\(c\)|copyright)\s*(?:\d{4}\s*[-–]\s*)?(?:\d{4})?\s*,?\s*([A-Z][\w&.,' -]{1,80}?)"
                          r"(?:\s*(?:\.|All rights|\||$))", re.I)
SOCIAL_HOSTS = ("linkedin.com", "twitter.com", "x.com", "facebook.com", "github.com", "youtube.com",
                "instagram.com", "mastodon.social")
TITLE_SPLIT_RE = re.compile(r"\s+[|–—\-:·•]\s+")
HQ_LABELS = ("headquarters", "headquartered in", "head office", "hq", "registered office", "main office")
ADDRESS_LABELS = ("address", "office", "registered office", "visit us", "find us")
FOUNDED_LABELS = ("founded", "established", "since", "year founded")


@dataclass
class Candidate:
    value: Any
    method: str
    confidence: float
    evidence: str = ""
    source_url: str | None = None  # set when the value came from elsewhere than the page it is stored with


@dataclass
class PageDoc:
    url: str
    html: str
    tree: HTMLParser
    text: str
    title: str
    meta: dict[str, str]
    jsonld: list[dict[str, Any]]
    links: list[tuple[str, str]] = field(default_factory=list)  # (absolute url, anchor text)


def _visible_text(tree: HTMLParser) -> str:
    body = tree.body or tree.root
    if body is None:
        return ""
    clone = HTMLParser(body.html or "")
    for node in clone.css("script, style, noscript, svg, template, iframe"):
        node.decompose()
    text = clone.root.text(separator="\n") if clone.root else ""
    lines = [re.sub(r"[ \t ]+", " ", ln).strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def _flatten_jsonld(items: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    stack = list(items)
    while stack:
        item = stack.pop(0)
        if isinstance(item, list):
            stack.extend(item)
        elif isinstance(item, dict):
            if "@graph" in item:
                stack.extend(item["@graph"] if isinstance(item["@graph"], list) else [item["@graph"]])
            out.append(item)
    return out


def parse_page(url: str, html: str) -> PageDoc:
    tree = HTMLParser(html)
    title_node = tree.css_first("title")
    title = re.sub(r"\s+", " ", title_node.text()).strip() if title_node else ""
    meta: dict[str, str] = {}
    for m in tree.css("meta"):
        key = (m.attributes.get("property") or m.attributes.get("name") or "").strip().lower()
        content = m.attributes.get("content")
        if key and content and key not in meta:
            meta[key] = content.strip()
    try:
        data = extruct.extract(html, base_url=url, syntaxes=["json-ld", "microdata"], uniform=True, errors="ignore")
        jsonld = _flatten_jsonld(data.get("json-ld", []) + data.get("microdata", []))
    except Exception:  # noqa: BLE001 - malformed structured data must not stop extraction
        jsonld = []
    links: list[tuple[str, str]] = []
    for a in tree.css("a[href]"):
        href = a.attributes.get("href") or ""
        if href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        absolute = normalize_url(href, base=url)
        if absolute:
            links.append((absolute, re.sub(r"\s+", " ", a.text()).strip()[:200]))
    return PageDoc(url, html, tree, _visible_text(tree), title, meta, jsonld, links)


def _types(item: dict[str, Any]) -> set[str]:
    t = item.get("@type", [])
    return {x.split("/")[-1] for x in (t if isinstance(t, list) else [t]) if isinstance(x, str)}


ORG_TYPES = {"Organization", "Corporation", "LocalBusiness", "Company", "NGO", "OnlineBusiness",
             "EducationalOrganization", "Store", "ProfessionalService"}


def _orgs(doc: PageDoc) -> list[dict[str, Any]]:
    return [i for i in doc.jsonld if _types(i) & ORG_TYPES]


def _first_str(v: Any) -> str | None:
    if isinstance(v, list):
        v = v[0] if v else None
    if isinstance(v, dict):
        v = v.get("name") or v.get("@value")
    return str(v).strip() if v not in (None, "") else None


def _snippet(text: str, needle: str, width: int = 90) -> str:
    idx = text.lower().find(needle.lower()[:60])
    if idx < 0:
        return needle[:200]
    start, end = max(0, idx - width), min(len(text), idx + len(needle) + width)
    return ("…" if start else "") + text[start:end].replace("\n", " ") + ("…" if end < len(text) else "")


def _address_text(addr: Any) -> tuple[str | None, str | None, str | None]:
    """Return (full address, locality+country, country) from a schema.org PostalAddress."""
    if isinstance(addr, list):
        addr = addr[0] if addr else None
    if isinstance(addr, str):
        return addr, None, None
    if not isinstance(addr, dict):
        return None, None, None
    country = _first_str(addr.get("addressCountry"))
    parts = [_first_str(addr.get(k)) for k in ("streetAddress", "postalCode", "addressLocality",
                                               "addressRegion")]
    full = ", ".join(p for p in parts + [country] if p)
    locality = ", ".join(p for p in (_first_str(addr.get("addressLocality")), country) if p)
    return full or None, locality or None, country


def _label_values(doc: PageDoc, labels: list[str]) -> list[tuple[str, str]]:
    """Find 'Label: value' pairs in definition lists, tables and text lines."""
    found: list[tuple[str, str]] = []
    wanted = [lb.lower().strip() for lb in labels if lb.strip()]
    if not wanted:
        return found
    for dt in doc.tree.css("dt, th"):
        key = dt.text(strip=True).lower().rstrip(":")
        if any(key == w or key.startswith(w) for w in wanted):
            sib: Node | None = dt.next
            while sib is not None and sib.tag not in ("dd", "td"):
                sib = sib.next
            if sib is not None:
                val = sib.text(separator=" ", strip=True)
                if val:
                    found.append((val, f"{dt.text(strip=True)} {val}"))
    for line in doc.text.splitlines():
        low = line.lower()
        for w in wanted:
            m = re.match(rf"^\s*{re.escape(w)}\s*[:\-–]\s*(.{{2,200}})$", low)
            if m:
                found.append((line[m.start(1):].strip(), line.strip()))
    return found


# --- semantic extractors ----------------------------------------------------------------------


MARKS_RE = re.compile(r"[®™©℠]")
# "Merck & Co., Inc., Rahway, NJ, USA": a trailing city, state and country is an address, not the name.
US_PLACE_RE = re.compile(r",\s*[A-Z][A-Za-z .'-]{1,40},\s*[A-Z]{2}(?:,\s*(?:USA|U\.S\.A\.|US|United States))?$")
DOMAIN_NAME_RE = re.compile(r"^[\w-]+(\.[\w-]+)*\.[a-z]{2,6}$", re.I)


def clean_company_name(name: str, keep: str = "first") -> str:
    """Drop trademark signs, taglines after a separator and a trailing US address."""
    name = MARKS_RE.sub("", name).strip()
    parts = [p.strip() for p in TITLE_SPLIT_RE.split(name) if p.strip()]
    if len(parts) > 1:
        name = parts[0] if keep == "first" else parts[-1]
    return US_PLACE_RE.sub("", name).strip(" ,")


def _name_candidate(name: str, method: str, confidence: float, evidence: str, keep: str = "first") -> Candidate:
    clean = clean_company_name(name, keep)
    if DOMAIN_NAME_RE.match(clean):  # "JNJ.com" is how the site brands itself, not the company's name
        confidence = min(confidence, 0.35)
    return Candidate(clean or name, method, confidence, evidence)


def _company_name(doc: PageDoc) -> list[Candidate]:
    out = []
    for org in _orgs(doc):
        name = _first_str(org.get("name")) or _first_str(org.get("legalName"))
        if name:
            out.append(_name_candidate(name, "jsonld", 0.9, f"JSON-LD {sorted(_types(org))[0]}.name = {name}"))
    for key in ("og:site_name", "application-name"):
        if doc.meta.get(key):
            out.append(_name_candidate(doc.meta[key], "meta", 0.75, f'<meta {key}="{doc.meta[key]}">'))
    m = COPYRIGHT_RE.search(doc.text[-3000:])
    if m:
        name = m.group(1).strip(" .,")
        if 2 <= len(name) <= 80 and not name.lower().startswith("all rights"):
            out.append(_name_candidate(name, "pattern", 0.55, m.group(0).strip()))
    if doc.title:
        parts = TITLE_SPLIT_RE.split(doc.title)
        if len(parts) > 1:
            out.append(_name_candidate(parts[-1], "title", 0.45, f"<title>{doc.title}</title>", keep="last"))
        elif urlsplit(doc.url).path in ("", "/"):
            out.append(_name_candidate(doc.title, "title", 0.4, f"<title>{doc.title}</title>"))
    return [c for c in out if c.value]


def _website(doc: PageDoc) -> list[Candidate]:
    out = []
    for org in _orgs(doc):
        u = _first_str(org.get("url"))
        norm = normalize_url(u, base=doc.url) if u else None
        if norm and not has_public_suffix(norm) and urlsplit(norm).hostname != urlsplit(doc.url).hostname:
            norm = None  # "https://www.bridewell/": a typo in the site's own markup, not a website
        if norm:
            if registered_domain(norm) == registered_domain(doc.url):  # "/in/" or "/en-us" -> the homepage
                p = urlsplit(norm)
                norm = f"{p.scheme}://{p.netloc}/"
            out.append(Candidate(norm, "jsonld", 0.9, f"JSON-LD Organization.url = {u}"))
    parts = urlsplit(doc.url)
    out.append(Candidate(f"{parts.scheme}://{parts.netloc}/", "page_origin", 0.8, f"crawled site {parts.netloc}"))
    return out


# Mailboxes that exist but are not a company's general contact; kept, but ranked last.
NARROW_MAILBOX_RE = re.compile(
    r"^(hr|careers?|jobs?|recruit\w*|talent|privacy|dataprotection|dpo|gdpr|drugsafety|pharmacovigilance|"
    r"safety|ethics|compliance|business\.?ethics|legal|investors?|investor[._]?relations|ir|noreply|no-reply|"
    r"donotreply|webmaster|abuse|security|accessibility|hr\.\w+|\w*(gdpr|dpo|privacy)\w*)$")
# Words that mark a mailbox as something other than a way to contact the company (copyrightnotices@,
# grievanceofficer@, pandora-jobs@, reportabuse@, peoplesupport-china@). These are dropped outright.
NOT_CONTACT_RE = re.compile(
    r"copyright|trademark|legal|grievance|privacy|gdpr|dpo|dataprotect|abuse|report|complian|ethic|whistle|"
    r"jobs?\b|jobs?[._-]|careers?|recruit|talent|people|\bhr\b|^hr[._-]|hr$|registration|noreply|no-reply|donotreply|"
    r"unsubscribe|bounce|mailer|postmaster|webmaster|accessib|safety|vigilance|security|"
    r"vulnerab|partner|affiliate|marketing|sponsor|advertis|billing|invoice|"
    r"payable|receivable|procurement|vendor|supplier|tax|fraud|counterfeit|recall|warranty|clinicaltrial|"
    r"grants?\b|grants?[._-]|secretar|medinfo|adverse")
# Words in a mailbox that belong to a team rather than a person (mediarelations@, zoetismedia@).
ROLE_WORD_RE = re.compile(
    r"info|contact|hello|sales|office|support|enquir|inquir|media|press|communicat|news|"
    r"customer|service|patient|general|admin|team|mail|help|connect|business|ask|question|"
    r"welcome|care|orders|booking|reserv|feedback|helpdesk|frontdesk|reception|relations|"
    r"investor|proposals|customercare|desk"
)
JOBS_PAGE_RE = re.compile(r"^(jobs|careers?|recruiting|talent)\.|/(jobs|careers?|recruiting|join-us|vacancies)(/|$)",
                          re.I)
NEWS_PAGE_RE = re.compile(r"/(press|news|media|stories|blog)[^/]*/.+", re.I)
# first.last or first.m.last: a person, not the company's contact (customer.service has a team word: kept).
PERSONAL_MAILBOX_RE = re.compile(r"^[a-z]+(?:[._-][a-z]+){1,2}\d*$")
PLACEHOLDER_EMAIL_RE = re.compile(r"lorem|ipsum|yourdomain|your-?email|domain\.com$|email\.com$|sentry|wixpress", re.I)


def _same_company_domain(domain: str, site: str) -> bool:
    """acme.com, mail.acme.com, or a sister domain sharing the brand (snowflake.com / snowflake.net)."""
    reg = registered_domain(f"https://{domain}/") or domain
    return reg == site or reg.split(".")[0] == site.split(".")[0]


def _decode_cfemail(encoded: str) -> str | None:
    """Decode Cloudflare's XOR hex email-protection token."""
    h = encoded.strip()
    if len(h) < 6 or len(h) % 2 != 0:
        return None
    try:
        key = int(h[:2], 16)
        out = "".join(chr(int(h[i:i + 2], 16) ^ key) for i in range(2, len(h), 2))
    except ValueError:
        return None
    return out if EMAIL_RE.fullmatch(out) else None


def emails_from_text(text: str, domain: str) -> list[dict[str, str]]:
    """Same-company role mailboxes extracted cleanly from plain page text."""
    if not text or not domain:
        return []
    site = registered_domain(f"https://{domain}/") or domain.lower()
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for m in EMAIL_RE.finditer(text):
        addr = m.group().lower()
        if addr in seen or addr.endswith(IMAGE_SUFFIX) or "example." in addr or PLACEHOLDER_EMAIL_RE.search(addr):
            continue
        local, em_domain = addr.split("@", 1)
        if not _same_company_domain(em_domain, site):
            continue
        if NOT_CONTACT_RE.search(local) or not ROLE_WORD_RE.search(local):
            continue
        if PERSONAL_MAILBOX_RE.match(local) and not ROLE_WORD_RE.search(local):
            continue
        seen.add(addr)
        out.append({"email": addr, "method": "regex"})
    return out


def _emails(doc: PageDoc) -> list[Candidate]:
    site = registered_domain(doc.url)
    seen: dict[str, Candidate] = {}
    for a in doc.tree.css('a[href^="mailto:"]'):
        addr = unquote((a.attributes.get("href") or "")[7:].split("?")[0]).strip()
        if EMAIL_RE.fullmatch(addr):
            same = addr.split("@")[-1].lower().endswith(site)
            seen.setdefault(addr.lower(), Candidate(addr, "mailto", 0.85 if same else 0.4, f"mailto:{addr}"))
    for el in doc.tree.css("[data-cfemail], a[href*='/cdn-cgi/l/email-protection#']"):
        token = el.attributes.get("data-cfemail") or (el.attributes.get("href") or "").partition("#")[2]
        addr = _decode_cfemail(token)
        if addr:
            same = addr.split("@")[-1].lower().endswith(site)
            seen.setdefault(addr.lower(), Candidate(addr, "cfemail", 0.85 if same else 0.4, f"cfemail:{addr}"))
    for org in _orgs(doc):
        addr = _first_str(org.get("email"))
        if addr and EMAIL_RE.fullmatch(addr.removeprefix("mailto:")):
            addr = addr.removeprefix("mailto:")
            seen.setdefault(addr.lower(), Candidate(addr, "jsonld", 0.9, f"JSON-LD email = {addr}"))
    for m in EMAIL_RE.finditer(doc.text):
        addr = m.group()
        if addr.lower().endswith(IMAGE_SUFFIX) or "example." in addr.lower():
            continue
        same = addr.split("@")[-1].lower().endswith(site)
        seen.setdefault(addr.lower(), Candidate(addr, "regex", 0.7 if same else 0.3, _snippet(doc.text, addr)))
    # A careers or job site's addresses are recruiting mailboxes (mydelekhr@ on jobs.delekus.com).
    if JOBS_PAGE_RE.search(urlsplit(doc.url).netloc + urlsplit(doc.url).path):
        return []
    out = []
    for c in seen.values():
        local, domain = c.value.lower().split("@", 1)
        if PLACEHOLDER_EMAIL_RE.search(c.value):  # template text, not a real mailbox
            continue
        # Another company's address (an agency, a distributor, a blog author) is never this company's contact,
        # unless the site's own structured data declares it.
        if c.method != "jsonld" and not _same_company_domain(domain, site):
            continue
        if local in ("info", "contact", "hello", "sales", "office", "support", "enquiries", "inquiries"):
            c.confidence = min(0.95, c.confidence + 0.05)  # role mailboxes people expect to contact
        elif NOT_CONTACT_RE.search(local):
            continue  # legal notices, jobs, abuse reports, partner programmes...: not "contact the company"
        elif re.search(r"[._-][a-z]{2}$", local):
            c.confidence = round(c.confidence - 0.25, 2)  # a country office's box (citrix_ru@), not the main one
        elif NARROW_MAILBOX_RE.match(local):
            c.confidence = round(c.confidence - 0.25, 2)  # HR, privacy, drug safety...: real, but not "contact"
        elif PERSONAL_MAILBOX_RE.match(local) and not ROLE_WORD_RE.search(local):
            continue  # first.last@: one person's inbox (a press officer), not the company's contact
        elif not ROLE_WORD_RE.search(local):
            # kmontag@, jruberti@: most likely a person; one quoted in a press release even more so.
            c.confidence = round(c.confidence - (0.35 if NEWS_PAGE_RE.search(urlsplit(doc.url).path) else 0.2), 2)
        out.append(c)
    return out


# Numbers of other organizations that many sites print: FDA MedWatch (1-800-FDA-1088), on every US drug site.
THIRD_PARTY_NUMBERS = {"8003321088"}
PHONE_TEXT_RE = re.compile(r"\+\d[\d ()./-]{6,20}\d")
LOCAL_PHONE_RE = re.compile(
    r"(?:"
    r"(?:\b1[-.\s]?)?\(\d{3}\)[-.\s]?\d{3}[-.\s]?\d{4}\b"
    r"|\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b"
    r"|\b0\d{2,4}[-.\s]\d{3,4}[-.\s]?\d{3,4}\b"
    r"|\b1800[-.\s]?\d{3}[-.\s]?\d{3,4}\b"
    r"|(?:Tel|Telephone|Phone|Ph|Call|Mob|Fax)\s*[:.]?\s*\d[\d ()./-]{7,18}\d"
    r")",
    re.I,
)
_LABEL_PREFIX_RE = re.compile(r"^(?:Tel|Telephone|Phone|Ph|Call|Mob|Fax)\s*[:.]?\s*", re.I)
_ISO_DATE_RE = re.compile(r"^(?:19|20)\d\d[-/.]\d{1,2}[-/.]\d{1,2}$")


def _not_third_party(raw: str) -> bool:
    return re.sub(r"\D", "", raw.upper().replace("FDA", "332"))[-10:] not in THIRD_PARTY_NUMBERS


def phones_from_text(text: str, countries: Sequence[str] | None = None) -> list[dict[str, str]]:
    """Validated E.164 phone numbers from plain text (international +, plus local iso2 format)."""
    if not text:
        return []
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for m in PHONE_TEXT_RE.finditer(text):
        normalized = _e164(m.group())
        if normalized and normalized not in seen and _not_third_party(normalized):
            seen.add(normalized)
            out.append({"phone": normalized, "method": "regex"})
    regions = [c.upper() for c in (countries or ()) if c]
    if regions:
        for m in LOCAL_PHONE_RE.finditer(text):
            raw_num = _LABEL_PREFIX_RE.sub("", m.group()).strip()
            if _ISO_DATE_RE.match(raw_num):
                continue
            normalized = _local_number(raw_num, regions)
            if normalized and normalized not in seen and _not_third_party(normalized):
                seen.add(normalized)
                out.append({"phone": normalized, "method": "regex_local"})
    return out


def _phones(doc: PageDoc) -> list[Candidate]:
    return [c for c in _phone_candidates(doc) if _not_third_party(c.value)]


def _phone_candidates(doc: PageDoc) -> list[Candidate]:
    out = []
    for a in doc.tree.css('a[href^="tel:"]'):
        # "+91 40 67611600 / 700": a second extension after a slash is not part of the number.
        num = unquote((a.attributes.get("href") or "")[4:]).split("/")[0].strip()  # "tel:%20+44..."
        if sum(ch.isdigit() for ch in num) >= 7:
            out.append(Candidate(num, "tel_link", 0.85, f"tel:{num}"))
    for org in _orgs(doc):
        tel = (_first_str(org.get("telephone")) or "").split("/")[0].strip()
        if tel:
            out.append(Candidate(tel, "jsonld", 0.9, f"JSON-LD telephone = {tel}"))
    for m in PHONE_TEXT_RE.finditer(doc.text):
        out.append(Candidate(m.group(), "regex", 0.55, _snippet(doc.text, m.group())))
    # One number written several ways ("+44 (0) 161 209 5200", "+441612095200") is one candidate.
    seen: set[str] = set()
    unique = []
    for c in out:
        c.value = _e164(c.value) or c.value
        if c.value not in seen:
            seen.add(c.value)
            unique.append(c)
    return unique


def _e164(raw: str) -> str | None:
    if not raw.startswith("+"):
        return None  # read later in the requested country (prefer_country_phones)
    try:
        num = phonenumbers.parse(raw, None)
    except phonenumbers.NumberParseException:
        return None
    return phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164) if phonenumbers.is_valid_number(
        num) else None


def _local_number(raw: str, countries: list[str]) -> str | None:
    """+E164 form of a number written without its country code, if it is valid in one requested country."""
    for region in countries:
        try:
            num = phonenumbers.parse(raw, region)
        except phonenumbers.NumberParseException:
            continue
        if phonenumbers.is_valid_number(num):
            return phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164)
    return None


def prefer_country_emails(cands: list[Candidate], countries: list[str]) -> list[Candidate]:
    """Drop another country's office mailbox (Media_Au@ in a US run) when countries were asked for; with no
    countries it stays, only ranked below the main mailbox."""
    if not countries:
        return cands
    import phonenumbers

    wanted = {c.upper() for c in countries}
    keep = []
    for c in cands:
        m = re.search(r"[._-]([a-z]{2})$", c.value.split("@")[0].lower())
        code = m.group(1).upper() if m else ""
        if code in phonenumbers.SUPPORTED_REGIONS and code not in wanted:
            continue
        keep.append(c)
    cands[:] = keep
    return cands


def prefer_country_phones(cands: list[Candidate], countries: list[str]) -> list[Candidate]:
    """Keep only numbers that can belong to the requested countries. Sites list their offices abroad and
    serve a visitor's local number (IBM shows +49 to a German visitor), and a branch office's number in
    another country is a wrong answer, so it is dropped rather than kept as a fallback."""
    if not countries:
        return cands
    keep = []
    for c in cands:
        raw = c.value.strip()
        if not raw.startswith("+"):
            # No country code: a local number ("9847433522"), read in the requested country instead of
            # being taken for a US number when the export formats it.
            local = _local_number(raw, countries)
            if local:
                c.value = local
            keep.append(c)
            continue
        try:
            region = phonenumbers.region_code_for_number(phonenumbers.parse(raw, None))
        except phonenumbers.NumberParseException:
            continue
        if region and region != "ZZ" and region not in countries:
            continue
        keep.append(c)
    cands[:] = keep
    return cands


_US_STATES = (
    "AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|"
    "NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|DC"
)
_AU_STATES = "NSW|VIC|QLD|WA|SA|TAS|ACT|NT"
_COUNTRIES_OPT = (
    r"(?:[ ]*,?[ ]*(?:USA|U\.S\.A\.|United States|UK|United Kingdom|India|Germany|Deutschland|"
    r"France|Canada|Australia|New Zealand|Singapore|Switzerland|Netherlands|Ireland))?"
)
ADDR_POSTAL_RE = re.compile(
    rf"(?:"
    rf"(?P<uk>\b[A-Z]{{1,2}}\d[A-Z\d]?[ ]+\d[A-Z]{{2}}\b)"
    rf"|(?P<ca>\b[A-CEGHJ-NPR-TV-Z]\d[A-CEGHJ-NPR-TV-Z][ -]\d[A-CEGHJ-NPR-TV-Z]\d\b)"
    rf"|(?P<us>\b(?:{_US_STATES})(?:,[ ]*|[ ]*[-–][ ]*|[ ]+)\d{{5}}(?:-\d{{4}})?\b)"
    rf"|(?P<au>\b(?:{_AU_STATES})[ ]+\d{{4}}\b)"
    rf"|(?P<in>(?:[-–, ]|PIN[ ]*[:\-]?[ ]*)\d{{6}}\b(?=[, .\n]|$)(?:[ ]*,?[ ]*India)?)"
    rf"|(?P<eu>,[ ]*\d{{4,5}}[ ]+[A-Z][A-Za-z\u00C0-\u024F-]{{2,}}"
    rf"(?:[ ][A-Z][A-Za-z\u00C0-\u024F-]{{2,}})?)"
    rf"){_COUNTRIES_OPT}",
)
ADDR_STREET_RE = re.compile(
    r"(?:\b(?:st(?:reet)?|rd|road|ave(?:nue)?|blvd|boulevard|dr(?:ive)?|ln|lane|way|ct|court|pl(?:ace)?|"
    r"pkwy|parkway|cir(?:cle)?|sq(?:uare)?|suite|ste|floor|flr|bldg|building|block|sector|phase|plot|"
    r"unit|box|p\.?o\.?\s*box|nagar|marg|chowk|colony|industrial|park|plaza|tower|center|centre|house|"
    r"str(?:aße|asse)?|rue|calle|via|gasse|weg|laan)\b|#\s*\d)",
    re.I,
)
ADDR_NOISE_RE = re.compile(r"(?:copyright|all rights reserved|privacy policy|cookie|terms of|@|https?://|\{|\})", re.I)
_LEAD_NOISE_RE = re.compile(
    r"^(?:get in touch|follow us|contact us|visit us|find us|phone(?:\s+number)?|call us|email)\s*[:\-,]?\s*",
    re.I,
)
_ADDRESS_ORG_TYPES = ORG_TYPES | {
    "Place", "CivicStructure", "FoodEstablishment", "MedicalOrganization",
    "FinancialService", "LegalService", "HealthAndBeautyBusiness",
}


def _iter_address_items(raw: Any) -> list[tuple[str | None, str | None, str | None]]:
    items = raw if isinstance(raw, list) else [raw]
    out: list[tuple[str | None, str | None, str | None]] = []
    for entry in items:
        if isinstance(entry, dict) and "address" in entry and not any(
            k in entry for k in ("streetAddress", "addressLocality", "postalCode")
        ):
            out.extend(_iter_address_items(entry.get("address")))
            continue
        full, locality, country = _address_text(entry)
        if full or locality or country:
            out.append((full, locality, country))
    return out


def addresses_from_text(text: str) -> list[dict[str, str]]:
    """Extract multi-branch street addresses from plain page text anchored on postal codes."""
    if not text:
        return []
    joined = "\n".join(ln.strip() for ln in text.splitlines() if ln.strip())
    raw_cands: list[tuple[str, str, str]] = []
    split_pat = r"(?:\s*[|•×·]\s*|\n{2,}|\[email\s+protected\]|(?:Ph|Tel|Fax|Fx|Phone|Email)\s*[:.]\s*\S+)"
    for m in ADDR_POSTAL_RE.finditer(joined):
        lo = max(0, m.start() - 160)
        window = joined[lo:m.end()]
        parts = re.split(split_pat, window, flags=re.I)
        raw_lines = [c.strip(" ,;-–") for c in parts[-1].splitlines() if c.strip()]
        picked: list[str] = []
        for ln in reversed(raw_lines[-3:]):
            picked.append(ln)
            cur = ", ".join(reversed(picked))
            if ADDR_STREET_RE.search(cur) and (len(picked) >= 2 or ":" in ln):
                break
        cand = re.sub(r"\s+", " ", ", ".join(reversed(picked))).strip(" ,;-–.")
        cand = _LEAD_NOISE_RE.sub("", cand).strip(" ,;-–.")
        if len(cand) > 180:
            cand = cand[-180:].split(" ", 1)[-1]
        if len(cand) < 15 or ADDR_NOISE_RE.search(cand) or not ADDR_STREET_RE.search(cand):
            continue
        code = (
            m.group("uk") or m.group("ca") or m.group("us") or m.group("au") or m.group("in") or m.group("eu") or ""
        ).strip(" ,-–")
        country = next((c for g, c in (("us", "US"), ("uk", "GB"), ("ca", "CA"), ("in", "IN"), ("au", "AU"))
                        if m.group(g)), "")
        raw_cands.append((cand, code, country))

    raw_cands.sort(key=lambda x: -len(x[0]))
    kept: list[dict[str, str]] = []
    seen_norms: set[str] = set()
    seen_tails: set[tuple[str, str]] = set()
    for cand, code, country in raw_cands:
        norm = re.sub(r"\W+", "", cand.lower())
        tail_key = (code.lower(), norm[-55:])
        if any(norm in sn for sn in seen_norms) or tail_key in seen_tails:
            continue
        seen_norms.add(norm)
        seen_tails.add(tail_key)
        kept.append({"address": cand, "postal_code": code, "country": country, "method": "text"})
    return kept


def _addresses(doc: PageDoc, want: str) -> list[Candidate]:
    out: list[Candidate] = []
    seen: set[str] = set()
    addr_items = [i for i in doc.jsonld if _types(i) & _ADDRESS_ORG_TYPES]
    for org in addr_items:
        raw_sources: list[Any] = [org.get("address"), org.get("location")]
        for sub_key in ("department", "subOrganization"):
            sub = org.get(sub_key)
            for s in sub if isinstance(sub, list) else [sub] if isinstance(sub, dict) else []:
                if isinstance(s, dict):
                    raw_sources.extend([s.get("address"), s.get("location")])
        for raw in raw_sources:
            if not raw:
                continue
            for full, locality, country in _iter_address_items(raw):
                value = {"address": full, "headquarters": locality or full, "country": country}[want]
                if value and value not in seen:
                    seen.add(value)
                    out.append(Candidate(value, "jsonld", 0.85, f"JSON-LD address: {full}"))
    for item in doc.jsonld:
        if "PostalAddress" in _types(item):
            for full, locality, country in _iter_address_items(item):
                value = {"address": full, "headquarters": locality or full, "country": country}[want]
                if value and value not in seen:
                    seen.add(value)
                    out.append(Candidate(value, "jsonld", 0.85, f"JSON-LD address: {full}"))
    labels = HQ_LABELS if want == "headquarters" else ADDRESS_LABELS
    if want != "country":
        for value, evidence in _label_values(doc, list(labels)):
            if value not in seen:
                seen.add(value)
                out.append(Candidate(value, "label", 0.6 if want == "headquarters" else 0.55, evidence))
        if want == "address":
            for node in doc.tree.css("address"):
                text = re.split(
                    r"\s*[·|•,;-]?\s*\b(?:phone|tel|telephone|fax|email)\b\s*:",
                    node.text(separator=", ", strip=True),
                    maxsplit=1,
                    flags=re.I,
                )[0].strip(" ,·|•-")
                if 8 <= len(text) <= 300 and text not in seen:
                    seen.add(text)
                    out.append(Candidate(text, "html_address", 0.65, f"<address>{text}</address>"))
        if want == "headquarters":
            m = re.search(r"headquartered in ([A-Z][\w .,'-]{2,60}?)(?:[.;]|\s+(?:and|with|since)\b)", doc.text)
            if m:
                val = m.group(1).strip(" ,")
                if val not in seen:
                    seen.add(val)
                    out.append(Candidate(val, "pattern", 0.6, _snippet(doc.text, m.group(0))))
    return out


def _description(doc: PageDoc) -> list[Candidate]:
    out = []
    for org in _orgs(doc):
        d = _first_str(org.get("description"))
        if d:
            out.append(Candidate(d, "jsonld", 0.8, d[:200]))
    for key in ("description", "og:description", "twitter:description"):
        if doc.meta.get(key):
            out.append(Candidate(doc.meta[key], "meta", 0.75, f'<meta {key}="{doc.meta[key][:150]}">'))
            break
    return out


def _social(doc: PageDoc) -> list[Candidate]:
    links = []
    for url, _text in doc.links:
        host = (urlsplit(url).hostname or "").removeprefix("www.")
        if host in SOCIAL_HOSTS and urlsplit(url).path.strip("/") and "share" not in url:
            if url not in links:
                links.append(url)
    for org in _orgs(doc):
        same = org.get("sameAs")
        for u in same if isinstance(same, list) else [same] if same else []:
            if isinstance(u, str) and u not in links:
                links.append(u)
    return [Candidate(links[:10], "links", 0.8, ", ".join(links[:3]))] if links else []


def _is_pricing_page(doc: PageDoc) -> bool:
    path = urlsplit(doc.url).path.lower()
    return any(w in path for w in ("pricing", "price", "plans", "preise", "tarif")) or "pricing" in doc.title.lower()


def _pricing(doc: PageDoc) -> list[Candidate]:
    out = []
    for item in doc.jsonld:
        offers = item.get("offers")
        for offer in offers if isinstance(offers, list) else [offers] if isinstance(offers, dict) else []:
            price, cur = _first_str(offer.get("price")), _first_str(offer.get("priceCurrency"))
            if price:
                out.append(Candidate(f"{price} {cur or ''}".strip(), "jsonld", 0.85, f"JSON-LD Offer {price} {cur}"))
    if _is_pricing_page(doc):
        prices = list(dict.fromkeys(m.group().strip() for m in PRICE_RE.finditer(doc.text)))[:8]
        if prices:
            out.append(Candidate("; ".join(prices), "pricing_page", 0.7, _snippet(doc.text, prices[0])))
        else:
            m = CONTACT_SALES_RE.search(doc.text)
            if m:
                out.append(Candidate("Contact sales (no public prices)", "pricing_page", 0.6,
                                     _snippet(doc.text, m.group())))
    return out


def _founded(doc: PageDoc) -> list[Candidate]:
    out = []
    for org in _orgs(doc):
        d = _first_str(org.get("foundingDate"))
        if d and YEAR_RE.search(d):
            out.append(Candidate(YEAR_RE.search(d).group(), "jsonld", 0.9, f"JSON-LD foundingDate = {d}"))
    for value, evidence in _label_values(doc, list(FOUNDED_LABELS)):
        m = YEAR_RE.search(value)
        if m:
            out.append(Candidate(m.group(), "label", 0.65, evidence))
    # "Founded in 1916" is the company's only when the sentence is about the company: "we were founded in",
    # "the company was founded in", "Boeing was founded in". A subsidiary, tenant or partner ("Semmes ... was
    # founded in 1887", "CDL Systems was founded in 1992" on a product page) is not.
    brand = (registered_domain(doc.url) or "").split(".")[0]
    path = urlsplit(doc.url).path.strip("/")
    for m in re.finditer(r"\b(?:founded|established|incorporated) in (1[89]\d\d|20[0-4]\d)\b", doc.text, re.I):
        before = doc.text[max(0, m.start() - 60):m.start()].lower()
        subject = re.split(r"[.!?;]\s", before)[-1]  # the start of this sentence
        about_us = re.search(r"\b(we|our company|the company|the corporation)\b", subject)
        named = brand and brand in subject.replace(" ", "").replace("-", "") and path.count("/") <= 1
        if about_us or named:
            out.append(Candidate(m.group(1), "pattern", 0.6, _snippet(doc.text, m.group(0))))
            break
    return out


CTA_RE = re.compile(r"^(learn|see|back to|find out|get( a| started)?|read|explore|discover|meet|watch|try|start|"
                    r"sign|request|contact|view|what|why|how|more|overview|home|all |shop|buy|download|book)\b", re.I)
ICON_TEXT_RE = re.compile(r"(arrow|chevron|caret)[-_ ]?(right|left|down|up)$", re.I)


def _product_categories(doc: PageDoc) -> list[Candidate]:
    names = []
    for url, raw in doc.links:
        text = ICON_TEXT_RE.sub("", raw).strip()
        path = urlsplit(url).path.lower()
        product_path = re.match(r"^/(?:[a-z]{2}/)?(products?|solutions?|platform|services)/[^/]+/?$", path)
        if product_path and 2 <= len(text) <= 60 and not CTA_RE.match(text):
            if text not in names:
                names.append(text)
    for item in doc.jsonld:
        if _types(item) & {"Product", "SoftwareApplication", "Service"}:
            n = _first_str(item.get("name"))
            if n and n not in names:
                names.append(n)
    return [Candidate(names[:15], "nav_links", 0.6, ", ".join(names[:5]))] if names else []


# --- user rules -------------------------------------------------------------------------------


def _jsonld_path(doc: PageDoc, path: str) -> list[str]:
    type_name, _, key = path.partition(".")
    values = []
    for item in doc.jsonld:
        if type_name in _types(item) or type_name == "*":
            cur: Any = item
            for part in key.split("."):
                cur = cur.get(part) if isinstance(cur, dict) else None
            v = _first_str(cur)
            if v:
                values.append(v)
    return values


def _rule_candidates(doc: PageDoc, spec: FieldSpec) -> list[Candidate]:
    r = spec.rules
    out: list[Candidate] = []
    for sel in r.css:
        try:
            nodes = doc.tree.css(sel)
        except Exception:  # noqa: BLE001 - invalid selector from user config
            continue
        for node in nodes[:20]:
            text = node.attributes.get("content") or node.attributes.get("href") or node.text(separator=" ", strip=True)
            if text:
                out.append(Candidate(text, "css", 0.85, f"{sel} → {text[:120]}"))
    for key in r.meta:
        if doc.meta.get(key.lower()):
            out.append(Candidate(doc.meta[key.lower()], "meta", 0.8, f'<meta {key}="{doc.meta[key.lower()][:120]}">'))
    for path in r.jsonld:
        for v in _jsonld_path(doc, path):
            out.append(Candidate(v, "jsonld", 0.85, f"JSON-LD {path} = {v[:120]}"))
    if r.regex:
        for m in re.finditer(r.regex, doc.text[:200_000]):
            value = m.group(1) if m.groups() else m.group(0)
            out.append(Candidate(value, "regex", 0.6, _snippet(doc.text, m.group(0))))
            if len(out) > 50:
                break
    labels = r.labels or ([spec.label, spec.name.replace("_", " ")] if spec.semantic == Semantic.none else [])
    for value, evidence in _label_values(doc, labels):
        out.append(Candidate(value, "label", 0.55, evidence))
    return out


def extract_field(doc: PageDoc, spec: FieldSpec) -> list[Candidate]:
    s = spec.semantic
    if s == Semantic.company_name:
        found = _company_name(doc)
    elif s == Semantic.website_url:
        found = _website(doc)
    elif s == Semantic.contact_email:
        found = _emails(doc)
    elif s == Semantic.phone:
        found = _phones(doc)
    elif s in (Semantic.address, Semantic.headquarters, Semantic.country):
        found = _addresses(doc, s.value)
    elif s == Semantic.description:
        found = _description(doc)
    elif s == Semantic.page_title:
        found = [Candidate(doc.title, "title", 0.9, f"<title>{doc.title}</title>")] if doc.title else []
    elif s == Semantic.social_links:
        found = _social(doc)
    elif s == Semantic.pricing:
        found = _pricing(doc)
    elif s == Semantic.founded_year:
        found = _founded(doc)
    elif s == Semantic.product_categories:
        found = _product_categories(doc)
    elif s == Semantic.industry:
        # Registries (Wikidata, SEC) supply the industry as a discovery hint; pages rarely state it.
        found = [Candidate(v, "label", 0.5, ev) for v, ev in _label_values(doc, ["industry", "sector"])]
    elif s == Semantic.source_url:
        found = [Candidate(doc.url, "page_url", 1.0, doc.url)]
    else:
        found = []
    # User rules come first: they are explicit instructions for this field.
    return _rule_candidates(doc, spec) + found


def extract_page(doc: PageDoc, fields: list[FieldSpec]) -> dict[str, list[Candidate]]:
    return {f.name: extract_field(doc, f) for f in fields}


_EXEC_ROLE_RE = re.compile(
    r"\b(?:chief\s+[a-z]+\s+officer|ceo|cto|cfo|coo|ciso|cmo|cro|president|"
    r"co-?founder|founder|chair(?:man|person|woman)|managing\s+(?:director|partner)|"
    r"vice\s+president|svp|evp|vp\b|general\s+counsel|head\s+of\s+[a-z]+)\b",
    re.I,
)


def extract_leadership(doc: PageDoc) -> list[tuple[str, str]]:
    """Extract (full_name, raw_role) pairs from Schema.org Person / leadership cards without guessing emails."""
    out: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add_pair(raw_name: str | None, raw_role: str | None) -> None:
        name = " ".join((raw_name or "").split()).strip(" ,|-•")
        role = " ".join((raw_role or "").split()).strip(" ,|-•")
        if not name or not role or len(name) > 80 or len(role) > 120:
            return
        words = name.split()
        if not (2 <= len(words) <= 5) or any(ch.isdigit() for ch in name) or "@" in name:
            return
        key = (name.lower(), role.lower())
        if key not in seen:
            seen.add(key)
            out.append((name, role))

    for item in doc.jsonld:
        types = _types(item)
        if "Person" in types:
            add_pair(_first_str(item.get("name")), _first_str(item.get("jobTitle") or item.get("roleName")))
        for f_key in ("founder", "founders"):
            f_val = item.get(f_key)
            for f in f_val if isinstance(f_val, list) else [f_val] if isinstance(f_val, dict) else []:
                if isinstance(f, dict):
                    add_pair(_first_str(f.get("name")), _first_str(f.get("jobTitle")) or "founder")

    for h in doc.tree.css("h2, h3, h4"):
        name = " ".join(h.text(separator=" ", strip=True).split())
        if not (2 <= len(name.split()) <= 5) or len(name) > 60:
            continue
        sib = h.next
        steps = 0
        while sib is not None and steps < 3:
            steps += 1
            txt = " ".join(sib.text(separator=" ", strip=True).split())
            if txt and len(txt) <= 90 and _EXEC_ROLE_RE.search(txt) and txt.lower() != name.lower():
                add_pair(name, txt)
                break
            sib = sib.next
    return out
