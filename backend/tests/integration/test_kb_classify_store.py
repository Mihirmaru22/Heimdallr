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
        c.execute("CREATE TABLE kb.pdl_company (domain text, name text, industry text, sector text, "
                  "size text, iso2 text)")
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
    picked = teach.select_pages(conn, 8, "m")
    assert sum(r[7] == "Technology" for r in picked) == 4 and len(picked) == 8
    teach.save(conn, picked[0][0], teach.parse(picked[0][0], '{"real_page": true, "tech_company": false, '
                                               '"micro_sector": "none", "offering": "service", "reason": ""}'),
               "m", 1.0, None)
    assert picked[0][0] not in {r[0] for r in teach.select_pages(conn, 100, "m")}
    assert [r[0] for r in teach.select_pages(conn, 100, "other", same_as="m")] == [picked[0][0]]
    teach.save(conn, picked[0][0], None, "other", 1.0, "ValueError: x")  # a second model, same page
    assert conn.execute("SELECT count(*) FROM kb.teach_label").fetchone()[0] == 2


def test_teach_table_from_before_gets_the_two_column_key(conn):
    conn.execute("DROP TABLE kb.teach_label")
    conn.execute("CREATE TABLE kb.teach_label (domain text PRIMARY KEY, real_page boolean, tech_company boolean, "
                 "micro_sector text, offering text, reason text, raw text, error text, model text NOT NULL, "
                 "seconds real, labelled_at timestamptz NOT NULL DEFAULT now())")
    conn.execute(teach.SCHEMA_SQL)
    conn.execute(teach.SCHEMA_SQL)  # twice is fine
    teach.save(conn, "a.com", None, "m1", 1.0, "e")
    teach.save(conn, "a.com", None, "m2", 1.0, "e")
    assert conn.execute("SELECT count(*) FROM kb.teach_label").fetchone()[0] == 2


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


def test_pages_exported_for_claude_come_back_as_checked_labels(conn, tmp_path):
    for d in ("a.com", "b.com", "c.com"):
        _homepage(conn, d, f"{d} sells things")
    out = tmp_path / "pages.csv"
    assert teach.export_pages(conn, out, 10, "claude") == 3
    rows = list(csv.DictReader(out.open(encoding="utf-8")))
    assert {r["domain"] for r in rows} == {"a.com", "b.com", "c.com"} and rows[0]["page"]
    filled = {"a.com": ("true", "true", "cybersecurity", "product"), "b.com": ("no", "", "", ""),
              "c.com": ("true", "true", "blockchain", "product")}
    for r in rows:
        r["real_page"], r["tech_company"], r["micro_sector"], r["offering"] = filled[r["domain"]]
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    summary = teach.import_labels(conn, out, "claude")
    assert summary.rows == 3 and summary.tech == 1 and sum(summary.errors.values()) == 1
    got = dict(conn.execute("SELECT domain, coalesce(micro_sector, error) FROM kb.teach_label "
                            "WHERE model = 'claude'").fetchall())
    assert got["a.com"] == "cybersecurity" and got["b.com"] is None and got["c.com"].startswith("ValueError")
    assert teach.export_pages(conn, out, 10, "claude") == 0


def test_uncertain_export_puts_the_pages_the_classifier_doubts_first(conn):
    conn.execute(classify.SCHEMA_SQL)
    scores = {"sure.com": (0.99, 0.01, False, None), "edge.com": (0.95, 0.52, True, None),
              "micro.com": (0.97, 0.9, True, None), "known.com": (0.98, 0.95, True, "fintech"),
              "junk.com": (0.45, 0.1, None, None)}
    for d, (real, tech, is_tech, micro) in scores.items():
        _homepage(conn, d)
        conn.execute("INSERT INTO kb.company_label (domain, real_score, tech_score, tech_company, micro_sector, "
                     "model) VALUES (%s, %s, %s, %s, %s, 'fake')", (d, real, tech, is_tech, micro))
    _homepage(conn, "new.com")  # never classified
    picked = {r[0] for r in teach.select_pages(conn, 4, "claude", uncertain=True)}
    assert picked == {"edge.com", "micro.com", "junk.com", "new.com"}
    assert all(len(r) == 8 for r in teach.select_pages(conn, 4, "claude", uncertain=True))


