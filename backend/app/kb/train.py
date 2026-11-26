"""Train the homepage classifier on teacher labels (kb.teach_label) and say how good it is.

Four heads, each a softmax regression on the page's sentence vector (numpy, no extra library):

- real_page: yes / no, on every labelled page;
- tech_company: yes / no, on real pages;
- micro_sector: on tech companies, for micro-sectors with at least MIN_EXAMPLES examples (the
  rest cannot be learned yet and are reported as such, not guessed);
- offering: product / service / both / none, on real pages.

Besides the page vector, a head can read the page's words: TF-IDF over unigrams and bigrams of
the first WORDS_CHARS characters (vocabulary learned from the labelled pages, numpy only). The
sentence model smears exact terms (SAP, SIEM, biomarker, PCB, LMS) that tell micro-sectors apart.
Each head is cross-validated with and without the words and keeps whichever agrees with the
teacher more often, so a feature that does not help a head is never forced on it.

Before saving, each head is cross-validated (k folds): the report gives accuracy and, per class,
how often a predicted label agrees with the teacher. That agreement is with the teacher, not
with the truth; the hand check of a sample after labelling is what says whether both are right.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

MIN_EXAMPLES = 8
FOLDS = 5
TARGET_PRECISION = 0.8  # a label is kept only above the confidence where cross-validation reached this
MIN_INDUSTRY_ROWS = 3  # a PDL industry becomes a feature once this many labelled pages have it
INDUSTRY_WEIGHT = 0.5  # scale of the industry one-hot next to the unit-length page vector
WORDS_WEIGHT = 0.8  # scale of the unit-length TF-IDF vector next to the page vector
MAX_TERMS = 4000  # vocabulary size: the terms found on the most labelled pages
MIN_TERM_PAGES = 3  # a term is learned only from at least this many labelled pages
TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+#&.-]*[a-z0-9+#]|[a-z0-9]")


def fit(x: np.ndarray, y: np.ndarray, n_classes: int, l2: float = 1e-4, epochs: int = 1200,
        lr: float = 0.01) -> tuple[np.ndarray, np.ndarray]:
    """Multinomial logistic regression, full batch, Adam. Rare classes are weighted up by the square
    root of their rarity: fully equal weights made the large classes (IT services) lose recall and
    the small ones guess too often. Plain gradient descent (400 steps, l2 1e-3) had not converged
    on 34 micro-sectors: 12 of them were never predicted. Adam with a lighter l2 fixed that in
    cross-validation (micro-sector 60.5% -> 67.8%, kept at 80% agreement 36% -> 70% of pages)."""
    n, d = x.shape
    w = np.zeros((d, n_classes))
    b = np.zeros(n_classes)
    onehot = np.eye(n_classes)[y]
    counts = np.bincount(y, minlength=n_classes).astype(float)
    weights = np.sqrt(n / (n_classes * np.maximum(counts, 1.0)))[y][:, None]
    beta1, beta2, eps = 0.9, 0.999, 1e-8
    mw, vw, mb, vb = np.zeros_like(w), np.zeros_like(w), np.zeros_like(b), np.zeros_like(b)
    for t in range(1, epochs + 1):
        p = softmax(x @ w + b)
        g = (p - onehot) * weights / n
        gw, gb = x.T @ g + l2 * w, g.sum(axis=0)
        mw, mb = beta1 * mw + (1 - beta1) * gw, beta1 * mb + (1 - beta1) * gb
        vw, vb = beta2 * vw + (1 - beta2) * gw * gw, beta2 * vb + (1 - beta2) * gb * gb
        c1, c2 = 1 - beta1 ** t, 1 - beta2 ** t
        w -= lr * (mw / c1) / (np.sqrt(vw / c2) + eps)
        b -= lr * (mb / c1) / (np.sqrt(vb / c2) + eps)
    return w, b


def terms(text: str) -> list[str]:
    """Lower-case words and the pairs of neighbouring words."""
    words = TOKEN_RE.findall((text or "").lower())
    return words + [f"{a} {b}" for a, b in zip(words, words[1:], strict=False)]


def vocabulary(texts) -> tuple[list[str], np.ndarray]:
    """The MAX_TERMS terms found on the most pages (at least MIN_TERM_PAGES, and not on more than
    half of them), with their inverse document frequency."""
    df: Counter = Counter()
    for text in texts:
        df.update(set(terms(text)))
    n = max(1, len(texts))
    kept = [t for t, k in df.items() if MIN_TERM_PAGES <= k <= n / 2]
    kept = sorted(kept, key=lambda t: (-df[t], t))[:MAX_TERMS]
    kept.sort()
    return kept, np.array([math.log((1 + n) / (1 + df[t])) + 1 for t in kept])


def word_features(texts, vocab: list[str], idf: np.ndarray) -> np.ndarray:
    index = {t: k for k, t in enumerate(vocab)}
    out = np.zeros((len(texts), len(vocab)))
    for row, text in enumerate(texts):
        for t, k in Counter(terms(text)).items():
            if t in index:
                out[row, index[t]] = 1 + math.log(k)
    out *= idf
    return WORDS_WEIGHT * out / np.maximum(np.linalg.norm(out, axis=1, keepdims=True), 1e-12)


def softmax(z: np.ndarray) -> np.ndarray:
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def normalise(vectors) -> np.ndarray:
    x = np.asarray(vectors, dtype=np.float64)
    return x / np.maximum(np.linalg.norm(x, axis=1, keepdims=True), 1e-12)


@dataclass
class HeadReport:
    name: str
    examples: int
    accuracy: float
    per_class: dict = field(default_factory=dict)  # class -> {examples, precision, recall}
    dropped: dict = field(default_factory=dict)  # classes with too few examples to learn
    threshold: float = 0.0  # confidence from which predictions reached TARGET_PRECISION
    covered: float = 0.0  # share of pages at or above that confidence
    words: bool = False  # the head reads the word features
    other: dict = field(default_factory=dict)  # cross-validation of the variant not kept

    def lines(self) -> list[str]:
        out = [f"{self.name}: {self.examples:,} examples, cross-validated agreement with the teacher "
               f"{100 * self.accuracy:.1f}%" + (" (page vector + words)" if self.words else " (page vector)")]
        if self.other:
            out.append(f"  {'without' if self.words else 'with'} words: {100 * self.other['accuracy']:.1f}%, "
                       f"kept at about {100 * TARGET_PRECISION:.0f}% agreement: {100 * self.other['covered']:.1f}% "
                       "of pages (not kept)")
        for c, s in sorted(self.per_class.items(), key=lambda x: -x[1]["examples"]):
            out.append(f"  {c:<28} {s['examples']:>5}  precision {100 * s['precision']:5.1f}%  "
                       f"recall {100 * s['recall']:5.1f}%")
        if self.per_class:
            out.append(f"  kept when confidence >= {self.threshold:.2f}: {100 * self.covered:.1f}% of pages, "
                       f"about {100 * TARGET_PRECISION:.0f}% agreement; the rest are left unsure")
        if self.dropped:
            out.append("  too few examples to learn yet: "
                       + ", ".join(f"{c} ({n})" for c, n in sorted(self.dropped.items(), key=lambda x: -x[1])))
        return out


def cross_validate(x: np.ndarray, y: np.ndarray, classes: list[str], folds: int = FOLDS,
                   seed: int = 7) -> tuple[float, dict, float, float]:
    rng = np.random.default_rng(seed)
    order = rng.permutation(len(y))
    predicted = np.empty_like(y)
    confidence = np.zeros(len(y))
    for k in range(folds):
        test = order[k::folds]
        train = np.setdiff1d(order, test)
        w, b = fit(x[train], y[train], len(classes))
        p = softmax(x[test] @ w + b)
        predicted[test] = np.argmax(p, axis=1)
        confidence[test] = p.max(axis=1)
    threshold, covered = confidence_threshold(confidence, predicted == y)
    per_class = {}
    for i, c in enumerate(classes):
        tp = int(((predicted == i) & (y == i)).sum())
        per_class[c] = {"examples": int((y == i).sum()),
                        "precision": tp / max(1, int((predicted == i).sum())),
                        "recall": tp / max(1, int((y == i).sum()))}
    return float((predicted == y).mean()), per_class, threshold, covered


def confidence_threshold(confidence: np.ndarray, correct: np.ndarray,
                         target: float = TARGET_PRECISION) -> tuple[float, float]:
    """The lowest confidence from which the predictions at or above it agree with the teacher at
    least `target` of the time, and the share of pages that keeps. 1.01 (keep nothing) if no
    confidence reaches it."""
    order = np.argsort(-confidence, kind="stable")
    ranked = confidence[order]
    hits = np.cumsum(correct[order]) / np.arange(1, len(order) + 1)
    cut = np.append(ranked[:-1] > ranked[1:], True)  # a cut never splits pages of equal confidence
    ok = np.nonzero((hits >= target) & cut)[0]
    ok = ok[ok >= min(9, len(order) - 1)]  # not on the strength of a handful of pages
    if len(ok) == 0:
        return 1.01, 0.0
    last = ok[-1]
    if last == len(order) - 1:  # every prediction together already reaches the target: keep all
        return 0.0, 1.0
    return float(ranked[last]), float((last + 1) / len(order))


def industry_features(industries, vocabulary: list[str]) -> np.ndarray:
    index = {v: k for k, v in enumerate(vocabulary)}
    out = np.zeros((len(industries), len(vocabulary)))
    for row, industry in enumerate(industries):
        if industry in index:
            out[row, index[industry]] = INDUSTRY_WEIGHT
    return out


@dataclass
class LabelModel:
    embed_model: str
    heads: dict  # name -> (classes, w, b)
    reports: list[HeadReport] = field(default_factory=list)
    industries: list[str] = field(default_factory=list)  # PDL industries used as features
    vocab: list[str] = field(default_factory=list)  # terms of the word features (none: not used)
    idf: np.ndarray | None = None
    uses_words: dict = field(default_factory=dict)  # head -> whether it reads the word features
    chunks: int = 1  # pieces of the page embedded and averaged (app.kb.classify.page_chunks)

    def features(self, vectors, industries=None) -> np.ndarray:
        x = normalise(vectors)
        if not self.industries:
            return x
        return np.hstack([x, industry_features(industries or [None] * len(x), self.industries)])

    def head_features(self, name: str, base: np.ndarray, words: np.ndarray | None) -> np.ndarray:
        if self.uses_words.get(name) and words is not None:
            return np.hstack([base, words])
        return base

    def threshold(self, head: str) -> float:
        return next((r.threshold for r in self.reports if r.name == head), 0.0)

    def predict(self, vectors, industries=None, texts=None) -> dict[str, list[dict[str, float]]]:
        """texts: the pages' word texts (app.kb.classify.word_text), for heads that read words."""
        base = self.features(vectors, industries)
        words = None
        if self.vocab and any(self.uses_words.values()):
            words = word_features(texts if texts is not None else [""] * len(base), self.vocab, self.idf)
        out = {}
        for name, (classes, w, b) in self.heads.items():
            x = self.head_features(name, base, words)
            p = softmax(x @ w + b) if classes else np.zeros((len(x), 0))
            out[name] = [dict(zip(classes, map(float, row), strict=True)) for row in p]
        return out

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        arrays = {}
        meta = {"embed_model": self.embed_model, "heads": {}, "industries": self.industries,
                "reports": [r.__dict__ for r in self.reports], "vocab": self.vocab,
                "uses_words": self.uses_words, "chunks": self.chunks}
        if self.idf is not None:
            arrays["idf"] = self.idf
        for name, (classes, w, b) in self.heads.items():
            arrays[f"{name}_w"], arrays[f"{name}_b"] = w, b
            meta["heads"][name] = classes
        np.savez(path, meta=np.array(json.dumps(meta)), **arrays)

    @classmethod
    def load(cls, path: Path) -> LabelModel:
        data = np.load(path, allow_pickle=False)
        meta = json.loads(str(data["meta"]))
        heads = {n: (classes, data[f"{n}_w"], data[f"{n}_b"]) for n, classes in meta["heads"].items()}
        return cls(meta["embed_model"], heads, [HeadReport(**r) for r in meta["reports"]],
                   meta.get("industries", []), meta.get("vocab", []),
                   data["idf"] if "idf" in data.files else None, meta.get("uses_words", {}), meta.get("chunks", 1))


