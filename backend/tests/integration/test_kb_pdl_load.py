"""Loading PDL into Postgres: the new table replaces the old only when its checks pass."""

from __future__ import annotations

import csv

import pytest

from app.kb import pdl

HEADER = ["id", "name", "website", "industry", "size", "founded", "country", "region", "locality",
          "linkedin_url"]


def _file(path, n):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        for i in range(n):
            w.writerow([f"c{i}", f"Company {i}", f"company{i}.com", "computer software", "11-50", "2010",
                        "germany", "berlin", "berlin", ""])
    return path


@pytest.fixture
def dsn(database):
    import psycopg

    url = pdl.kb_dsn()
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute("DROP SCHEMA IF EXISTS kb CASCADE")
    return url


def _count(dsn, sql):
    import psycopg

    with psycopg.connect(dsn) as conn:
        return conn.execute(sql).fetchone()[0]


def test_load_swaps_in_and_refuses_a_truncated_file(tmp_path, dsn):
    pdl.load(_file(tmp_path / "full.csv", 100), dsn)
    assert _count(dsn, "SELECT count(*) FROM kb.pdl_company") == 100
    assert _count(dsn, "SELECT count(*) FROM kb.pdl_company WHERE sector = 'Technology' AND iso2 = 'DE'") == 100
    assert _count(dsn, "SELECT max(domain_rows) FROM kb.pdl_company") == 1

    with pytest.raises(ValueError, match="refused"):
        pdl.load(_file(tmp_path / "short.csv", 50), dsn)
    assert _count(dsn, "SELECT count(*) FROM kb.pdl_company") == 100  # old table untouched
    assert _count(dsn, "SELECT to_regclass('kb.pdl_company_load') IS NULL") is True

    pdl.load(tmp_path / "short.csv", dsn, force=True)
    assert _count(dsn, "SELECT count(*) FROM kb.pdl_company") == 50
    assert _count(dsn, "SELECT count(*) FROM kb.load_log") == 2