def test_biggest_companies_exported_first_in_chosen_countries(conn):
    sizes = {"big.co": ("10001+", "GB"), "mid.co": ("201-500", "IN"), "small.co": ("1-10", "US"),
             "abroad.co": ("10001+", "DE"), "unknown.co": (None, "US")}
    for d, (size, iso2) in sizes.items():
        _homepage(conn, d, f"{d} makes things")
        conn.execute("INSERT INTO kb.pdl_company VALUES (%s, %s, 'retail', 'Retail and consumer goods', %s, %s)",
                     (d, d, size, iso2))
    got = [r[0] for r in teach.select_pages(conn, 3, "claude", biggest_first=True, countries="GB,IN,US")]
    assert got == ["big.co", "mid.co", "small.co"]
    mid = teach.select_pages(conn, 3, "claude", biggest_first=True, countries="GB,IN,US", sizes="51-500")
    assert [r[0] for r in mid] == ["mid.co"]
    assert teach.size_rank("10001+") == 10001 and teach.size_rank(None) == 0


def test_teacher_label_and_profile_replace_the_classifiers(conn, tmp_path):
    _homepage(conn, "acme.co", "payroll software")
    _homepage(conn, "shop.co", "shoes")
    c = classify.Classifier(fake_embed, train.train(examples(), "fake"))
    for label in c.label(["acme.co", "shop.co"], ["payroll software", "shoes"]):
        classify.save(conn, label, "fake", None)
    out = tmp_path / "labels.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["domain", "real_page", "tech_company", "micro_sector", "offering", "reason",
                    "sector", "niche", "offers", "address", "people", "audience"])
        w.writerow(["acme.co", "true", "true", "hr tech", "product", "payroll SaaS", "Technology",
                    "payroll software", "payroll app; HR portal", "1 High St, London",
                    "Jane Doe (CEO)", "B2B"])
        w.writerow(["shop.co", "true", "false", "none", "product", "", "Shops", "shoe shop", "shoes", "-", "",
                    "everyone"])
    teach.import_labels(conn, out, "claude")
    assert classify.apply_teacher(conn, "claude") == 2
    rows = {r[0]: r[1:] for r in conn.execute(
        "SELECT domain, model, micro_sector, sector, offers, address, real_score, people FROM kb.company_label")}
    assert rows["acme.co"] == ("teacher:claude", "hr tech", "Technology", "payroll app; HR portal",
                               "1 High St, London", 1.0, "Jane Doe (CEO)")
    assert rows["shop.co"][2:5] == (None, "shoes", None)  # unknown sector dropped, "-" address = unknown
    audience = dict(conn.execute("SELECT domain, audience FROM kb.company_label").fetchall())
    assert audience == {"acme.co": "b2b", "shop.co": None}  # outside the list = unknown


def test_contact_page_details_merge_with_homepage_labels_in_either_order(conn, tmp_path):
    from app.kb import pages

    conn.execute(pages.SCHEMA_SQL)
    for d in ("a.co", "b.co"):
        _homepage(conn, d, f"{d} sells software")
        conn.execute("INSERT INTO kb.pdl_company VALUES (%s, %s, 'computer software', 'Technology', '51-200', 'GB')",
                     (d, d))
        pages.save(conn, d, [pages.CompanyPage(d, "contact", f"https://{d}/contact", "Contact", "1 High St"),
                             pages.CompanyPage(d, "job", f"https://{d}/jobs/1", "Engineer", "We use Salesforce")],
                   "")
    out = tmp_path / "contacts.csv"
    assert teach.export_contacts(conn, out, 10, "claude") == 2
    rows = list(csv.DictReader(out.open(encoding="utf-8")))
    assert "1 High St" in rows[0]["contact"] and "Salesforce" in rows[0]["jobs"]
    labels = tmp_path / "labels.csv"
    with labels.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["domain", "real_page", "tech_company", "micro_sector", "offering", "reason", "address"])
        w.writerow(["a.co", "true", "true", "crm and sales tech", "product", "", "-"])
    teach.import_labels(conn, labels, "claude")  # a.co: homepage label first
    found = tmp_path / "found.csv"
    with found.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["domain", "address", "phone", "email", "people", "tools"])
        w.writerow(["a.co", "1 High St, London", "+44 20 1234", "info@a.co", "-", "Salesforce; AWS"])
        w.writerow(["b.co", "2 Low St", "-", "-", "-", "SAP"])  # b.co: contact page first
    assert teach.import_profile(conn, found, "claude") == (1, 1)
    assert teach.select_pages(conn, 10, "claude")[0][0] == "b.co"  # still waiting for its homepage label
    assert teach.export_contacts(conn, out, 10, "claude") == 0
    teach.import_labels(conn, labels, "claude")  # the homepage pass again does not erase the contact details
    assert classify.apply_teacher(conn, "claude") == 1  # b.co has no homepage label yet
    row = conn.execute("SELECT address, phone, tools, micro_sector FROM kb.company_label "
                       "WHERE domain = 'a.co'").fetchone()
    assert row == ("1 High St, London", "+44 20 1234", "Salesforce; AWS", "crm and sales tech")
