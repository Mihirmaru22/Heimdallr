"""Proof that a company uses a product: its names, verbatim quotes, who the company is to the product, and how
much the proof counts for."""

import json
from datetime import date

from app.evidence.judge import Judge, rule_relationship, score
from app.evidence.products import product_for
from app.evidence.quotes import document_text, find_mentions, verify_quote
from app.llm.openrouter import LLMUnavailable, Reply

TODAY = date(2026, 10, 21)


class Router:
    def __init__(self, *answers, error=None):
        self.answers, self.error, self.calls = list(answers), error, 0

    async def chat(self, messages, **_kw):
        self.calls += 1
        if self.error:
            raise self.error
        answer = self.answers.pop(0)
        return Reply(answer if isinstance(answer, str) else json.dumps(answer), "minimax/minimax-m3.1-flash:free")

    async def aclose(self):
        pass


def test_known_products_bring_their_other_names_and_short_names_never_count_alone():
    tc = product_for("teamcenter", ["Siemens Teamcenter", "TC"])
    assert tc.names[0] == "Teamcenter" and "TcPLM" in tc.names and "TC" not in tc.names
    sap = product_for("SAP")
    assert "SAP S/4HANA" in sap.names and "SAP" not in sap.names
    assert not sap.mentioned_in("Our SAP (sales and planning) team grew.")
    assert sap.mentioned_in("We completed our move to SAP S/4HANA in 2025.")
    # A lone short name the person typed is kept, but matched case-sensitively and as a whole word.
    ifs = product_for("IFS")
    assert ifs.names == ["IFS"] and ifs.mentioned_in("We run IFS Cloud.") and not ifs.mentioned_in("ifs and buts")
    assert not product_for("catia").mentioned_in("Catia Lopez joined the board.")


def test_quotes_are_whole_sentences_copied_word_for_word():
    html = ("<html><body><script>var Teamcenter = 1;</script><p>We design trucks.</p><p>In 2024 we completed the "
            "rollout of Siemens Teamcenter&nbsp;across our engineering sites. Revenue grew.</p>"
            "<p>Teamcenter also stores our bills of materials.</p></body></html>")
    text = document_text(html)
    quotes = find_mentions(text, product_for("Teamcenter"))
    assert quotes == ["In 2024 we completed the rollout of Siemens Teamcenter across our engineering sites.",
                      "Teamcenter also stores our bills of materials."]
    assert all(verify_quote(q, text) for q in quotes)
    assert not verify_quote("We completed the rollout of Teamcenter everywhere.", text)  # not in the document


def test_rules_settle_vendors_competitors_and_resellers():
    tc = product_for("Teamcenter")
    assert rule_relationship("SIEMENS AG", tc, "Teamcenter revenue grew.")[0] == "vendor"
    s4 = product_for("S/4HANA")
    assert rule_relationship("Rimini Street", s4, "We compete with SAP for S/4HANA support.")[0] == "competitor"
    assert rule_relationship("Hackett Group", s4, "We offer implementation services for S/4HANA.")[0] \
        == "partner_or_reseller"
    assert rule_relationship("Avient", s4, "We are implementing SAP S/4HANA across our plants.") is None


async def test_the_model_only_picks_a_relationship_and_one_of_our_quotes():
    router = Router({"relationship": "rolling_out", "quote": 2, "reason": "it is implementing it"},
                    {"relationship": "uses", "quote": 2, "reason": "second reading agrees it is in use"})
    judge = Judge(router)
    quotes = ["SAP S/4HANA is a risk.", "We are implementing SAP S/4HANA across our plants."]
    j = await judge.judge("Avient", product_for("SAP"), quotes, "10-K filed 2025-02-20")
    assert (j.relationship, j.quote, j.judged_by) == ("rolling_out", quotes[1], "model:minimax/minimax-m3.1-flash:free")
    # Text the model writes is never used as the quote.
    router.answers += [{"relationship": "uses", "quote": 9, "reason": "x", "quote_text": "made up"},
                       {"relationship": "uses", "quote": 1, "reason": "x"}]
    j = await judge.judge("Avient", product_for("SAP"), quotes, "10-K")
    assert j.quote == quotes[1]  # out of range: the last one given


class Models(Router):
    """Each call answered by a different free model, so a second reading is a second opinion."""

    async def chat(self, messages, **kw):
        reply = await super().chat(messages, **kw)
        return Reply(reply.text, f"model-{self.calls}:free")


