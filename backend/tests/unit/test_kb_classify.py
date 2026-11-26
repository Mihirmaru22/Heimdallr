"""Homepage labels: training on teacher labels and applying the heads, with a word-count embedder."""

from __future__ import annotations

import re
import zlib

import numpy as np

from app.kb import classify, train


def fake_embed(texts):
    """Bag of words hashed into 256 dimensions: same words, same direction."""
    out = []
    for text in texts:
        v = [0.0] * 256
        for word in re.findall(r"[a-z]+", text.lower()):
            v[zlib.crc32(word.encode()) % 256] += 1.0
        out.append(v)
    return out


PAGES = {
    "parked": ("this domain is for sale buy it now parked", dict(real_page=False, tech_company=False,
                                                                 micro_sector=None, offering="none")),
    "payroll": ("payroll software for small business start free trial", dict(real_page=True, tech_company=True,
                                                                             micro_sector="hr tech",
                                                                             offering="product")),
    "security": ("endpoint security platform stops ransomware threats", dict(real_page=True, tech_company=True,
                                                                             micro_sector="cybersecurity",
                                                                             offering="product")),
    "lawyer": ("family law solicitors divorce advice book a consultation", dict(real_page=True, tech_company=False,
                                                                                micro_sector=None,
                                                                                offering="service")),
}


def examples(copies=12):
    out = []
    for i in range(copies):
        for text, label in PAGES.values():
            out.append((fake_embed([f"{text} page{i}"])[0], label))
    return out


def test_page_text_joins_title_description_and_the_opening_of_the_text():
    text = classify.page_text(" Acme ", "We sell widgets", "a  b\n" + "x" * 1000)
    assert text.startswith("Acme. We sell widgets. a b ")
    assert len(text) <= len("Acme. We sell widgets. ") + classify.TEXT_CHARS
    assert classify.page_text(None, None, None) == ""


def test_training_learns_each_head_and_reports_cross_validated_agreement():
    model = train.train(examples(), "fake")
    reports = {r.name: r for r in model.reports}
    assert reports["real_page"].examples == 48 and reports["real_page"].accuracy == 1.0
    assert reports["tech_company"].examples == 36  # real pages only
    assert set(model.heads["micro_sector"][0]) == {"hr tech", "cybersecurity"}  # tech companies only
    assert "precision" in "\n".join(reports["micro_sector"].lines())


def test_classes_with_too_few_examples_are_reported_not_learned():
    data = examples() + [(fake_embed(["robot arms for factories"])[0],
                          dict(real_page=True, tech_company=True, micro_sector="robotics", offering="product"))]
    model = train.train(data, "fake")
    micro = {r.name: r for r in model.reports}["micro_sector"]
    assert micro.dropped == {"robotics": 1}
    assert "robotics" not in model.heads["micro_sector"][0]


def test_classifier_labels_new_pages_and_leaves_junk_unlabelled():
    c = classify.Classifier(fake_embed, train.train(examples(), "fake"))
    parked, payroll, lawyer = c.label(["a", "b", "c"], ["domain for sale parked", "payroll software free trial",
                                                        "divorce solicitors consultation"])
    assert not parked.real_page and parked.tech_company is None and parked.offering is None
    assert payroll.real_page and payroll.tech_company and payroll.micro_sector == "hr tech"
    assert payroll.offering == "product"
    assert lawyer.real_page and lawyer.tech_company is False and lawyer.micro_sector is None
    assert lawyer.offering == "service"


def test_model_survives_save_and_load(tmp_path):
    model = train.train(examples(), "fake")
    path = tmp_path / "m.npz"
    model.save(path)
    again = train.LabelModel.load(path)
    v = fake_embed(["payroll software"])
    assert again.embed_model == "fake"
    assert np.allclose(list(again.predict(v)["micro_sector"][0].values()),
                       list(model.predict(v)["micro_sector"][0].values()))
    assert [r.name for r in again.reports] == [r.name for r in model.reports]


def test_summary_counts_real_tech_and_unsure():
    c = classify.Classifier(fake_embed, train.train(examples(), "fake"))
    summary = classify.Summary()
    for label in c.label(["a", "b"], ["domain for sale parked", "payroll software free trial"]):
        summary.add(label)
    report = summary.report()
    assert "Homepages labelled: 2" in report and "hr tech" in report


def test_confidence_threshold_keeps_only_what_reaches_the_target():
    conf = np.array([0.9] * 10 + [0.5] * 10)
    correct = np.array([True] * 10 + [False] * 10)
    threshold, covered = train.confidence_threshold(conf, correct, target=0.8)
    assert threshold == 0.9 and covered == 0.5
    assert train.confidence_threshold(conf, np.ones(20, bool)) == (0.0, 1.0)
    assert train.confidence_threshold(conf, np.zeros(20, bool))[0] > 1


def test_pdl_industry_is_a_feature_when_seen_often_enough():
    data = [(v, {**t, "industry": "computer software" if t["tech_company"] else "law practice"})
            for v, t in examples()]
    model = train.train(data, "fake")
    assert model.industries == ["computer software", "law practice"]
    assert model.heads["tech_company"][1].shape[0] == 256 + 2
    probs = model.predict(fake_embed(["payroll software"]), ["computer software"])
    assert probs["tech_company"][0]["yes"] > 0.5


def test_words_are_kept_only_for_heads_they_help_and_survive_save_and_load(tmp_path):
    data = examples()
    texts = [f"{text} page{i}" for i in range(12) for text, _ in PAGES.values()]
    model = train.train(data, "fake", texts=texts, chunks=2)
    reports = {r.name: r for r in model.reports}
    assert set(model.uses_words) == {"real_page", "tech_company", "micro_sector", "offering"}
    assert all(r.other for r in reports.values())  # both variants were cross-validated
    assert ("words" in "\n".join(reports["micro_sector"].lines()))
    path = tmp_path / "m.npz"
    model.save(path)
    again = train.LabelModel.load(path)
    assert again.chunks == 2 and again.uses_words == model.uses_words and again.vocab == model.vocab
    c = classify.Classifier(fake_embed, again)
    (payroll,) = c.label(["b"], [("Payroll", "payroll software", "free trial for small business")])
    assert payroll.micro_sector == "hr tech"


def test_terms_and_vocabulary():
    assert train.terms("SAP S/4HANA and C++ apps") == ["sap", "s", "4hana", "and", "c++", "apps",
                                                       "sap s", "s 4hana", "4hana and", "and c++", "c++ apps"]
    vocab, idf = train.vocabulary(["payroll app"] * 3 + ["law firm"] * 3 + ["other"])
    assert "payroll" in vocab and "payroll app" in vocab and len(idf) == len(vocab)


def test_page_chunks_add_the_next_part_of_the_page():
    text = "a" * 600 + "b" * 2000
    first, more = classify.page_chunks("T", None, text)
    assert first.startswith("T. aaa") and set(more) == {"b"} and len(more) == classify.MORE_CHARS
    assert classify.page_chunks("T", None, "short") == ["T. short"]
    assert len(classify.page_chunks("T", None, text, chunks=1)) == 1
    vecs = classify.embed_pages(fake_embed, [("T", None, text), "short"], 2)
    assert len(vecs) == 2 and abs(np.linalg.norm(vecs[1]) - 1) < 1e-9
