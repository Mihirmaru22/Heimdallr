"""Laya against the old rules on labelled decisions from many fields.

Run on a machine where Laya's model can download (first run fetches it):

    python -m argus.evals.laya_decisions            # table of accuracy per decision
    python -m argus.evals.laya_decisions --show     # also every example Laya or the rules got wrong
    python -m argus.evals.laya_decisions --model english --model multilingual --model typed-decisions

The examples are hand-labelled and deliberately spread across fields (medicine, law, sport,
history, software, farming, finance, ...), so the score is not tuned to one kind of question.
A decision where Laya scores below the rules should be reported back before trusting it.
"""

from __future__ import annotations

import argparse
import time

from argus.brain.decisions import DecisionService, set_decisions
from argus.capability_registry.matcher import CapabilityMatcher
from argus.investigation.planner import InvestigationPlanner
from argus.investigation.question_intent import _INTENT_OPTIONS, classify_intent
from argus.investigation.reported_disputes import _SENTENCE_KINDS, classify_sentence_rule
from argus.investigation.resolution import claim_kind_fits_question

QUESTION_FORM = [
    ("Why did the Roman Republic collapse?", "causal"),
    ("What caused the 2008 financial crisis?", "causal"),
    ("How does CRISPR gene editing work?", "mechanism"),
    ("How do tidal power stations generate electricity?", "mechanism"),
    ("Compare PostgreSQL and MySQL on replication and licensing", "comparison"),
    ("Messi vs Ronaldo career goals", "comparison"),
    ("What changed in EU data protection law between 2016 and 2024?", "change"),
    ("Is intermittent fasting safe for people with type 1 diabetes?", "yes_no"),
    ("Does Norway tax unrealised capital gains?", "yes_no"),
    ("Who founded Patagonia?", "role"),
    ("Who is the current head coach of the All Blacks?", "role"),
    ("What is the boiling point of ethanol at sea level?", "attribute"),
    ("Find the headquarters address of Maersk", "attribute"),
    ("Give me an overview of the lithium mining industry in Chile", "summary"),
    ("Summarise the main findings of the IPCC sixth assessment report", "summary"),
    ("Which hospitals in Ohio use Epic for electronic health records?", "listing"),
    ("List vineyards in Oregon that grow Pinot Noir", "listing"),
    ("Tell me which startups in Berlin build battery recycling technology", "listing"),
    ("Name the open-source alternatives to Photoshop", "listing"),
    ("Companies in Japan that use SAP S/4HANA", "listing"),
    ("Thoughts on the future of vertical farming", "open"),
]

DOMAIN = [
    ("Which companies acquired cybersecurity startups in 2023?", "corporate"),
    ("Who are the executive officers of Siemens and their tenure?", "corporate"),
    ("How does Rust's borrow checker prevent data races?", "technical"),
    ("Compare vector databases on query latency benchmarks", "technical"),
    ("What was the sequence of events in the Cuban missile crisis?", "historical"),
    ("Why did the Ottoman Empire decline in the 19th century?", "historical"),
    ("What is the evidence that microplastics harm human health?", "scientific_policy"),
    ("Do minimum wage increases reduce employment?", "scientific_policy"),
    ("What does the Gates Foundation fund in malaria research?", "organization"),
    ("Find accounts linked to the username darkstar_88 across platforms", "identity"),
    ("Best time of year to plant garlic in Scotland", "generic"),
    ("Which football clubs in Spain have women's teams in the top league?", "generic"),
]

JURISDICTION = [
    ("What is the status of the second appeal?", "GLOBAL"),
    ("Which US hospitals use Epic?", "US"),
    ("SEC filings of Tesla in 2024", "US"),
    ("Companies in the United Kingdom that use Sage accounting", "GB"),
    ("Directors registered at Companies House for Arm Holdings", "GB"),
    ("German manufacturers using Teamcenter", "DE"),
    ("Rice farmers in Vietnam using drones", "GLOBAL"),
    ("Tell us about wind farms in Denmark", "GLOBAL"),
]

SENTENCE = [
    ("Later analyses contradict the cometary impact model.", "dispute"),
    ("The two surveys report conflicting estimates of the herd size.", "dispute"),
    ("The cause of the outage remains disputed among engineers.", "dispute"),
    ("Earlier reports naming him as CEO are outdated.", "supersession"),
    ("The 2019 guidance has been superseded by the 2023 standard.", "supersession"),
    ("There is no conflict between the two accounts.", "none"),
    ("The museum's findings do not contradict the earlier excavation.", "none"),
    ("Opposing teams met in the final on Saturday.", "none"),
    ("The company denied any wrongdoing in a statement.", "dispute"),
]


# (user question, template sub-question, must it be answered?)
SUBQUESTION = [
    ("Which hospitals in Ohio use Epic?", "Which Ohio hospitals have announced an Epic go-live?", True),
    ("Which hospitals in Ohio use Epic?", "Who are the key executive officers of Epic Systems?", False),
    ("Why did the Roman Republic collapse?", "What political crises preceded the end of the Republic?", True),
    ("Why did the Roman Republic collapse?", "What is the current population of Rome?", False),
    ("What is the evidence that microplastics harm human health?", "Which studies measured microplastics in human blood or tissue?", True),
    ("What is the evidence that microplastics harm human health?", "Which companies manufacture plastic bottles?", False),
    ("Who founded Patagonia?", "When and by whom was Patagonia founded?", True),
    ("Who founded Patagonia?", "What is Patagonia's annual revenue?", False),
]