async def test_a_sure_reading_is_taken_as_it_is_with_no_second_reading():
    router = Models({"relationship": "uses", "quote": 1, "reason": "in use", "sure": True})
    j = await Judge(router).judge("Coty", product_for("SAP S/4HANA"), ["S/4HANA went live at Coty plants."], "10-K")
    # The company's own filing, read once by a sure model: first-hand, so it keeps its strength.
    assert j.relationship == "uses" and not j.one_reading and router.calls == 1


async def test_an_unsure_reading_gets_a_second_and_disagreement_about_a_use_leaves_a_mention():
    quote = ["A manufacturer switched to our product during its S/4HANA migration."]
    router = Models({"relationship": "rolling_out", "quote": 1, "reason": "migrating", "sure": False},
                    {"relationship": "other_mention", "quote": 1, "reason": "a customer's migration"})
    j = await Judge(router).judge("Vertex", product_for("SAP"), quote, "10-K")
    assert j.relationship == "unreviewed" and "second reading says other_mention" in j.reason and router.calls == 2
    router = Models({"relationship": "uses", "quote": 1, "reason": "in use", "sure": False},
                    {"relationship": "uses", "quote": 1, "reason": "in use"})
    j = await Judge(router).judge("Coty", product_for("SAP S/4HANA"), ["S/4HANA went live at Coty plants."], "10-K")
    assert j.relationship == "uses" and not j.one_reading and "agrees" in j.reason


async def test_an_unsure_use_with_no_second_reading_possible_counts_for_less_instead_of_vanishing():
    class OneAnswer(Models):
        async def chat(self, messages, **kw):
            if self.calls:
                self.calls += 1
                raise LLMUnavailable("no free model answered")
            return await super().chat(messages, **kw)

    router = OneAnswer({"relationship": "uses", "quote": 1, "reason": "in use", "sure": False})
    j = await Judge(router, wait=0).judge("Davey", product_for("SAP S/4HANA"), ["S/4HANA runs Davey's finance."],
                                          "10-K")
    assert j.relationship == "uses" and j.one_reading and "no second reading could be made" in j.reason
    assert score(j.relationship, 0.85, "2026-02-01", TODAY, one_reading=True) == ("Likely", 0.69)
    # An older filing is weighed by its age only: one reading caps it, never pushes it out.
    assert score(j.relationship, 0.85, "2023-02-01", TODAY, one_reading=True) == \
        score(j.relationship, 0.85, "2023-02-01", TODAY) == ("Likely", 0.42)


async def test_without_a_model_proof_stays_unreviewed_and_the_model_is_not_asked_again():
    router = Router(error=LLMUnavailable("free requests used up for today"))
    judge = Judge(router)
    for _ in range(2):
        j = await judge.judge("Avient", product_for("SAP"), ["SAP S/4HANA handles order to cash."], "10-K")
        assert j.relationship == "unreviewed" and "used up" in j.judged_by
    assert router.calls == 1
    j = await Judge(Router("not json")).judge("Avient", product_for("SAP"), ["SAP S/4HANA handles order to cash."],
                                              "10-K")
    assert j.relationship == "unreviewed"


def test_score_weighs_the_relationship_and_the_age_of_the_proof():
    assert score("uses", 0.85, "2026-02-01", TODAY) == ("Confirmed", 0.85)
    assert score("uses", 0.85, "2023-02-01", TODAY) == ("Likely", 0.42)  # 3+ years old: halved
    assert score("uses", 0.85, "2019-02-01", TODAY) == ("Mentioned", 0.17)  # history
    assert score("evaluating", 0.85, "2026-02-01", TODAY) == ("Likely", 0.51)
    assert score("unreviewed", 0.85, "2026-02-01", TODAY) == ("Mentioned", 0.4)
    for rel in ("vendor", "competitor", "partner_or_reseller", "moved_away", "integrates_with", "other_mention"):
        assert score(rel, 0.85, "2026-02-01", TODAY) == ("", 0.0)


def test_a_quote_at_the_very_start_of_the_text_keeps_its_first_letter():
    text = "Our plants run SAP S/4HANA. Revenue grew."
    assert find_mentions(text, product_for("SAP")) == ["Our plants run SAP S/4HANA."]


