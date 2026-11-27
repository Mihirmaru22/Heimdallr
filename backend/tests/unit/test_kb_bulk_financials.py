"""Unit tests for UK Accounts iXBRL, India MCA, USAspending aggregation, and Wikidata People."""

from __future__ import annotations

import csv
import io
import zipfile

from app.kb import india_mca, people, uk_accounts, usaspending_bulk


def test_parse_uk_accounts_ixbrl_respects_scale_and_ignores_negative_employee_scale():
    html = """<html><body>
    <xbrli:context id="C"><xbrli:period><xbrli:endDate>2026-02-28</xbrli:endDate></xbrli:period></xbrli:context>
    <xbrli:context id="E"><xbrli:period><xbrli:endDate>2025-02-28</xbrli:endDate></xbrli:period></xbrli:context>
    <xbrli:unit id="GBP"><xbrli:measure>iso4217:GBP</xbrli:measure></xbrli:unit>
    <ix:nonNumeric name="bus:UKCompaniesHouseRegisteredNumber" contextRef="C">00094103</ix:nonNumeric>
    <ix:nonNumeric name="bus:BalanceSheetDate" contextRef="C">28 February 2026</ix:nonNumeric>
    <ix:nonNumeric name="bus:EntityDormantTruefalse" contextRef="C">false</ix:nonNumeric>
    <ix:nonFraction name="core:NetAssetsLiabilities" contextRef="C" scale="3">440</ix:nonFraction>
    <ix:nonFraction name="core:NetAssetsLiabilities" contextRef="E" scale="3">300</ix:nonFraction>
    <ix:nonFraction name="core:CashBankOnHand" contextRef="C" scale="0">71,743</ix:nonFraction>
    <ix:nonFraction name="core:AverageNumberEmployeesDuringPeriod" contextRef="C" scale="-2">7</ix:nonFraction>
    </body></html>"""
    row = uk_accounts.parse_ixbrl(html, "Prod223_4360_00094103_20260228.html")
    assert row is not None
    d = dict(zip(uk_accounts.COLUMNS, row, strict=True))
    assert d["company_number"] == "00094103"
    assert str(d["period_end"]) == "2026-02-28"
    assert d["net_assets"] == 440_000.0
    assert d["cash"] == 71_743.0
    assert d["employees"] == 7
    assert d["dormant"] is False


def test_india_mca_normalise_maps_cin_capital_and_email_domain():
    row = india_mca.normalise({
        "CORPORATE_IDENTIFICATION_NUMBER": "U72900KA2020PTC123456",
        "COMPANY_NAME": "Acme Software Private Limited",
        "COMPANY_STATUS": "Active",
        "COMPANY_CLASS": "Private",
        "DATE_OF_REGISTRATION": "15-05-2020",
        "AUTHORIZED_CAP": "1000000",
        "PAIDUP_CAP": "500000",
        "PRINCIPAL_BUSINESS_ACTIVITY_AS_PER_CIN": "Computer and related activities",
        "REGISTERED_STATE": "Karnataka",
        "EMAIL_ADDR": "compliance@acmesoft.in",
    })
    assert row is not None
    d = dict(zip(india_mca.COLUMNS, row, strict=True))
    assert d["cin"] == "U72900KA2020PTC123456"
    assert d["name_key"] == "acme software private"
    assert d["paidup_capital"] == 500000.0
    assert d["email_domain"] == "acmesoft.in"


def test_usaspending_scan_zip_aggregates_by_uei(tmp_path):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(list(usaspending_bulk.NEEDED_COLS))
    w.writerow(["UEI123456789", "Acme Defense Inc.", "", "", "USA", "VA", "Reston", "20190",
                "703-555-0199", "1000000.50", "2026-03-01", "Department of Defense", "541511"])
    w.writerow(["UEI123456789", "Acme Defense Inc.", "", "", "USA", "VA", "Reston", "20190",
                "703-555-0199", "250000.00", "2026-04-15", "Department of the Air Force", "541512"])
    zpath = tmp_path / "usa.zip"
    with zipfile.ZipFile(zpath, "w") as z:
        z.writestr("FY2026_1.csv", buf.getvalue())

    agg, cov = usaspending_bulk.scan_zip(zpath)
    assert cov.recipients == 1 and cov.transactions == 2
    rec = agg["UEI123456789"]
    assert rec["award_count"] == 2
    assert rec["total_obligated"] == 1250000.50
    assert rec["phone"] == "7035550199"
    assert str(rec["latest_action_date"]) == "2026-04-15"


def test_wikidata_people_parser_keeps_qid_and_source_url():
    bindings = [{
        "item": {"value": "http://www.wikidata.org/entity/Q312"},
        "prop": {"value": "http://www.wikidata.org/prop/P169"},
        "person": {"value": "http://www.wikidata.org/entity/Q265852"},
        "personLabel": {"value": "Tim Cook"},
        "start": {"value": "2011-08-24T00:00:00Z"},
    }]
    rows = people.parse_wikidata_leadership_rows(bindings, {"Q312": ("apple.com", 320193)})
    assert len(rows) == 1
    assert rows[0]["full_name"] == "Tim Cook"
    assert rows[0]["raw_role"] == "chief executive officer"
    assert rows[0]["person_qid"] == "Q265852"
    assert rows[0]["source_url"] == "https://www.wikidata.org/wiki/Q312"
