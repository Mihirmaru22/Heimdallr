"""Companies House snapshot parsing, with the header as the register publishes it."""

from __future__ import annotations

import csv
import io
import zipfile

from app.kb import companies_house as ch
from app.kb.pdl import read_rows

HEADER = ["CompanyName", " CompanyNumber", "RegAddress.CareOf", "RegAddress.POBox", "RegAddress.AddressLine1",
          " RegAddress.AddressLine2", "RegAddress.PostTown", "RegAddress.County", "RegAddress.Country",
          "RegAddress.PostCode", "CompanyCategory", "CompanyStatus", "CountryOfOrigin", "DissolutionDate",
          "IncorporationDate", "SICCode.SicText_1", "SICCode.SicText_2", "SICCode.SicText_3",
          "SICCode.SicText_4", "URI", "PreviousName_1.CONDATE", " PreviousName_1.CompanyName"]
ROWS = [
    ["ACME (UK) LIMITED", "01234567", "", "", "1 High Street", "Shoreditch", "LONDON", "", "UNITED KINGDOM",
     "e1 6an", "Private Limited Company", "Active", "United Kingdom", "", "05/03/2012",
     "62012 - Business and domestic software development", "None Supplied", "", "",
     "http://business.data.gov.uk/id/company/01234567", "01/01/2015", "ACME SOFTWARE LTD"],
    ["OLD CO PLC", "00000042", "", "", "", "", "LEEDS", "", "", "", "Public Limited Company", "Dissolved",
     "United Kingdom", "31/12/2020", "01/01/1990", "None Supplied", "", "", "", "", "", ""],
]


def _zip(tmp_path):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(HEADER)
    w.writerows(ROWS)
    path = tmp_path / "BasicCompanyDataAsOneFile-2026-11-01.zip"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("BasicCompanyDataAsOneFile-2026-11-01.csv", buf.getvalue())
    return path


def test_reads_the_snapshot_zip(tmp_path):
    coverage_rows: list[tuple] = []
    coverage = ch.scan(read_rows(_zip(tmp_path)), coverage_rows.append)
    assert coverage.rows == 2
    acme = dict(zip(ch.COLUMNS, coverage_rows[0], strict=True))
    assert acme["company_number"] == "01234567"
    assert acme["name_key"] == "acme"
    assert acme["status"] == "Active" and acme["category"] == "Private Limited Company"
    assert str(acme["incorporated"]) == "2012-03-05"
    assert (acme["post_town"], acme["postcode"]) == ("london", "E1 6AN")
    assert acme["sic_codes"] == ["62012"]
    assert acme["sic_text"] == ["62012 - Business and domestic software development"]
    assert acme["previous_names"] == ["ACME SOFTWARE LTD"]
    old = dict(zip(ch.COLUMNS, coverage_rows[1], strict=True))
    assert str(old["dissolved"]) == "2020-12-31" and old["sic_codes"] is None
    assert coverage.by_status == {"Active": 1, "Dissolved": 1}
    assert "Header as read" not in coverage.report()


def test_name_key_matches_pdl_style_names():
    assert ch.name_key("ACME (UK) LIMITED") == ch.name_key("acme uk ltd") == "acme"
    assert ch.name_key("Smith & Jones Plc") == "smith jones"
