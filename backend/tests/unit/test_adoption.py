"""Proof by rule: a sentence naming an organisation, the product and an adoption verb needs no model."""

import pytest

from app.evidence.adoption import clean_name, fullest_name, rule_uses
from app.evidence.products import product_for
from app.evidence.thirdparty import names_no_customer, publisher_by_site, rule_reading

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


# The eight ways real pages said it that the first rules missed (NetSuite UK, 2026-10-29), with neutral names.
@pytest.mark.parametrize(("title", "sentence", "organisation"), [
    ("Northfield Employers Technographics",  # the product written in another case
     "In 2024, Northfield Employers implemented Oracle Netsuite SuitePeople Onboarding.", "Northfield Employers"),
    ("Case Study: Kestrel Networks achieves 50% revenue growth with Oracle NetSuite",  # outcome, and "the company"
     "The company moved to NetSuite ERP and Inventory Management.", "Kestrel Networks"),
    ("NetSuite powers Brightwell up", "Oracle NetSuite has revealed how Brightwell has leveraged NetSuite to scale.",
     "Brightwell"),  # the product as subject; "leveraged"
    ("Case studies", "Larkspur Achieves 146% growth in two years with NetSuite ERP", "Larkspur"),  # outcome
    ("Case studies", "Harrow Vale FC Transforms Financial Operations with NetSuite", "Harrow Vale FC"),
    ("NetSuite Case Study - Glenmoor Distillery - NetSuite Review",  # "the company" is the title's one organisation
     "After evaluating various options, the company selected Oracle NetSuite, implemented by a partner.",
     "Glenmoor Distillery"),
    ("Ashbury Cricket selects Fenwick Solutions and Oracle NetSuite for ERP implementation",  # the title itself
     "Managed Services for NetSuite", "Ashbury Cricket"),
    ("MYRA internationalise on NetSuite -",  # "its ... selection, implementation and use of", pointing to the title
     "NetSuite has announced the success that MYRA has had following its selection, implementation and use of "
     "NetSuite.", "MYRA"),
])
def test_the_ways_pages_say_it_that_were_missed_are_accepted(title, sentence, organisation):
    uses = rule_uses(NETSUITE, [sentence], title)
    assert organisation in [u.organisation for u in uses]


def test_headline_capitals_and_vague_pointers_are_not_names():
    # "Enables Growth": a title-case headline's capital, not an organisation.
    assert rule_uses(NETSUITE, ["Foresight Pays Off: Early Investment in NetSuite Enables Growth for Kelpie"]) == []
    # "why they chose NetSuite" points to no one organisation; a title of furniture words names none.
    assert rule_uses(NETSUITE, ["Each case says why they chose NetSuite."],
                     "NetSuite Cloud ERP Case Studies: Challenges, Modules, Outcomes") == []
    assert rule_uses(NETSUITE, ["The partner implemented NetSuite in March."], "Glenmoor Distillery") == []
    # "for ERP implementation" names no one: still the subject's own use.
    assert [u.organisation for u in rule_uses(NETSUITE, ["Ashbury Cricket selects Oracle NetSuite for ERP."])] \
        == ["Ashbury Cricket"]


def test_a_name_is_taken_in_the_fullest_form_the_page_writes():
    text = ("Wexley Electronics is a UK clock maker. Wexley implemented NetSuite ERP with a partner, replacing its old "
            "system.")
    (found,) = rule_reading(NETSUITE, ["Wexley implemented NetSuite ERP with a partner."], text,
                            "https://casestudies.example/wexley")
    assert found.customer == "Wexley Electronics"
    assert fullest_name("Wexley", ["Wexley. It runs NetSuite."], NETSUITE) == "Wexley"  # the sentence ended there
    assert fullest_name("Wexley", ["Wexley Implemented NetSuite"], NETSUITE) == "Wexley"  # a verb is not the name


def test_on_a_partner_s_own_site_its_work_for_clients_is_not_its_own_use():
    sentence = ("To help meet increased customer demand, Brookline Cloud Solutions implemented the cloud-based Oracle "
                "NetSuite ERP solution.")
    # Its own success-stories page: a partner's case study about a client, read by the model instead.
    assert rule_reading(NETSUITE, [sentence], sentence, "https://brooklinecloud.co.uk/success-stories/") == []
    plain = "Brookline Cloud Solutions implemented Oracle NetSuite in 2021."
    # Next to "customer" wording anywhere on its site: the same.
    assert rule_reading(NETSUITE, [sentence], sentence, "https://brooklinecloud.co.uk/news/") == []
    # The company's own news page saying it plainly is first-hand.
    (own,) = rule_reading(NETSUITE, [plain], plain, "https://brooklinecloud.co.uk/news/")
    assert own.customer == "Brookline Cloud Solutions" and own.publisher == "customer"


