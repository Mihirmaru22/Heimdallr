"""Plain-language questions read by a free model into a checked plan, with the rules as the fallback."""

import json

from app.llm.openrouter import LLMUnavailable, Reply
from app.spec.planner import plan_spec


class FakeRouter:
    def __init__(self, answer=None, error=None):
        self.answer, self.error, self.messages = answer, error, None

    async def chat(self, messages, **_kw):
        self.messages = messages
        if self.error:
            raise self.error
        text = self.answer if isinstance(self.answer, str) else json.dumps(self.answer)
        return Reply(text, "minimax/minimax-m3.1-flash:free")

    async def aclose(self):
        pass


async def test_a_technology_question_becomes_a_plan_with_its_filters():
    router = FakeRouter({"rows": "companies", "technology": "Teamcenter", "countries": ["USA"],
                         "technology_aliases": ["Siemens Teamcenter", " ", "Siemens Teamcenter"],
                         "details": ["contact_email", "phone", "address", "not_a_detail"], "max_results": 40})
    spec, by, notes = await plan_spec("give me the list of the companies in usa who uses teamcenter "
                                      "with contact info and address", [], router)
    assert by == "model:minimax/minimax-m3.1-flash:free"
    assert [f.name for f in spec.fields] == ["company_name", "website_url", "uses_technology", "contact_email",
                                             "phone", "address", "evidence", "evidence_url", "evidence_date",
                                             "evidence_type"]
    assert spec.fields[2].label == "Uses Teamcenter"
    d = spec.discovery
    assert d.countries == ["US"] and d.technology == "Teamcenter"
    assert d.technology_aliases == ["Siemens Teamcenter"]
    assert d.providers == ["sec_filings"]  # no industry: a list of random US companies is not worth checking
    assert any("Add an industry" in n for n in notes)
    assert spec.deduplication_keys == ["website_url"] and spec.record_scope == "site"


async def test_a_technology_question_outside_the_us_checks_company_websites():
    router = FakeRouter({"rows": "companies", "technology": "SAP", "countries": ["DE"], "industry": "automotive",
                         "max_results": 20})
    spec, _by, notes = await plan_spec("german car makers using sap", [], router)
    assert "sec_filings" not in spec.discovery.providers and "wikidata" in spec.discovery.providers
    assert spec.discovery.max_results == 60  # three companies checked per row asked for
    assert spec.crawl.priority_keywords[0] == "career"
    assert any("websites of up to 60" in n for n in notes) and not any("SEC" in n for n in notes)


async def test_a_bare_technology_question_searches_filings_and_asks_for_a_filter():
    router = FakeRouter({"rows": "companies", "technology": "Teamcenter"})
    spec, _by, notes = await plan_spec("who uses teamcenter", [], router)
    assert spec.discovery.providers == ["sec_filings"] and spec.discovery.max_results == 50
    assert any("Add an industry" in n for n in notes)


async def test_keywords_alone_never_bring_a_list_of_random_companies_to_a_technology_question():
    router = FakeRouter({"rows": "companies", "technology": "SAP S/4HANA", "countries": ["US"],
                         "keywords": ["SAP", "contact info"]})
    spec, _by, notes = await plan_spec("US companies that use SAP S/4HANA, with website and contact info", [],
                                       router)
    assert spec.discovery.providers == ["sec_filings"]
    assert any("Add an industry" in n for n in notes)


async def test_sites_of_one_company_with_a_custom_detail():
    router = FakeRouter({"rows": "sites", "parent_company": "Ford", "details": ["address", "phone"],
                         "custom_details": [{"label": "Plant head", "description": "who runs the plant"}]})
    spec, _by, notes = await plan_spec("list the manufacturing plants of ford with plant head and contacts", [],
                                       router)
    assert spec.entity == "site" and spec.record_scope == "page" and spec.deduplication_keys == []
    plant_head = next(f for f in spec.fields if f.name == "plant_head")
    assert plant_head.label == "Plant head" and plant_head.description == "who runs the plant"
    assert spec.discovery.parent_company == "Ford"
    assert any("Ford" in n for n in notes) and any("Plant head" in n for n in notes)


async def test_the_model_cannot_set_limits_or_providers():
    router = FakeRouter({"rows": "companies", "industry": "pharmaceutical", "countries": ["IN"],
                         "max_results": 1000, "providers": ["seeds"], "crawl": {"max_pages": 999999},
                         "details": ["phone"]})
    spec, _by, _notes = await plan_spec("pharma companies in india", [], router)
    assert spec.crawl.max_pages == 2000 and spec.discovery.providers == ["wikidata", "gleif", "searxng"]


async def test_no_model_or_a_bad_answer_falls_back_to_the_rules():
    question = "Find up to 30 pharmaceutical companies in Germany with website and phone"
    spec, by, notes = await plan_spec(question, [], FakeRouter(error=LLMUnavailable("no key")))
    assert by == "rules" and "no key" in notes[0] and spec.discovery.countries == ["DE"]
    spec, by, notes = await plan_spec(question, [], FakeRouter("Sure! Here are some companies: Bayer, ..."))
    assert by == "rules" and "could not be used" in notes[0]
    spec, by, _notes = await plan_spec(question, [], FakeRouter({"rows": "planets"}))
    assert by == "rules"


async def test_start_urls_still_come_from_the_question():
    router = FakeRouter({"rows": "companies", "details": ["contact_email"]})
    spec, _by, _notes = await plan_spec("emails from acme.com and https://beta.io/about", [], router)
    assert spec.crawl.start_urls == ["https://beta.io/about", "https://acme.com/"]
    assert spec.discovery.providers == ["seeds"]