async def test_busy_free_models_are_waited_out_and_never_stop_the_judge_for_good():
    class Busy:
        def __init__(self, busy_calls):
            self.busy_calls, self.calls = busy_calls, 0

        async def chat(self, messages, **_kw):
            self.calls += 1
            if self.calls <= self.busy_calls:
                raise LLMUnavailable("no free model answered: a: rate limited; b: rate limited")
            return Reply(json.dumps({"relationship": "uses", "quote": 1}), "minimax/minimax-m3.1-flash:free")

        async def aclose(self):
            pass

    judge = Judge(Busy(2), wait=0)
    j = await judge.judge("Avient", product_for("SAP"), ["SAP S/4HANA handles order to cash."], "10-K")
    assert j.relationship == "uses" and judge.unavailable is None  # two busy moments, then an answer

    judge = Judge(Busy(3), wait=0)
    j = await judge.judge("Avient", product_for("SAP"), ["SAP S/4HANA handles order to cash."], "10-K")
    assert j.relationship == "unreviewed" and judge.unavailable is None  # this piece only
    j = await judge.judge("Lancaster", product_for("SAP"), ["SAP S/4HANA handles order to cash."], "10-K")
    assert j.relationship == "uses"  # the next company is judged again


def test_plain_first_person_use_is_settled_by_rules_and_anything_hedged_is_not():
    sap = product_for("SAP")
    assert rule_relationship("Avient", sap, "In 2025 we completed the migration of our plants to SAP S/4HANA.")[0] \
        == "uses"
    assert rule_relationship("Avient", sap, "Our finance teams use SAP S/4HANA daily.")[0] == "uses"
    for hedged in ("We may implement SAP S/4HANA in 2027.", "Our customers run SAP S/4HANA.",
                   "We plan to migrate to SAP S/4HANA.", "SAP S/4HANA is used by many companies."):
        assert rule_relationship("Avient", sap, hedged) is None, hedged


def test_long_sentences_and_tables_are_cut_at_whole_words_around_the_mention():
    sap = product_for("SAP")
    table = "Gross margin 21.0 % 10.9 % 14.3 % ________ 1 Costs attributable to a multi-year SAP S/4HANA rollout."
    assert find_mentions(table, sap) == ["1 Costs attributable to a multi-year SAP S/4HANA rollout."]
    long = "Intro words. " + "padding " * 60 + "we moved to SAP S/4HANA and " + "more " * 60 + "end. Next."
    (quote,) = find_mentions(long, sap)
    assert "SAP S/4HANA" in quote and len(quote) <= 420 and verify_quote(quote, long)
    assert quote.startswith("padding ") and quote.endswith("more")  # whole words at both ends
    bullets = "• FY24 cash flow fell. • Our plants now run SAP S/4HANA."
    assert find_mentions(bullets, sap) == ["Our plants now run SAP S/4HANA."]


def test_a_sentence_repeated_in_the_document_is_quoted_once():
    text = "Costs of our SAP S/4HANA rollout. Revenue grew. Costs of our SAP S/4HANA rollout."
    assert find_mentions(text, product_for("SAP")) == ["Costs of our SAP S/4HANA rollout."]


async def test_a_person_s_biography_is_not_proof_the_company_uses_it():
    router = Router({"relationship": "uses", "quote": 1})
    bio = "In operations, he later oversaw the business and IT transformation to SAP S/4HANA."
    j = await Judge(router).judge("Belden", product_for("SAP"), [bio], "DEF 14A")
    assert (j.relationship, j.judged_by) == ("other_mention", "rules") and router.calls == 0
    own = "Our plants run SAP S/4HANA."
    j = await Judge(router).judge("Belden", product_for("SAP"), [bio, own], "10-K")
    assert j.relationship == "uses" and j.quote == own  # the biography is set aside, the company's own words judged


def test_a_site_is_not_done_on_values_the_record_would_reject():
    from app.crawl.runner import CrawlRunner
    from app.spec.models import FieldSpec

    runner = CrawlRunner.__new__(CrawlRunner)
    runner.fields_by_name = {"phone": FieldSpec(name="phone", type="phone", semantic="phone"),
                             "contact_email": FieldSpec(name="contact_email", type="email", semantic="contact_email")}
    assert runner._usable("phone", "+1 314 342 4351") and runner._usable("contact_email", "info@advansix.com")
    assert not runner._usable("phone", "12") and not runner._usable("contact_email", "not an email")


async def test_an_answer_in_a_broken_shape_is_not_asked_again():
    router = Router("not json", {"relationship": "evaluating", "quote": 1, "reason": "plans it"})
    j = await Judge(router).judge("Marzetti", product_for("SAP S/4HANA"), ["S/4HANA is planned for 2027."], "10-K")
    assert j.relationship == "unreviewed" and "could not be read" in j.judged_by and router.calls == 1
