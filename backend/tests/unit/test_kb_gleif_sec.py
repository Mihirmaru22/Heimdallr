"""Tests for bulk GLEIF LEI2 and SEC EDGAR loaders."""

from __future__ import annotations

import csv
import io
import json
import zipfile

from app.kb import gleif, sec_bulk


def test_gleif_scans_zip_rows(tmp_path):
    headers = [src for _, src in gleif.SOURCE_HEADERS]
    rows = [
        ["5493001KJTIIGC8Y1R12", "ACME PAYMENTS LTD", "ACTIVE", "ISSUED", "GENERAL", "8888", "LTD",
         "GB", "GB", "GB-LND", "LONDON", "e1 6an", "1 High Street",
         "GB", "LONDON", "e1 6an", "1 High Street", "2020-01-15T00:00:00Z", "2026-01-15T00:00:00Z"],
        ["54930099999999999999", "OLD CORP INC", "INACTIVE", "LAPSED", "GENERAL", "8888", "CORP",
         "US", "US", "US-DE", "WILMINGTON", "19801", "100 Main St",
         "US", "AUSTIN", "78701", "200 Congress", "2018-05-01T00:00:00Z", ""],
    ]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(headers)
    w.writerows(rows)
    zpath = tmp_path / "gleif.zip"
    with zipfile.ZipFile(zpath, "w") as z:
        z.writestr("lei2.csv", buf.getvalue())

    out: list[tuple] = []
    cov = gleif.scan(gleif.iter_rows(zpath), out.append)
    assert cov.rows == 2
    first = dict(zip(gleif.COLUMNS, out[0], strict=True))
    assert first["lei"] == "5493001KJTIIGC8Y1R12"
    assert first["name_key"] == "acme payments"
    assert first["entity_status"] == "ACTIVE"
    assert (first["iso2"], first["city"], first["postcode"]) == ("GB", "london", "E1 6AN")
    assert str(first["registered_at"]) == "2020-01-15"
    assert cov.by_status == {"ACTIVE": 1, "INACTIVE": 1}


def test_sec_bulk_scans_tickers_and_submissions_zip(tmp_path):
    tickers = tmp_path / "tickers.json"
    tickers.write_text(json.dumps({
        "fields": ["cik", "name", "ticker", "exchange"],
        "data": [[320193, "Apple Inc.", "AAPL", "Nasdaq"]],
    }))
    sub_zip = tmp_path / "submissions.zip"
    with zipfile.ZipFile(sub_zip, "w") as z:
        z.writestr("CIK0000320193.json", json.dumps({
            "cik": "0000320193", "name": "Apple Inc.", "sic": "3571",
            "sicDescription": "Electronic Computers", "ein": "942404110",
            "entityType": "operating", "website": "https://www.apple.com",
            "addresses": {"business": {"street1": "One Apple Park Way", "city": "CUPERTINO",
                                       "stateOrCountry": "CA", "zipCode": "95014"}},
        }))
        # Chunked filing archive must be skipped cleanly
        z.writestr("CIK0000320193-submissions-001.json", "{}")

    out: list[tuple] = []
    cov = sec_bulk.scan(sec_bulk.iter_rows(tickers, sub_zip), out.append)
    assert cov.rows == 1
    row = dict(zip(sec_bulk.COLUMNS, out[0], strict=True))
    assert (row["cik"], row["ticker"], row["exchange"], row["rank"]) == (320193, "AAPL", "Nasdaq", 0)
    assert (row["domain"], row["city"], row["state"]) == ("apple.com", "cupertino", "CA")
    assert row["sic"] == "3571" and "Cupertino" in row["address"].title()
