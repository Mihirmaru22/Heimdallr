"""Proof by rule: a sentence naming an organisation, the product and an adoption verb needs no model."""

import pytest

from app.evidence.adoption import clean_name, rule_uses
from app.evidence.products import product_for
from app.evidence.thirdparty import publisher_by_site, rule_reading

# With the other names the plan gives (technology_aliases), as a job has them.
NETSUITE = product_for("Oracle NetSuite", ["NetSuite"])
WINDCHILL = product_for("PTC Windchill", ["Windchill"])


@pytest.mark.parametrize(("sentence", "product", "organisation"), [
    ("Lick, a UK headquartered home décor brand, is using Oracle NetSuite.", NETSUITE, "Lick"),
    ("In 2019 CONMED Corporation implemented PTC Windchill Quality Solutions.", WINDCHILL, "CONMED Corporation"),
    ("DARING Foods has chosen Oracle NetSuite to help manage growing demand.", NETSUITE, "DARING Foods"),
    ("Undercover Snacks turns to Oracle NetSuite to integrate its operations.", NETSUITE, "Undercover Snacks"),
    ("PTC today announced that Komatsu America Corp. has chosen Windchill.", WINDCHILL, "Komatsu America Corp."),
    ("Heart of Midlothian FC went live on NetSuite in March.", NETSUITE, "Heart of Midlothian FC"),
    ("Western Global migrated to Oracle NetSuite in 2021.", NETSUITE, "Western Global"),
    ("Oracle NetSuite was implemented at Wharton Electronics last year.", NETSUITE, "Wharton Electronics"),
    ("GoCardless runs on NetSuite across its finance team.", NETSUITE, "GoCardless"),
])
def test_a_sentence_saying_an_organisation_uses_the_product_is_accepted(sentence, product, organisation):
    (use,) = rule_uses(product, [sentence])
    assert use.organisation == organisation and use.quote == sentence


@pytest.mark.parametrize(("sentence", "product"), [
    ("Acme plans to implement Oracle NetSuite next year.", NETSUITE),  # not yet
    ("Acme is not using Oracle NetSuite.", NETSUITE),  # negated
    ("Acme may deploy PTC Windchill.", WINDCHILL),  # hedged
    ("Acme migrated from Oracle NetSuite to another ERP.", NETSUITE),  # moved away
    ("Companies that use Oracle NetSuite grow faster.", NETSUITE),  # no organisation named
    ("Many retailers use Oracle NetSuite.", NETSUITE),
    ("Emerald Technology implemented NetSuite for Heart of Midlothian.", NETSUITE),  # done for someone else
    ("Oracle NetSuite customers include Lick and BARK.", NETSUITE),  # a list: no adoption verb
    ("Does Acme use Oracle NetSuite?", NETSUITE),  # a question
    ("Acme is evaluating Oracle NetSuite.", NETSUITE),
    ("Acme helps customers implement Oracle NetSuite.", NETSUITE),  # a partner's service
    ("The NetSuite users group met in London.", NETSUITE),
])
def test_hedged_negated_generic_or_third_party_sentences_are_left_to_the_model(sentence, product):
    assert rule_uses(product, [sentence]) == []


def test_the_name_loses_the_words_that_start_a_sentence():
    assert clean_name("In 2019 CONMED Corporation") == "CONMED Corporation"
    assert clean_name("Today Lick") == "Lick"
    assert clean_name("The Companies") == "" and clean_name("Many Leading Retailers") == ""
    assert clean_name("Western Global") == "Western Global"


def test_a_rule_reading_says_who_published_the_page_from_its_address():
    assert publisher_by_site("https://www.netsuite.com/portal/customers/lick.shtml", "Lick", NETSUITE) == "vendor"
    assert publisher_by_site("https://www.ptc.com/en/case-studies/conmed", "CONMED", WINDCHILL) == "vendor"
    assert publisher_by_site("https://www.lick.com/news", "Lick", NETSUITE) == "customer"
    assert publisher_by_site("https://uktechnews.co.uk/lick", "Lick", NETSUITE) == "other"
    assert publisher_by_site("https://uktechnews.co.uk/lick", "Lick", NETSUITE, "news") == "news"
    sentence = "Lick, a UK-based home décor brand, is using Oracle NetSuite."
    (found,) = rule_reading(NETSUITE, [sentence], sentence, "https://www.netsuite.com/customers/lick")
    assert found.customer == "Lick" and found.publisher == "vendor" and found.agreement == "rules"
    assert found.country == "GB" and found.judged_by == "rules: active sentence"
    # The product's maker is never its own customer.
    assert rule_reading(NETSUITE, ["Oracle deployed NetSuite internally."], "Oracle deployed NetSuite internally.",
                        "https://example.com") == []
