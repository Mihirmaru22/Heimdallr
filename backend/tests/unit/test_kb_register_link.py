"""Unit tests for two-signal UK Company No, Indian CIN, and Wikidata LEI linking."""

from __future__ import annotations

from app.kb.register_link import extract_register_ids, norm_uk_number, parse_wikidata_lei_rows


def test_extract_register_ids_pulls_uk_company_numbers_and_cins_without_phone_false_positives():
    text = (
        "Registered in England and Wales No: 5444653. Call us at 02079460999. "
        "Scottish Co. Reg No. SC123456. "
        "Corporate Identification Number (CIN): L24299MH1977PLC019982."
    )
    uk, cin = extract_register_ids(text)
    assert [u[0] for u in uk] == ["05444653", "SC123456"]
    assert "02079460999" not in str(uk)
    assert [c[0] for c in cin] == ["L24299MH1977PLC019982"]
    assert norm_uk_number("5444653") == "05444653"


def test_parse_wikidata_lei_rows_extracts_valid_20_char_leis():
    rows = parse_wikidata_lei_rows([
        {"item": {"value": "http://www.wikidata.org/entity/Q312"}, "lei": {"value": "HWUPKR0MPOU8FGXBT394"}},
        {"item": {"value": "http://www.wikidata.org/entity/Q999"}, "lei": {"value": "BAD"}},
    ])
    assert rows == {"Q312": "HWUPKR0MPOU8FGXBT394"}


def test_parse_gleif_rr_parents(tmp_path):
    from app.kb import gleif

    csv_file = tmp_path / "rr.csv"
    csv_file.write_text(
        "Relationship.StartNode.NodeID,Relationship.StartNode.NodeIDType,"
        "Relationship.EndNode.NodeID,Relationship.EndNode.NodeIDType,"
        "Relationship.RelationshipType,Relationship.RelationshipStatus\n"
        "CHILD1,LEI,PARENT1,LEI,IS_DIRECTLY_CONSOLIDATED_BY,ACTIVE\n"
        "CHILD1,LEI,ULT1,LEI,IS_ULTIMATELY_CONSOLIDATED_BY,ACTIVE\n"
        "CHILD2,LEI,OLD1,LEI,IS_DIRECTLY_CONSOLIDATED_BY,INACTIVE\n",
        encoding="utf-8",
    )
    assert gleif.parse_parent_rows(csv_file) == [("CHILD1", "PARENT1", "ULT1", None)]