# (question, question type, claim "subject predicate object", does the claim answer it?)
CLAIM_FIT = [
    ("Who leads Acme Corp?", "OFFICER_TENURE", "Acme Corp chief_executive_officer Jane Doe", True),
    ("Who leads Acme Corp?", "OFFICER_TENURE", "Acme Corp mentioned_in Jane Doe was named chief executive in 2021", True),
    ("Who leads Acme Corp?", "OFFICER_TENURE", "Acme Corp headquartered_in Denver", False),
    ("What is the contact email of the Riverside clinic?", "CONTACT_CHANNEL", "Riverside clinic email info@riverside.example", True),
    ("What is the contact email of the Riverside clinic?", "CONTACT_CHANNEL", "Riverside clinic founded 1998", False),
    ("Which servers host example.org?", "INFRASTRUCTURE_ATTRIBUTION", "example.org resolves_to 93.184.216.34", True),
    ("Which servers host example.org?", "INFRASTRUCTURE_ATTRIBUTION", "example.org owned_by Example Foundation", False),
    ("Who leads the Red Cross in Kenya?", "OFFICER_TENURE", "Kenya Red Cross secretary_general Ahmed Idris", True),
]


def _subq_rule(pair: str) -> bool:
    objective, sub = pair.split("\n", 1)
    return len(InvestigationPlanner._topic_terms(sub, set()) & InvestigationPlanner._topic_terms(objective, set())) >= 2


def _claim(text: str) -> dict:
    subject, predicate, obj = (text.split(" ", 2) + ["", ""])[:3]
    return {"subject": subject, "predicate": predicate, "object": obj}


def _run(service: DecisionService, show: bool) -> None:
    set_decisions(service)
    rows = []

    def check(name, examples, laya_fn, rule_fn):
        laya_ok = rule_ok = 0
        misses = []
        started = time.perf_counter()
        for text, gold in examples:
            got_laya, got_rule = laya_fn(text), rule_fn(text)
            laya_ok += got_laya == gold
            rule_ok += got_rule == gold
            if got_laya != gold or got_rule != gold:
                misses.append((text, gold, got_laya, got_rule))
        ms = (time.perf_counter() - started) * 1000 / max(1, len(examples))
        rows.append((name, len(examples), laya_ok, rule_ok, ms))
        if show:
            for text, gold, gl, gr in misses:
                print(f"  [{name}] {text!r}: expected {gold}, Laya {gl}, rules {gr}")

    def laya_choice(name, instructions, options):
        def f(text):
            d = service.choose(name, text, instructions, options, rule=None)
            return d.answer if d.by == "laya" else None
        return f

    check("question form", QUESTION_FORM, laya_choice("question_form", "What does this question ask for?", _INTENT_OPTIONS),
          lambda t: classify_intent(t).kind)
    check("domain", DOMAIN, laya_choice("question_domain", "Which kind of research question is this?", InvestigationPlanner._DOMAIN_OPTIONS),
          InvestigationPlanner._detect_domain_rule)
    check("jurisdiction", JURISDICTION, laya_choice("question_jurisdiction", "Which country's records does this question concern?", CapabilityMatcher._JURISDICTIONS),
          CapabilityMatcher.jurisdiction_rule)
    check("sentence conflict", SENTENCE, laya_choice("sentence_conflict", "Does this sentence report a conflict between accounts?", _SENTENCE_KINDS),
          lambda t: classify_sentence_rule(t) or "none")

    def laya_yes_no(name, instructions):
        def f(text):
            d = service.yes_no(name, text, instructions, rule=None)
            return d.answer if d.by == "laya" else None
        return f

    check("critical sub-question", [(f"User question: {o}\nSub-question: {q}", g) for o, q, g in SUBQUESTION],
          laya_yes_no("subquestion_critical", "Must this sub-question be answered to answer the user's question?"),
          lambda t: _subq_rule(t.replace("User question: ", "").replace("Sub-question: ", "")))
    fit_rules = {f"Question: {q}\nClaim: {c}": claim_kind_fits_question(_claim(c), qt) for q, qt, c, _ in CLAIM_FIT}
    check("claim answers question", [(f"Question: {q}\nClaim: {c}", g) for q, _, c, g in CLAIM_FIT],
          laya_yes_no("claim_answers_question", "Does this claim state the kind of fact the question asks for?"),
          lambda t: fit_rules[t])

    print(f"{'decision':<24}{'examples':>9}{'Laya':>8}{'rules':>8}{'ms/ex':>8}")
    for name, n, lo, ro, ms in rows:
        print(f"{name:<24}{n:>9}{lo:>8}{ro:>8}{ms:>8.1f}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--show", action="store_true", help="print every example Laya or the rules got wrong")
    parser.add_argument("--model", action="append", default=[], help="Laya checkpoint (english, multilingual, typed-decisions); repeat to compare")
    args = parser.parse_args()
    import os

    for model in args.model or [os.environ.get("HEIMDALLR_LAYA_MODEL", "")]:
        if model:
            os.environ["HEIMDALLR_LAYA_MODEL"] = model
        service = DecisionService(enabled=True, laya_decides="all")
        if not service.available:
            raise SystemExit("Laya is not available (pip install laya, and let it download its model once).")
        started = time.perf_counter()
        service.yes_no("warmup", "warm up", "Is this a warm-up?", rule=None)  # loads the checkpoint; not timed below
        load_s = time.perf_counter() - started
        router = service.router()
        device = getattr(router, "device", None) or "auto"
        print(f"\nLaya checkpoint: {service.model}; device: {device}; load + first call {load_s:.1f} s")
        _run(service, args.show)


if __name__ == "__main__":
    main()
