"""One decision maker for the whole project: Laya, with the old rules kept only as a fallback.

Rule (Ronak, 2026-10-17): Laya makes the decisions; language models read and write text.

Every judgment call (which domain a question is in, what kind of question it is, which
sub-questions matter, which jurisdiction a question concerns, whether a sentence reports a
dispute, whether a claim answers a question) goes through ``get_decisions()``:

- with Laya installed and not turned off (HEIMDALLR_LAYA=0), Laya's answer is used;
- without Laya, the existing rule answers, so behaviour is unchanged;
- either way, both answers are written to the decision journal (``decisions.jsonl`` in the run
  folder when a run is recorded), so how often Laya and the rules disagree can be measured.

Not routed here, on purpose: safety and accounting checks that must give the same answer every
time (SSRF and robots.txt, budgets, tool permissions, the evidence gate that checks a quote is on
the page, resolution coverage). A wrong guess there would break a guarantee, not just a ranking.

HEIMDALLR_LAYA_MIN_CONFIDENCE (default 0): below this Laya confidence the rule answer is used.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import os
from pathlib import Path
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Decision:
    name: str
    answer: Any
    by: str  # "laya" or "rule"
    confidence: float | None = None
    rule_answer: Any = None
    laya_answer: Any = None


class DecisionService:
    """Laya's typed decisions (choice, yes/no, score) with a rule fallback and a journal."""

    def __init__(self, router: Any = None, enabled: bool | None = None) -> None:
        self._router = router
        self._checked = router is not None
        self.enabled = (os.environ.get("HEIMDALLR_LAYA", "1").strip() != "0") if enabled is None else enabled
        self.min_confidence = float(os.environ.get("HEIMDALLR_LAYA_MIN_CONFIDENCE", "0") or 0)
        self.journal: list[dict[str, Any]] = []
        self._journal_path: Path | None = None
        self._lock = threading.Lock()
        self._cache: dict[str, Any] = {}
        self._failures = 0
        self.engine: Any = None  # System1DecisionEngine sharing the same router

    # --- setup -----------------------------------------------------------------------------

    def router(self) -> Any:
        if not self.enabled:
            return None
        if not self._checked:
            self._checked = True
            try:
                from argus.brain.system1 import System1DecisionEngine

                engine = System1DecisionEngine()
                self._router = engine._ensure_router()
                self.engine = engine if self._router is not None else None
            except Exception as exc:  # pragma: no cover - depends on the machine
                logger.info("Laya unavailable, decisions use the rules: %s", exc)
                self._router = None
        return self._router

    @property
    def available(self) -> bool:
        return self.router() is not None

    def set_journal(self, path: Path | str | None) -> None:
        self._journal_path = Path(path) if path else None

    def summary(self) -> dict[str, Any]:
        by_laya = [d for d in self.journal if d["by"] == "laya"]
        disagree = [d for d in by_laya if d.get("rule") is not None and d["rule"] != d["laya"]]
        return {"decisions": len(self.journal), "by_laya": len(by_laya), "by_rule": len(self.journal) - len(by_laya),
                "laya_disagreed_with_rule": len(disagree)}

    # --- core ------------------------------------------------------------------------------

    def _predict(self, text: str, question: dict[str, Any]) -> dict[str, Any] | None:
        router = self.router()
        if router is None:
            return None
        key = json.dumps([text[:4000], question], sort_keys=True, default=str)
        if key in self._cache:
            return self._cache[key]
        try:
            res = router.predict(text[:4000], {"q": question})
            ans = (res or {}).get("answers", {}).get("q")
        except Exception as exc:
            logger.debug("Laya decision failed: %s", exc)
            ans = None
            self._failures += 1
            if self._failures >= 3:  # model missing or broken: stop asking, use the rules
                logger.warning("Laya failed %d times (%s); decisions use the rules for the rest of the run", self._failures, exc)
                self._router, self.engine = None, None
            return None
        self._failures = 0
        if len(self._cache) < 20000:
            self._cache[key] = ans
        return ans

    def _record(self, name: str, text: str, by: str, answer: Any, rule: Any, laya: Any, conf: float | None, ms: float) -> Decision:
        entry = {"name": name, "by": by, "answer": answer, "rule": rule, "laya": laya,
                 "confidence": None if conf is None else round(conf, 4), "ms": round(ms, 1), "input": text[:300]}
        with self._lock:
            self.journal.append(entry)
            if self._journal_path:
                try:
                    with self._journal_path.open("a", encoding="utf-8") as f:
                        f.write(json.dumps(entry, default=str) + "\n")
                except OSError:
                    pass
        return Decision(name, answer, by, conf, rule, laya)

    def _settle(self, name: str, text: str, laya: Any, conf: float | None, rule: Any, started: float) -> Decision:
        ms = (time.perf_counter() - started) * 1000
        if laya is not None and (conf is None or conf >= self.min_confidence):
            return self._record(name, text, "laya", laya, rule, laya, conf, ms)
        return self._record(name, text, "rule", rule, rule, laya, conf, ms)

    def choose(self, name: str, text: str, instructions: str, options: dict[str, str], rule: str | None) -> Decision:
        """One of ``options`` (label -> description). ``rule`` is the answer without Laya."""
        started = time.perf_counter()
        ans = self._predict(text, {"type": "choice", "instructions": instructions, "criteria": options})
        laya = conf = None
        if ans:
            choice = str(ans.get("choice", ""))
            if choice in options:
                laya = choice
                conf = _float(ans.get("confidence"))
        return self._settle(name, text, laya, conf, rule, started)

    def yes_no(self, name: str, text: str, question: str, rule: bool | None, threshold: float = 0.5) -> Decision:
        """True or False. Laya returns P(yes); ``threshold`` turns it into an answer."""
        started = time.perf_counter()
        ans = self._predict(text, {"type": "noul", "instructions": question})
        laya = conf = None
        if ans and ans.get("noul") is not None:
            p = _float(ans.get("noul"))
            if p is not None:
                laya = p >= threshold
                conf = max(p, 1 - p)
        return self._settle(name, text, laya, conf, rule, started)

    def score(self, name: str, text: str, instructions: str, levels: list[str], rule: int | None) -> Decision:
        """Index into ``levels`` (lowest first)."""
        started = time.perf_counter()
        ans = self._predict(text, {"type": "score", "instructions": instructions, "criteria": levels})
        laya = conf = None
        if ans and ans.get("score") is not None:
            try:
                laya = max(0, min(len(levels) - 1, int(ans["score"])))
                conf = _float(ans.get("confidence"))
            except (TypeError, ValueError):
                laya = None
        return self._settle(name, text, laya, conf, rule, started)


def _float(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


_SERVICE: DecisionService | None = None


def get_decisions() -> DecisionService:
    """The process-wide decision service (one Laya model, one journal)."""
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = DecisionService()
    return _SERVICE


def set_decisions(service: DecisionService | None) -> None:
    """Replace or forget the shared service (tests, or after changing the environment)."""
    global _SERVICE
    _SERVICE = service
