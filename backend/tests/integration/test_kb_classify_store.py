"""Homepage labels in Postgres: saved once per domain, and exported with the page for checking."""

from __future__ import annotations

import csv

import pytest

from app.kb import classify, homepages, pdl
from tests.unit.test_kb_classify import fake_embed


@pytest.fixture
def conn(database):
    import psycopg

    with psycopg.connect(pdl.kb_dsn(), autocommit=True) as c:
        c.execute("DROP SCHEMA IF EXISTS kb CASCADE")
        c.execute(homepages.SCHEMA_SQL)
        c.execute(classify.SCHEMA_SQL)
        yield c


def test_save_upserts_and_export_writes_the_page_with_empty_check_columns(conn, tmp_path):
    for domain in ("pay.example", "bakery.example"):
        homepages.save(conn, homepages.Homepage(domain=domain, found=True, crawl="own",
                                                url=f"https://{domain}/", title=domain, text="hello"))
    c = classify.Classifier(fake_embed)
    labels = c.label(["pay.example", "bakery.example"],
                     [classify.MICRO_SECTORS["payments"], "fresh sourdough croissants"])
    for label in labels:
        classify.save(conn, label, "fake", f"https://{label.domain}/")
    classify.save(conn, labels[0], "fake", "https://pay.example/")  # again: one row per domain
    assert conn.execute("SELECT count(*) FROM kb.company_label").fetchone()[0] == 2

    out = tmp_path / "sample.csv"
    assert classify.export_sample(conn, out, 10) == 2  # no kb.pdl_company here: pdl_sector is empty
    rows = list(csv.DictReader(out.open(encoding="utf-8")))
    by_domain = {r["domain"]: r for r in rows}
    assert by_domain["pay.example"]["micro_sector"] == "payments"
    assert by_domain["bakery.example"]["micro_sector"] == ""
    assert all(r["correct_micro_sector"] == "" and r["correct_offering"] == "" for r in rows)
