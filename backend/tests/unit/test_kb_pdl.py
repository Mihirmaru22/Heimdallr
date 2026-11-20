"""The PDL loader's parsing and derived fields, with no database."""

from __future__ import annotations

import csv
import gzip
import json
import zipfile

from app.kb import pdl

HEADER = ["id", "name", "website", "industry", "size", "founded", "country", "region", "locality",
          "linkedin_url"]
ROWS = [
    ["acme", "Acme Payments", "acmepay.com", "Financial Services", "51-200", "2015", "india",
     "maharashtra", "mumbai", "linkedin.com/company/acme"],
    ["blue", "Blue Pharma", "https://www.bluepharma.co.uk/about", "pharmaceuticals", "1001-5000", "1990",
     "united kingdom", "england", "london", "linkedin.com/company/blue"],
    ["nosite", "No Site Ltd", "", "", "1-10", "", "", "", "", ""],
    ["odd", "Odd Co", "linkedin.com/company/odd", "made-up industry", "11-50", "abc", "atlantis", "", "", ""],
]


def _write_csv(path, delimiter=","):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=delimiter)
        w.writerow(HEADER)
        w.writerows(ROWS)


def _by_id(path):
    return {r["id"]: r for r in pdl.read_rows(path)}


def test_reads_csv_pipe_json_gz_and_zip(tmp_path):
    _write_csv(tmp_path / "a.csv")
    _write_csv(tmp_path / "b.csv", delimiter="|")
    with open(tmp_path / "c.json", "w", encoding="utf-8") as f:
        for row in ROWS:
            f.write(json.dumps(dict(zip(HEADER, row, strict=True))) + "\n")
    with gzip.open(tmp_path / "d.csv.gz", "wt", encoding="utf-8") as f:
        f.write((tmp_path / "a.csv").read_text(encoding="utf-8"))
    with zipfile.ZipFile(tmp_path / "e.zip", "w") as z:
        z.write(tmp_path / "a.csv", "part1.csv")
        z.write(tmp_path / "c.json", "part2.json")
    for name in ("a.csv", "b.csv", "c.json", "d.csv.gz"):
        rows = _by_id(tmp_path / name)
        assert set(rows) == {"acme", "blue", "nosite", "odd"}, name
        assert rows["blue"]["locality"] == "london"
    assert len(list(pdl.read_rows(tmp_path / "e.zip"))) == 8


def test_derived_fields():
    row = dict(zip(pdl.COLUMNS, pdl.normalise(dict(zip(HEADER, ROWS[0], strict=True))), strict=True))
    assert row["domain"] == "acmepay.com"
    assert row["industry"] == "financial services"
    assert row["sector"] == "Financial services"
    assert (row["iso2"], row["region"], row["sub_region"]) == ("IN", "Asia", "Southern Asia")
    assert (row["state"], row["city"], row["founded"]) == ("maharashtra", "mumbai", 2015)

    blue = dict(zip(pdl.COLUMNS, pdl.normalise(dict(zip(HEADER, ROWS[1], strict=True))), strict=True))
    assert blue["domain"] == "bluepharma.co.uk"  # registered domain, not www. or the path
    assert blue["sector"] == "Healthcare and pharma"
    assert blue["region"] == "Europe"


def test_missing_and_unknown_values_stay_empty_and_are_reported():
    coverage = pdl.scan(dict(zip(HEADER, r, strict=True)) for r in ROWS)
    assert coverage.rows == 4
    assert coverage.filled["domain"] == 2  # a LinkedIn page is not the company's website
    assert coverage.filled["founded"] == 2
    assert coverage.unknown_industries == {"made-up industry": 1}
    assert coverage.unknown_countries == {"atlantis": 1}
    report = coverage.report()
    assert "Industries with no sector" in report and "'atlantis': 1" in report


def test_mapping_tables_cover_every_pdl_value():
    # PDL's canonical lists: 147 industries, 249 countries (docs.peopledatalabs.com, Nov 2026).
    assert len(pdl.industry_sectors()) == 147
    assert all(pdl.industry_sectors().values())
    regions = pdl.country_regions()
    assert len(regions) == 249
    assert all(iso2 and region and sub for iso2, region, sub in regions.values())


def test_shared_hosts_keep_the_company_subdomain():
    assert pdl._website_domain("girlhoodimpact.wixsite.com/girlhood-impact") == "girlhoodimpact.wixsite.com"
    assert pdl._website_domain("https://acme.github.io") == "acme.github.io"
    assert pdl._website_domain("www.example.co.uk:8080/x?y=1") == "example.co.uk"
    assert pdl._website_domain("not a website") == ""
