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


def test_companies_house_load_and_overlap_with_pdl(tmp_path, dsn):
    from app.kb import companies_house as ch

    pdl_file = tmp_path / "pdl.csv"
    with open(pdl_file, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        w.writerow(["a", "acme uk ltd", "acme.co.uk", "computer software", "11-50", "", "united kingdom",
                    "england", "london", ""])
    pdl.load(pdl_file, dsn)
    reg = tmp_path / "ch.csv"
    with open(reg, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["CompanyName", " CompanyNumber", "RegAddress.PostTown", "CompanyStatus"])
        w.writerow(["ACME (UK) LIMITED", "01234567", "LONDON", "Active"])
        w.writerow(["NEWCO LIMITED", "07654321", "LEEDS", "Active"])
        w.writerow(["GONE LIMITED", "00000001", "LEEDS", "Dissolved"])
    coverage = ch.load(reg, dsn)
    assert coverage.rows == 3
    assert coverage.overlap == {"active": 2, "name_match": 1, "name_town_match": 1, "pdl_uk": 1}
    assert _count(dsn, "SELECT count(*) FROM kb.uk_company") == 3
    assert _count(dsn, "SELECT to_regclass('kb.pdl_uk_keys') IS NULL") is True


def test_biggest_companies_first_in_chosen_countries_skipping_read_ones(tmp_path, dsn):
    import psycopg

    from app.kb import homepages

    path = tmp_path / "mixed.csv"
    rows = [("big.com", "10001+", "united kingdom"), ("mid.com", "201-500", "india"),
            ("small.com", "1-10", "united states"), ("de.com", "10001+", "germany"),
            ("nosize.com", "", "india"), ("read.com", "5001-10000", "united kingdom")]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        for i, (site, size, country) in enumerate(rows):
            w.writerow([f"c{i}", site, site, "computer software", size, "", country, "", "", ""])
    pdl.load(path, dsn)
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(homepages.SCHEMA_SQL)
        homepages.save(conn, homepages.Homepage(domain="read.com", found=True, crawl="own"))
        got = homepages.select_domains(conn, limit=3, iso2="GB,IN,US", biggest_first=True)
        assert got == ["big.com", "mid.com", "small.com"]
        assert len(homepages.select_domains(conn, iso2="gb, in", biggest_first=True)) == 3
        assert homepages.select_domains(conn, iso2="GB,IN,US", biggest_first=True, sizes="51-500") == ["mid.com"]
    assert homepages.parse_sizes("51-500") == (51, 500) and homepages.parse_sizes("1001-")[0] == 1001
    assert homepages.parse_sizes("") is None
