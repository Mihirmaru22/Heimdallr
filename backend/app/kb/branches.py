"""Normalized company branch addresses (kb.company_branch): DB backfill + Overture Maps Places loader."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.extract.deterministic import ROLE_WORD_RE, addresses_from_text

SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS kb;
CREATE TABLE IF NOT EXISTS kb.company_branch (
    domain text NOT NULL,
    branch_label text NOT NULL DEFAULT '',
    full_address text NOT NULL,
    city text,
    region text,
    postal_code text,
    country text,
    phone text,
    email text,
    source text NOT NULL,
    url text,
    collected_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (domain, full_address)
);
ALTER TABLE kb.company_branch ADD COLUMN IF NOT EXISTS email text;
CREATE INDEX IF NOT EXISTS company_branch_country_idx ON kb.company_branch (country);
CREATE INDEX IF NOT EXISTS company_branch_postal_idx ON kb.company_branch (postal_code);
"""

STAC_CATALOG = "https://stac.overturemaps.org/catalog.json"
MAX_ADDR_LEN = 400
MAX_LABEL_LEN = 120


def _pick_role_email(emails: Sequence[Any] | None, domain: str) -> str | None:
    """Keep only first-party role mailboxes from Overture places (never personal or 3rd-party emails)."""
    for raw in emails or ():
        if not isinstance(raw, str) or "@" not in raw:
            continue
        em = raw.strip().lower()
        local, _, host = em.partition("@")
        if (host == domain or host.endswith("." + domain)) and ROLE_WORD_RE.search(local):
            return em
    return None


def _clean_text(value: Any, limit: int = 200) -> str | None:
    if not value:
        return None
    s = re.sub(r"\s+", " ", str(value)).replace("\x00", "").strip()
    return s[:limit] or None


def branch_row(
    domain: str,
    full_address: str,
    source: str,
    *,
    branch_label: str = "",
    city: str | None = None,
    region: str | None = None,
    postal_code: str | None = None,
    country: str | None = None,
    phone: str | None = None,
    email: str | None = None,
    url: str | None = None,
) -> tuple | None:
    addr = _clean_text(full_address, MAX_ADDR_LEN)
    dom = _clean_text(domain, 253)
    if not dom or not addr or len(addr) < 8:
        return None
    return (
        dom.lower(),
        (_clean_text(branch_label, MAX_LABEL_LEN) or ""),
        addr,
        _clean_text(city, 120),
        _clean_text(region, 80),
        _clean_text(postal_code, 32),
        _clean_text(country, 64),
        _clean_text(phone, 40),
        _clean_text(email, 254),
        source,
        _clean_text(url, 500),
    )


def rows_from_extracted(
    domain: str,
    addresses: Sequence[dict[str, Any]] | None,
    text: str | None,
    url: str | None,
    default_phone: str | None = None,
    default_email: str | None = None,
) -> list[tuple]:
    """Turn stored address dicts + plain-text fallback into deduplicated kb.company_branch rows."""
    seen: dict[str, tuple] = {}
    for item in addresses or ():
        if not isinstance(item, dict):
            continue
        raw = item.get("address")
        if not raw:
            continue
        row = branch_row(
            domain,
            str(raw),
            str(item.get("method") or "html"),
            city=item.get("city"),
            region=item.get("region"),
            postal_code=item.get("postal_code"),
            country=item.get("country"),
            phone=default_phone,
            email=default_email,
            url=url,
        )
        if row:
            seen.setdefault(row[2].lower(), row)
    for item in addresses_from_text(text or ""):
        row = branch_row(
            domain,
            item["address"],
            item.get("method") or "text",
            postal_code=item.get("postal_code"),
            country=item.get("country"),
            phone=default_phone,
            email=default_email,
            url=url,
        )
        if row and not any(_norm(row[2]) in _norm(k) or _norm(k) in _norm(row[2]) for k in seen):
            seen[row[2].lower()] = row
    return list(seen.values())


def _norm(s: str) -> str:
    return re.sub(r"\W+", "", s.lower())


