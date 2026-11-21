"""Train the homepage classifier on teacher labels (kb.teach_label) and say how good it is.

Four heads, each a softmax regression on the page's sentence vector (numpy, no extra library):

- real_page: yes / no, on every labelled page;
- tech_company: yes / no, on real pages;
- micro_sector: on tech companies, for micro-sectors with at least MIN_EXAMPLES examples (the
  rest cannot be learned yet and are reported as such, not guessed);
- offering: product / service / both / none, on real pages.

Before saving, each head is cross-validated (k folds): the report gives accuracy and, per class,
how often a predicted label agrees with the teacher. That agreement is with the teacher, not
with the truth; the hand check of a sample after labelling is what says whether both are right.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

MIN_EXAMPLES = 8
FOLDS = 5


def fit(x: np.ndarray, y: np.ndarray, n_classes: int, l2: float = 1e-3, epochs: int = 400,
        lr: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    """Multinomial logistic regression by full-batch gradient descent, classes weighted equally."""
    n, d = x.shape
    w = np.zeros((d, n_classes))
    b = np.zeros(n_classes)
    onehot = np.eye(n_classes)[y]
    counts = np.bincount(y, minlength=n_classes).astype(float)
    weights = (n / (n_classes * np.maximum(counts, 1.0)))[y][:, None]  # rare classes count as much
    for _ in range(epochs):
        p = softmax(x @ w + b)
        g = (p - onehot) * weights / n
        w -= lr * (x.T @ g + l2 * w)
        b -= lr * g.sum(axis=0)
    return w, b


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

    def lines(self) -> list[str]:
        out = [f"{self.name}: {self.examples:,} examples, cross-validated agreement with the teacher "
               f"{100 * self.accuracy:.1f}%"]
        for c, s in sorted(self.per_class.items(), key=lambda x: -x[1]["examples"]):
            out.append(f"  {c:<28} {s['examples']:>5}  precision {100 * s['precision']:5.1f}%  "
                       f"recall {100 * s['recall']:5.1f}%")
        if self.dropped:
            out.append("  too few examples to learn yet: "
                       + ", ".join(f"{c} ({n})" for c, n in sorted(self.dropped.items(), key=lambda x: -x[1])))
        return out


def cross_validate(x: np.ndarray, y: np.ndarray, classes: list[str], folds: int = FOLDS,
                   seed: int = 7) -> tuple[float, dict]:
    rng = np.random.default_rng(seed)
    order = rng.permutation(len(y))
    predicted = np.empty_like(y)
    for k in range(folds):
        test = order[k::folds]
        train = np.setdiff1d(order, test)
        w, b = fit(x[train], y[train], len(classes))
        predicted[test] = np.argmax(x[test] @ w + b, axis=1)
    per_class = {}
    for i, c in enumerate(classes):
        tp = int(((predicted == i) & (y == i)).sum())
        per_class[c] = {"examples": int((y == i).sum()),
                        "precision": tp / max(1, int((predicted == i).sum())),
                        "recall": tp / max(1, int((y == i).sum()))}
    return float((predicted == y).mean()), per_class


@dataclass
class LabelModel:
    embed_model: str
    heads: dict  # name -> (classes, w, b)
    reports: list[HeadReport] = field(default_factory=list)

    def predict(self, vectors) -> dict[str, list[dict[str, float]]]:
        x = normalise(vectors)
        out = {}
        for name, (classes, w, b) in self.heads.items():
            p = softmax(x @ w + b) if classes else np.zeros((len(x), 0))
            out[name] = [dict(zip(classes, map(float, row), strict=True)) for row in p]
        return out

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        arrays = {}
        meta = {"embed_model": self.embed_model, "heads": {},
                "reports": [r.__dict__ for r in self.reports]}
        for name, (classes, w, b) in self.heads.items():
            arrays[f"{name}_w"], arrays[f"{name}_b"] = w, b
            meta["heads"][name] = classes
        np.savez(path, meta=np.array(json.dumps(meta)), **arrays)

    @classmethod
    def load(cls, path: Path) -> LabelModel:
        data = np.load(path, allow_pickle=False)
        meta = json.loads(str(data["meta"]))
        heads = {n: (classes, data[f"{n}_w"], data[f"{n}_b"]) for n, classes in meta["heads"].items()}
        return cls(meta["embed_model"], heads, [HeadReport(**r) for r in meta["reports"]])


def train(examples: list[tuple[list[float], dict]], embed_model: str) -> LabelModel:
    """examples: (sentence vector, teacher label as a dict with real_page, tech_company,
    micro_sector, offering)."""
    x_all = normalise([v for v, _ in examples])
    labels = [t for _, t in examples]
    targets = {
        "real_page": [(i, "yes" if t["real_page"] else "no") for i, t in enumerate(labels)],
        "tech_company": [(i, "yes" if t["tech_company"] else "no") for i, t in enumerate(labels) if t["real_page"]],
        "micro_sector": [(i, t["micro_sector"]) for i, t in enumerate(labels)
                         if t["tech_company"] and t["micro_sector"]],
        "offering": [(i, t["offering"]) for i, t in enumerate(labels) if t["real_page"]],
    }
    heads, reports = {}, []
    for name, pairs in targets.items():
        counts: dict[str, int] = {}
        for _, c in pairs:
            counts[c] = counts.get(c, 0) + 1
        dropped = {c: n for c, n in counts.items() if n < MIN_EXAMPLES}
        pairs = [(i, c) for i, c in pairs if c not in dropped]
        classes = sorted({c for _, c in pairs})
        if len(classes) < 2:
            heads[name] = (classes, np.zeros((x_all.shape[1], len(classes))), np.zeros(len(classes)))
            reports.append(HeadReport(name, len(pairs), 1.0 if classes else 0.0, {}, dropped))
            continue
        index = {c: k for k, c in enumerate(classes)}
        x = x_all[[i for i, _ in pairs]]
        y = np.array([index[c] for _, c in pairs])
        accuracy, per_class = cross_validate(x, y, classes)
        w, b = fit(x, y, len(classes))
        heads[name] = (classes, w, b)
        reports.append(HeadReport(name, len(pairs), accuracy, per_class, dropped))
    return LabelModel(embed_model, heads, reports)
