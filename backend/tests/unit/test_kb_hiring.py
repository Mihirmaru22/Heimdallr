"""Unit tests for ATS job-board discovery and structured department parsing."""

from __future__ import annotations

from app.kb import hiring


def test_parse_ats_board_recognizes_greenhouse_eu_lever_and_ashby():
    assert hiring.parse_ats_board("https://job-boards.eu.greenhouse.io/abbyy/jobs/4926103101") == (
        "greenhouse", "abbyy", "https://boards-api.eu.greenhouse.io/v1/boards/abbyy/jobs?content=false"
    )
    assert hiring.parse_ats_board("https://jobs.lever.co/bhhc") == (
        "lever", "bhhc", "https://api.lever.co/v0/postings/bhhc?mode=json"
    )
    assert hiring.parse_ats_board("https://jobs.ashbyhq.com/delinea") == (
        "ashby", "delinea", "https://api.ashbyhq.com/posting-api/job-board/delinea"
    )


def test_extract_department_counts_from_ats_payloads():
    gh = {"jobs": [
        {"departments": [{"name": "Engineering"}]},
        {"departments": [{"name": "Engineering"}]},
        {"departments": [{"name": "Sales"}]},
    ]}
    assert hiring.extract_department_counts("greenhouse", gh) == (3, {"Engineering": 2, "Sales": 1})
    lv = [{"categories": {"department": "Revenue"}}, {"categories": {"team": "Data"}}]
    assert hiring.extract_department_counts("lever", lv) == (2, {"Revenue": 1, "Data": 1})
    ab = {"jobs": [{"department": "Security"}, {"department": "Security"}]}
    assert hiring.extract_department_counts("ashby", ab) == (2, {"Security": 2})
