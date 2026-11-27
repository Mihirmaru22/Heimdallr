"""Unit tests for S&P 500 domain selection and Wikidata SPARQL parsing."""

from __future__ import annotations

from app.kb.sp500 import (
    load_constituents,
    parse_sparql_cik_rows,
    parse_sparql_ticker_rows,
    pick_primary_website,
)


def test_constituents_csv_has_all_503_symbols():
    items = load_constituents()
    assert len(items) == 503
    assert items[0]["symbol"] == "AAPL"
    assert items[-1]["symbol"] == "NWS"


def test_pick_primary_website_prefers_corporate_com_over_foreign_and_foundation():
    assert pick_primary_website(
        ["https://www.msd.no/", "https://www.merck.com"],
        "Merck & Co., Inc.",
    ) == ("https://www.merck.com/", "merck.com")

    assert pick_primary_website(
        ["https://thekrogercozerohungerzerowastefoundation.com/", "https://ir.kroger.com/", "https://www.kroger.com"],
        "KROGER CO",
    ) == ("https://www.kroger.com/", "kroger.com")

    assert pick_primary_website(
        ["https://tw.micron.com", "https://micron.cn", "https://www.micron.com.jp", "https://www.micron.com/"],
        "MICRON TECHNOLOGY INC",
    ) == ("https://www.micron.com/", "micron.com")

    assert pick_primary_website(
        ["https://apple.com/az/", "https://apple.com/au/"],
        "Apple Inc.",
    ) == ("https://apple.com/", "apple.com")

    assert pick_primary_website(
        ["https://www.nasdaq.com/"],
        "Nasdaq, Inc. Common Stock",
    ) == ("https://www.nasdaq.com/", "nasdaq.com")


def test_parse_sparql_cik_rows_aggregates_websites_and_facts():
    bindings = [
        {
            "cik": {"value": "0000320193"},
            "item": {"value": "http://www.wikidata.org/entity/Q312"},
            "itemLabel": {"value": "Apple Inc."},
            "desc": {"value": "American multinational technology company"},
            "website": {"value": "https://www.apple.com/"},
            "industryLabel": {"value": "consumer electronics"},
            "emp": {"value": "164000"},
        },
        {
            "cik": {"value": "0000320193"},
            "item": {"value": "http://www.wikidata.org/entity/Q312"},
            "itemLabel": {"value": "Apple Inc."},
            "website": {"value": "https://apple.com/"},
            "industryLabel": {"value": "software industry"},
        },
    ]
    parsed = parse_sparql_cik_rows(bindings)
    rec = parsed[320193]
    assert rec["qid"] == "Q312"
    assert rec["employees"] == 164000
    assert rec["websites"] == ["https://www.apple.com/", "https://apple.com/"]
    assert rec["industries"] == ["consumer electronics", "software industry"]


def test_parse_sparql_ticker_rows_groups_by_upper_symbol():
    rows = parse_sparql_ticker_rows([
        {"ticker": {"value": "xom"}, "item": {"value": "http://www.wikidata.org/entity/Q156238"},
         "website": {"value": "https://corporate.exxonmobil.com/"}},
    ])
    assert rows["XOM"][0]["website"] == "https://corporate.exxonmobil.com/"