def save_rows(conn, rows: Iterable[tuple]) -> int:
    """Upsert branch tuples into kb.company_branch in chunks."""
    batch: list[tuple] = []
    saved = 0
    now = datetime.now(UTC)
    sql = """
        INSERT INTO kb.company_branch
            (domain, branch_label, full_address, city, region, postal_code, country,
             phone, email, source, url, collected_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (domain, full_address) DO UPDATE SET
            branch_label = COALESCE(NULLIF(EXCLUDED.branch_label, ''), kb.company_branch.branch_label),
            city = COALESCE(EXCLUDED.city, kb.company_branch.city),
            region = COALESCE(EXCLUDED.region, kb.company_branch.region),
            postal_code = COALESCE(EXCLUDED.postal_code, kb.company_branch.postal_code),
            country = COALESCE(EXCLUDED.country, kb.company_branch.country),
            phone = COALESCE(EXCLUDED.phone, kb.company_branch.phone),
            email = COALESCE(EXCLUDED.email, kb.company_branch.email),
            url = COALESCE(EXCLUDED.url, kb.company_branch.url),
            collected_at = EXCLUDED.collected_at
    """
    for r in rows:
        batch.append((*r, now))
        if len(batch) >= 1000:
            with conn.cursor() as cur:
                cur.executemany(sql, batch)
            saved += len(batch)
            batch.clear()
    if batch:
        with conn.cursor() as cur:
            cur.executemany(sql, batch)
        saved += len(batch)
    return saved


def _first_field(items: Sequence[dict] | None, key: str) -> str | None:
    if items and isinstance(items[0], dict):
        return items[0].get(key)
    return None


def save_homepage(conn, domain: str, url: str | None, addresses: Sequence[dict] | None,
                  phones: Sequence[dict] | None, text: str | None,
                  emails: Sequence[dict] | None = None) -> int:
    conn.execute(SCHEMA_SQL)
    rows = rows_from_extracted(
        domain, addresses, text, url,
        default_phone=_first_field(phones, "phone"),
        default_email=_first_field(emails, "email"),
    )
    return save_rows(conn, rows) if rows else 0


def save_pages(conn, domain: str, pages: Sequence[Any]) -> int:
    conn.execute(SCHEMA_SQL)
    rows: list[tuple] = []
    for p in pages:
        rows.extend(rows_from_extracted(
            domain, p.addresses, p.text, p.url,
            default_phone=_first_field(getattr(p, "phones", None), "phone"),
            default_email=_first_field(getattr(p, "emails", None), "email"),
        ))
    dedup = {r[2].lower(): r for r in rows}
    return save_rows(conn, dedup.values()) if dedup else 0


def backfill_branches(conn, limit: int | None = None) -> tuple[int, int, int]:
    """Backfill plain-text addresses on empty homepage/company_page rows and populate kb.company_branch."""
    conn.execute(SCHEMA_SQL)
    hp_updated = 0
    cp_updated = 0
    branch_rows: list[tuple] = []
    hp_updates: list[tuple[str, str]] = []
    cp_updates: list[tuple[str, str, str]] = []

    h_rows = conn.execute(
        "SELECT domain, url, text, addresses, phones, emails FROM kb.homepage WHERE found ORDER BY domain LIMIT %s",
        (limit,),
    ).fetchall()
    for dom, url, text, addrs, phones, emails in h_rows:
        extracted = addresses_from_text(text or "") if not addrs else []
        if not addrs and extracted:
            addrs_to_save = [{"address": x["address"], "method": "text"} for x in extracted]
            hp_updates.append((json.dumps(addrs_to_save), dom))
            hp_updated += 1
        branch_rows.extend(rows_from_extracted(
            dom, addrs, text, url,
            default_phone=_first_field(phones, "phone"),
            default_email=_first_field(emails, "email"),
        ))

    if conn.execute("SELECT to_regclass('kb.company_page')").fetchone()[0]:
        p_rows = conn.execute(
            "SELECT domain, kind, url, text, addresses, phones, emails FROM kb.company_page "
            "WHERE kind IN ('contact', 'locations') ORDER BY domain, url LIMIT %s",
            (limit * 2 if limit else None,),
        ).fetchall()
        for dom, _kind, url, text, addrs, phones, emails in p_rows:
            extracted = addresses_from_text(text or "") if not addrs else []
            if not addrs and extracted:
                addrs_to_save = [{"address": x["address"], "method": "text"} for x in extracted]
                cp_updates.append((json.dumps(addrs_to_save), dom, url))
                cp_updated += 1
            branch_rows.extend(rows_from_extracted(
                dom, addrs, text, url,
                default_phone=_first_field(phones, "phone"),
                default_email=_first_field(emails, "email"),
            ))

    for i in range(0, len(hp_updates), 1000):
        with conn.cursor() as cur:
            cur.executemany("UPDATE kb.homepage SET addresses = %s WHERE domain = %s", hp_updates[i:i + 1000])
    for i in range(0, len(cp_updates), 1000):
        with conn.cursor() as cur:
            cur.executemany(
                "UPDATE kb.company_page SET addresses = %s WHERE domain = %s AND url = %s",
                cp_updates[i:i + 1000],
            )
    dedup = {(r[0], r[2].lower()): r for r in branch_rows}
    saved = save_rows(conn, dedup.values())
    return hp_updated, cp_updated, saved


