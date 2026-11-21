"""Teacher labels: the model's JSON answer is checked before it becomes a label."""

from __future__ import annotations

import json

import pytest

from app.kb import teach


def answer(**over):
    data = {"real_page": True, "tech_company": True, "micro_sector": "cybersecurity", "offering": "product",
            "reason": "sells endpoint security software"}
    data.update(over)
    return json.dumps(data)


def test_a_valid_answer_becomes_a_label():
    label = teach.parse("x.com", answer())
    assert (label.real_page, label.tech_company, label.micro_sector, label.offering) == (
        True, True, "cybersecurity", "product")


def test_not_a_tech_company_means_no_micro_sector():
    label = teach.parse("x.com", answer(tech_company=False))
    assert label.micro_sector is None


def test_a_junk_page_is_neither_tech_nor_offering():
    label = teach.parse("x.com", answer(real_page=False))
    assert label.tech_company is False and label.micro_sector is None and label.offering == "none"


@pytest.mark.parametrize("bad", [answer(micro_sector="space lasers"), answer(offering="maybe"),
                                 answer(real_page="yes"), "not json"])
def test_an_answer_outside_the_schema_is_an_error(bad):
    with pytest.raises(ValueError):
        teach.parse("x.com", bad)


def test_schema_offers_every_micro_sector_and_none():
    enum = teach.schema()["properties"]["micro_sector"]["enum"]
    assert "none" in enum and "cybersecurity" in enum


def test_page_for_model_keeps_title_description_and_opening_text():
    page = teach.page_for_model("Acme", "Security software", "word " * 1000)
    assert page.startswith("Acme\nSecurity software\nword ")
    assert len(page) <= len("Acme\nSecurity software\n") + teach.PAGE_CHARS


class FakeResponse:
    def __init__(self, content):
        self.content = content

    def raise_for_status(self):
        pass

    def json(self):
        return {"message": {"content": self.content}}


class FakeClient:
    def __init__(self, answers):
        self.answers, self.prompts = list(answers), []

    def post(self, url, json):
        self.prompts.append(json)
        return FakeResponse(self.answers.pop(0))


class FakeConn:
    def __init__(self):
        self.rows = []

    def execute(self, sql, params):
        self.rows.append(params)


def test_run_saves_labels_and_errors_and_one_bad_answer_fails_only_its_page():
    rows = [("a.com", "https://a.com/", "A", "", "security software", "A Ltd", "computer software", "Technology"),
            ("b.com", "https://b.com/", "B", "", "bakery", None, None, None)]
    client = FakeClient([answer(), "{broken"])
    conn = FakeConn()
    ticks = iter(range(10))
    summary = teach.run(conn, client, "m", rows, clock=lambda: next(ticks))
    assert summary.rows == 2 and summary.tech == 1 and sum(summary.errors.values()) == 1
    assert conn.rows[0][0] == "a.com" and conn.rows[0][3] == "cybersecurity"
    assert conn.rows[1][0] == "b.com" and conn.rows[1][7].startswith("JSONDecodeError")
    sent = client.prompts[0]
    assert sent["format"] == teach.schema() and sent["options"]["temperature"] == 0
    assert "LinkedIn industry (may be wrong): computer software" in sent["messages"][0]["content"]
