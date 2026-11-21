"""Homepage labels: the classifier logic, with a word-count embedder instead of the real model."""

from __future__ import annotations

import re
import zlib

from app.kb import classify


def fake_embed(texts):
    """Bag of words hashed into 256 dimensions: same words, same direction."""
    out = []
    for text in texts:
        v = [0.0] * 256
        for word in re.findall(r"[a-z]+", text.lower()):
            v[zlib.crc32(word.encode()) % 256] += 1.0
        out.append(v)
    return out


def test_page_text_joins_title_description_and_the_opening_of_the_text():
    text = classify.page_text(" Acme ", "We sell widgets", "a  b\n" + "x" * 1000)
    assert text.startswith("Acme. We sell widgets. a b ")
    assert len(text) <= len("Acme. We sell widgets. ") + classify.TEXT_CHARS
    assert classify.page_text(None, None, None) == ""


def test_a_page_that_says_what_a_micro_sector_is_gets_that_label():
    c = classify.Classifier(fake_embed)
    [label] = c.label(["pay.example"], [classify.MICRO_SECTORS["payments"]])
    assert label.micro_sector == "payments"
    assert label.micro_top3[0][0] == "payments"
    assert len(label.micro_top3) == 3


def test_a_page_unlike_every_micro_sector_gets_none():
    c = classify.Classifier(fake_embed)
    [label] = c.label(["bakery.example"], ["fresh sourdough loaves croissants every morning"])
    assert label.micro_sector is None
    assert label.micro_top3  # the runner-ups are kept for tuning


def test_a_page_not_clearly_ahead_of_the_runner_up_gets_none():
    text = classify.MICRO_SECTORS["payments"] + " " + classify.MICRO_SECTORS["fintech"]
    [clear] = classify.Classifier(fake_embed, min_score=0.0, min_margin=0.0).label(["x"], [text])
    margin = clear.micro_top3[0][1] - clear.micro_top3[1][1]
    [label] = classify.Classifier(fake_embed, min_score=0.0, min_margin=margin + 0.01).label(["x"], [text])
    assert clear.micro_sector is not None and label.micro_sector is None


def test_offering_follows_the_closest_example_sentences():
    c = classify.Classifier(fake_embed)
    shop, firm = c.label(["shop.example", "firm.example"],
                         [classify.OFFERINGS["product"][1], classify.OFFERINGS["service"][-1]])
    assert shop.offering == "product" and shop.offering_score > 0
    assert firm.offering == "service" and firm.offering_score < 0


def test_sector_guess_is_the_closest_sector():
    c = classify.Classifier(fake_embed)
    [label] = c.label(["x.example"], [classify.SECTORS["Aerospace and defense"]])
    assert label.sector_guess == "Aerospace and defense"


def test_summary_counts_labels_and_none():
    c = classify.Classifier(fake_embed)
    summary = classify.Summary()
    for label in c.label(["a", "b"], [classify.MICRO_SECTORS["payments"], "fresh sourdough croissants"]):
        summary.add(label)
    report = summary.report()
    assert "Homepages labelled: 2" in report
    assert "payments" in report and "(none)" in report