def extract_domain_candidates(url: str) -> list[str]:
    """Host and parent-stripped host (e.g. stores.acme.com -> ['stores.acme.com', 'acme.com']) for domain join."""
    raw = (url or "").strip()
    if not raw:
        return []
    if "://" not in raw:
        raw = "https://" + raw
    host = (urlsplit(raw).hostname or "").lower().removeprefix("www.").rstrip(".")
    if not host or "." not in host:
        return []
    parts = host.split(".")
    out = [host]
    if len(parts) >= 3:
        out.append(".".join(parts[1:]))
    return out


def format_overture_address(addr: dict[str, Any]) -> tuple[str, str | None, str | None, str | None, str | None] | None:
    """Format an Overture Places address struct if it contains real street/locality/postcode data."""
    if not isinstance(addr, dict):
        return None
    freeform = _clean_text(addr.get("freeform"), 220)
    locality = _clean_text(addr.get("locality"), 120)
    region = _clean_text(addr.get("region"), 80)
    postcode = _clean_text(addr.get("postcode"), 32)
    country = _clean_text(addr.get("country"), 16)
    if not (freeform or locality or postcode):
        return None
    if country == "AQ" and not freeform:
        return None
    parts = [p for p in (freeform, locality, region, postcode, country) if p]
    dedup_parts: list[str] = []
    for p in parts:
        if not dedup_parts or p.lower() not in ", ".join(dedup_parts).lower():
            dedup_parts.append(p)
    full = ", ".join(dedup_parts)
    if len(full) < 8:
        return None
    return full[:MAX_ADDR_LEN], locality, region, postcode, country


def overture_parquet_urls(release: str | None = None) -> tuple[str, list[str]]:
    """Resolve Overture release tag and HTTPS GeoParquet shard URLs via the official STAC catalog."""
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        if not release:
            cat = client.get(STAC_CATALOG)
            cat.raise_for_status()
            release = cat.json()["latest"]
        col = client.get(f"https://stac.overturemaps.org/{release}/places/place/collection.json")
        col.raise_for_status()
        item_hrefs = [lnk["href"] for lnk in col.json().get("links", []) if lnk.get("rel") == "item"]
        urls: list[str] = []
        for href in item_hrefs:
            item = client.get(href)
            item.raise_for_status()
            aws_href = (item.json().get("assets") or {}).get("aws", {}).get("href")
            if aws_href:
                urls.append(aws_href)
        return release, urls