def test_a_page_naming_no_one_but_the_product_its_maker_and_its_owner_needs_no_model():
    assert names_no_customer(NETSUITE, "Newsroom | NetSuite", ["The NetSuite", "NetSuite"],
                             "https://www.netsuite.co.uk/portal/press/1.shtml")
    assert names_no_customer(NETSUITE, "Threadwell Consulting | NetSuite Implementation Partner",
                             ["We help NetSuite clients improve their systems after go-live."],
                             "https://threadwellconsulting.com/")
    assert not names_no_customer(NETSUITE, "Kestrel Networks on NetSuite", ["Kestrel Networks runs NetSuite."],
                                 "https://news.example/kestrel")


@pytest.mark.parametrize("raw", [
    "Don't", "We've", "I’ve", "You're",  # contractions
    "A Global CRM Leader", "Leading Senior Living Organisation", "Global Food Distributor",  # descriptions
    "Microsoft Customers", "Hospitality Leaders",  # phrases about many
    "Hospitality Leaders In The UK Are", "Questions CFOs Should Ask Before Switching",  # a headline's words
    "Success Stories & Client Projects",  # page furniture
    "However", "UK and Ireland", "Vancouver’s Largest Guided Tour Company",  # an adverb, places, a description
])
def test_what_is_written_where_a_name_would_be_but_is_none(raw):
    assert clean_name(raw) == ""


def test_real_names_keep_their_words_and_lose_only_page_furniture():
    assert clean_name("Millwall Case Study") == "Millwall"
    assert clean_name("Tomatin’s") == "Tomatin"
    for name in ("Western Global", "Rail Delivery Group", "Heart of Midlothian FC", "M&C Saatchi"):
        assert clean_name(name) == name


def test_the_subject_of_a_page_is_the_title_s_name_its_address_also_names():
    from app.evidence.adoption import title_organisation

    title = "NetSuite for Football Clubs - Millwall NetSuite Case Study"
    assert title_organisation(title, NETSUITE, url="https://partner.example/case-studies/millwall") == "Millwall"
    # Without the address, the title's names are "Football Clubs" and an opening word: no one subject is sure.
    assert title_organisation(title, NETSUITE, url="https://partner.example/case-studies/") != "Millwall"


def test_a_case_study_page_is_read_for_its_subject_not_a_sidebar_or_its_menus():
    # The same page with no sentence about its subject goes to the model, not to the sidebar line.
    import asyncio

    from app.evidence.judge import Judge
    from app.evidence.thirdparty import read_page
    from app.llm.openrouter import Reply

    sentences = ["NetSuite Overview", "NetSuite Functionality", "Achieving Real-Time Financial Control with NetSuite",
                 "Harrow Vale FC Transforms Financial Operations with NetSuite &...",
                 "The club chose NetSuite to replace spreadsheets."]

    class Model:
        calls = 0

        async def chat(self, messages, **_kw):
            Model.calls += 1
            return Reply('{"publisher": "partner", "customers": [{"name": "Millwall", "quote": 5, '
                         '"relationship": "uses"}]}', "m:free")

        async def aclose(self):
            pass

    plain = sentences[:4]
    found, _ = asyncio.run(read_page(Judge(Model()), NETSUITE,
                                     "NetSuite for Football Clubs - Millwall NetSuite Case Study", plain,
                                     " ".join(plain) + " Millwall", "https://partner.example/case-studies/millwall"))
    assert Model.calls == 1 and "Millwall" in [f.customer for f in found]
    found, _ = asyncio.run(read_page(Judge(Model()), NETSUITE,
                                     "NetSuite for Football Clubs - Millwall NetSuite Case Study", sentences,
                                     " ".join(sentences) + " Millwall", "https://partner.example/case-studies/millwall"))
    # Not a list (the menus and headings are not organisations said to use it); "the club chose NetSuite" points
    # to the page's subject, Millwall, so the page is Millwall's, not the sidebar's.
    assert "Millwall" in [f.customer for f in found]


def test_the_last_item_of_a_list_and_two_names_joined_by_and_are_not_one_subject():
    assert rule_uses(NETSUITE, ["See how firms across IT, Media, Healthcare, and Senior Living transformed their "
                                "operations with NetSuite."]) == []
    text = ("Charlotte Tilbury and Lovesac both appear here. Charlotte Tilbury implemented NetSuite's advanced "
            "financials.")
    assert fullest_name("Charlotte Tilbury", [text], NETSUITE) == "Charlotte Tilbury"
