"""Homepage labels in Postgres: teacher labels picked and saved, labels saved once per domain and exported."""

from __future__ import annotations

import csv

import pytest

from app.kb import classify, homepages, pdl, teach, train
from tests.unit.test_kb_classify import examples, fake_embed


@pytest.fixture
def conn(database):
    import psycopg

    with psycopg.connect(pdl.kb_dsn(), autocommit=True) as c:
        c.execute("DROP SCHEMA IF EXISTS kb CASCADE")
        c.execute(homepages.SCHEMA_SQL)
        c.execute(classify.SCHEMA_SQL)
        c.execute(teach.SCHEMA_SQL)
        c.execute("CREATE TABLE kb.pdl_company (domain text, name text, industry text, sector text)")
        yield c


def _homepage(conn, domain, text="hello"):
    homepages.save(conn, homepages.Homepage(domain=domain, found=True, crawl="own", url=f"https://{domain}/",
                                            title=domain, text=text))


def test_teacher_pages_mix_tech_and_the_rest_and_skip_labelled_ones(conn):
    for i in range(10):
        _homepage(conn, f"t{i}.com")
        _homepage(conn, f"r{i}.com")
        conn.execute("INSERT INTO kb.pdl_company VALUES (%s, %s, 'computer software', 'Technology')",
                     (f"t{i}.com", f"T{i}"))
    picked = teach.select_pages(conn, 8)
    assert sum(r[7] == "Technology" for r in picked) == 4 and len(picked) == 8
    teach.save(conn, picked[0][0], teach.parse(picked[0][0], '{"real_page": true, "tech_company": false, '
                                               '"micro_sector": "none", "offering": "service", "reason": ""}'),
               "m", 1.0, None)
    assert picked[0][0] not in {r[0] for r in teach.select_pages(conn, 100)}


def test_labels_upsert_and_export_with_pdl_industry(conn, tmp_path):
    _homepage(conn, "pay.example", "payroll software free trial")
    _homepage(conn, "law.example", "divorce solicitors consultation")
    conn.execute("INSERT INTO kb.pdl_company VALUES ('law.example', 'Law', 'law practice', 'Professional services')")
    c = classify.Classifier(fake_embed, train.train(examples(), "fake"))
    labels = c.label(["pay.example", "law.example"], ["payroll software free trial", "divorce solicitors"])
    for label in labels:
        classify.save(conn, label, "fake", f"https://{label.domain}/")
    classify.save(conn, labels[0], "fake", "https://pay.example/")  # again: one row per domain
    assert conn.execute("SELECT count(*) FROM kb.company_label").fetchone()[0] == 2
    out = tmp_path / "sample.csv"
    assert classify.export_sample(conn, out, 10) == 2
    rows = {r["domain"]: r for r in csv.DictReader(out.open(encoding="utf-8"))}
    assert rows["pay.example"]["micro_sector"] == "hr tech"
    assert rows["law.example"]["pdl_industry"] == "law practice"