def train(examples: list[tuple[list[float], dict]], embed_model: str, texts=None, chunks: int = 1) -> LabelModel:
    """examples: (sentence vector, teacher label as a dict with real_page, tech_company,
    micro_sector, offering, and optionally the company's PDL industry, used as a feature).
    texts: each page's word text (app.kb.classify.word_text); without them no head reads words."""
    labels = [t for _, t in examples]
    counts_ind: dict[str, int] = {}
    for t in labels:
        if t.get("industry"):
            counts_ind[t["industry"]] = counts_ind.get(t["industry"], 0) + 1
    vocabulary_ind = sorted(k for k, n in counts_ind.items() if n >= MIN_INDUSTRY_ROWS)
    vocab, idf = vocabulary(texts) if texts is not None else ([], None)
    shell = LabelModel(embed_model, {}, [], vocabulary_ind, vocab, idf, {}, chunks)
    x_all = shell.features([v for v, _ in examples], [t.get("industry") for t in labels])
    words_all = word_features(texts, vocab, idf) if vocab else None
    targets = {
        "real_page": [(i, "yes" if t["real_page"] else "no") for i, t in enumerate(labels)],
        "tech_company": [(i, "yes" if t["tech_company"] else "no") for i, t in enumerate(labels) if t["real_page"]],
        "micro_sector": [(i, t["micro_sector"]) for i, t in enumerate(labels)
                         if t["tech_company"] and t["micro_sector"]],
        "offering": [(i, t["offering"]) for i, t in enumerate(labels) if t["real_page"]],
    }
    heads, reports, uses_words = {}, [], {}
    for name, pairs in targets.items():
        counts: dict[str, int] = {}
        for _, c in pairs:
            counts[c] = counts.get(c, 0) + 1
        dropped = {c: n for c, n in counts.items() if n < MIN_EXAMPLES}
        pairs = [(i, c) for i, c in pairs if c not in dropped]
        classes = sorted({c for _, c in pairs})
        if len(classes) < 2:
            heads[name] = (classes, np.zeros((x_all.shape[1], len(classes))), np.zeros(len(classes)))
            reports.append(HeadReport(name, len(pairs), 1.0 if classes else 0.0, {}, dropped, 0.0, 1.0))
            continue
        index = {c: k for k, c in enumerate(classes)}
        rows = [i for i, _ in pairs]
        y = np.array([index[c] for _, c in pairs])
        variants = {False: x_all[rows]}
        if words_all is not None:
            variants[True] = np.hstack([x_all[rows], words_all[rows]])
        scored = {k: cross_validate(x, y, classes) for k, x in variants.items()}
        best = max(scored, key=lambda k: (scored[k][0], scored[k][3]))
        accuracy, per_class, threshold, covered = scored[best]
        other = {"accuracy": scored[not best][0], "covered": scored[not best][3]} if len(scored) > 1 else {}
        w, b = fit(variants[best], y, len(classes))
        heads[name], uses_words[name] = (classes, w, b), best
        reports.append(HeadReport(name, len(pairs), accuracy, per_class, dropped, threshold, covered, best, other))
    if not any(uses_words.values()):
        vocab, idf = [], None
    return LabelModel(embed_model, heads, reports, vocabulary_ind, vocab, idf, uses_words, chunks)