def load_overture(
    conn,
    release: str | None = None,
    parts: int | None = None,
    local_dir: str | None = None,
    homepages_only: bool = False,
) -> tuple[str, int, int]:
    """Stream Overture Maps Places GeoParquet shards via DuckDB and match physical branches to KB domains."""
    import tempfile

    import duckdb

    conn.execute(SCHEMA_SQL)
    copy_sql = (
        "COPY (SELECT domain FROM kb.homepage WHERE found AND domain IS NOT NULL) TO STDOUT"
        if homepages_only
        else "COPY (SELECT domain FROM kb.pdl_company WHERE domain IS NOT NULL) TO STDOUT"
    )
    if local_dir:
        shards = sorted(str(p) for p in Path(local_dir).glob("*.parquet"))
        rel_name = release or Path(local_dir).name
    else:
        rel_name, shards = overture_parquet_urls(release)
    if parts:
        shards = shards[:parts]

    duck = duckdb.connect()
    if not local_dir:
        duck.execute("INSTALL httpfs; LOAD httpfs;")

    with tempfile.NamedTemporaryFile(mode="wb", suffix=".txt", delete=True) as tmp:
        with conn.cursor().copy(copy_sql) as cp:
            for chunk in cp:
                tmp.write(chunk)
        tmp.flush()
        duck.execute(
            "CREATE TEMP TABLE kb_domains AS SELECT DISTINCT lower(trim(column0)) AS domain "
            "FROM read_csv(?, header=false, delim='\t', columns={'column0': 'VARCHAR'})",
            [tmp.name],
        )
    domain_count = duck.execute("SELECT count(*) FROM kb_domains").fetchall()[0][0]
    print(
        f"Loaded {domain_count:,} domains into DuckDB; scanning {len(shards)} Overture shard(s) ({rel_name})...",
        flush=True,
    )

    total_matched = 0
    total_saved = 0
    for idx, shard in enumerate(shards, 1):
        duck.read_parquet(shard).create_view("raw_shard", replace=True)
        query = """
            WITH raw AS (
                SELECT
                    names.primary AS place_name,
                    addresses,
                    websites,
                    phones,
                    emails
                FROM raw_shard
                WHERE websites IS NOT NULL AND len(websites) > 0
                  AND addresses IS NOT NULL AND len(addresses) > 0
                  AND (operating_status IS NULL OR operating_status = 'open')
            ),
            exploded AS (
                SELECT
                    place_name,
                    addresses,
                    phones,
                    emails,
                    unnest(websites) AS site_url
                FROM raw
            ),
            hosts AS (
                SELECT
                    place_name,
                    addresses,
                    phones,
                    emails,
                    site_url,
                    lower(regexp_replace(
                        split_part(split_part(regexp_replace(site_url, '^https?://', ''), '/', 1), '?', 1),
                        '^www\\.', ''
                    )) AS host
                FROM exploded
            ),
            cand AS (
                SELECT
                    place_name,
                    addresses,
                    phones,
                    emails,
                    site_url,
                    CASE WHEN k1.domain IS NOT NULL THEN k1.domain ELSE k2.domain END AS kb_domain
                FROM hosts e
                LEFT JOIN kb_domains k1 ON k1.domain = e.host
                LEFT JOIN kb_domains k2 ON k1.domain IS NULL AND k2.domain = regexp_replace(e.host, '^[^.]+\\.', '')
                WHERE k1.domain IS NOT NULL OR k2.domain IS NOT NULL
            )
            SELECT DISTINCT kb_domain, place_name, addresses, phones, emails, site_url
            FROM cand
        """
        rows = duck.execute(query).fetchall()
        batch_rows: dict[tuple[str, str], tuple] = {}
        for dom, place_name, addrs, phones, emails, site_url in rows:
            phone0 = phones[0] if phones else None
            email0 = _pick_role_email(emails, dom)
            for addr in addrs or ():
                fmt = format_overture_address(addr)
                if not fmt:
                    continue
                full, city, region, postal, country = fmt
                br = branch_row(
                    dom,
                    full,
                    "overture",
                    branch_label=place_name or "",
                    city=city,
                    region=region,
                    postal_code=postal,
                    country=country,
                    phone=phone0,
                    email=email0,
                    url=site_url,
                )
                if br:
                    batch_rows[(br[0], br[2].lower())] = br
        saved = save_rows(conn, batch_rows.values())
        total_matched += len(rows)
        total_saved += saved
        print(f"  shard {idx}/{len(shards)}: {len(rows):,} matches -> {saved:,} branch rows saved", flush=True)
    return rel_name, total_matched, total_saved
