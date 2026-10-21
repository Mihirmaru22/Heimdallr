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
    router = Router({"relationship": "rolling_out", "quote": 2, "reason": "it is implementing it"})
    judge = Judge(router)
    quotes = ["SAP S/4HANA is a risk.", "We are implementing SAP S/4HANA across our plants."]
    j = await judge.judge("Avient", product_for("SAP"), quotes, "10-K filed 2025-02-20")
    assert (j.relationship, j.quote, j.judged_by) == ("rolling_out", quotes[1], "model:minimax/minimax-m3.1-flash:free")
    # Text the model writes is never used as the quote.
    router.answers.append({"relationship": "uses", "quote": 9, "reason": "x", "quote_text": "made up"})
    j = await judge.judge("Avient", product_for("SAP"), quotes, "10-K")
    assert j.quote == quotes[1]  # out of range: the last one given


async def test_without_a_model_proof_stays_unreviewed_and_the_model_is_not_asked_again():
    router = Router(error=LLMUnavailable("free requests used up for today"))
    judge = Judge(router)
    for _ in range(2):
        j = await judge.judge("Avient", product_for("SAP"), ["We run SAP S/4HANA."], "10-K")
        assert j.relationship == "unreviewed" and "used up" in j.judged_by
    assert router.calls == 1
    j = await Judge(Router("not json")).judge("Avient", product_for("SAP"), ["We run SAP S/4HANA."], "10-K")
    assert j.relationship == "unreviewed"


def test_score_weighs_the_relationship_and_the_age_of_the_proof():
    assert score("uses", 0.85, "2026-02-01", TODAY) == ("Confirmed", 0.85)
    assert score("uses", 0.85, "2023-02-01", TODAY) == ("Likely", 0.42)  # 3+ years old: halved
    assert score("uses", 0.85, "2019-02-01", TODAY) == ("Mentioned", 0.17)  # history
    assert score("evaluating", 0.85, "2026-02-01", TODAY) == ("Likely", 0.51)
    assert score("unreviewed", 0.85, "2026-02-01", TODAY) == ("Mentioned", 0.4)
    for rel in ("vendor", "competitor", "partner_or_reseller", "moved_away", "integrates_with", "other_mention"):
        assert score(rel, 0.85, "2026-02-01", TODAY) == ("", 0.0)
