"""A sentence that says, in so many words, that an organisation uses a product: proof that needs no model.

"Lick, a UK headquartered home décor brand, is using Oracle NetSuite", "In 2019 CONMED Corporation implemented PTC
Windchill", "DARING Foods has chosen Oracle NetSuite", "Oracle NetSuite was deployed at Wharton Electronics". The
sentence names the organisation, the product, and an adoption verb joining them. That is general English, not a
list of companies or sites: the organisation is the proper name the verb's subject (or, in the passive, its
agent) is written as, the product is matched by its names, and the verb is one of the ways a use is reported.

Anything hedged, negated or about leaving the product ("plans to", "is not using", "migrated from") is not
accepted here; it goes to the model, which reads the page as before. So does a page that only lists names.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.evidence.products import Product

# How a use is reported, active voice: the verb comes right before the product, with a few words such as
# "its new cloud-based" allowed in between.
ACTIVE_VERBS = (r"uses|using|use|implemented|implements|implementing|deployed|deploys|deploying|"
                r"selected|selects|selecting|chose|chosen|chooses|choosing|adopted|adopts|adopting|"
                r"rolled\s+out|rolls\s+out|rolling\s+out|standardi[sz]ed\s+on|standardi[sz]es\s+on|"
                r"relies\s+on|rely\s+on|relying\s+on|runs\s+on|running\s+on|runs|"
                r"(?:went|goes|gone|is|are)\s+live\s+(?:on|with)|"
                r"(?:migrated|migrates|migrating|moved|moves|moving|switched|switches|switching|upgraded|upgrades|"
                r"upgrading|transitioned|transitions|turned|turns|turning)\s+(?:over\s+)?to")
# Words that may stand between the subject and the verb: "Lick is using", "DARING Foods has recently chosen".
AUX = (r"(?:(?:has|have|had|is|are|was|were|been|gone|now|also|recently|successfully|officially|today|already)"
       r"\s+)*")
# Between the verb and the product: articles, possessives and a few adjectives ("its new cloud-based").
BRIDGE = r"(?:[\w'’-]+\s+){0,4}?"
PASSIVE = (r"(?:was|were|has\s+been|have\s+been|is|are|had\s+been)\s+(?:successfully\s+|recently\s+)?"
           r"(?:implemented|deployed|selected|chosen|adopted|rolled\s+out|introduced)\s+(?:at|by|across)\s+")
# What must not join the name to the product: a use that is not (yet, or any more) one, or someone else's.
HEDGE = re.compile(r"\b(?:not|n['’]t|never|no\s+longer|plans?|planned|planning|intends?|considering|considers|"
                   r"consider|evaluat\w*|may|might|could|would|should|will|shall|if|whether|hopes?|aims?|"
                   r"looking|pilot\w*|trial\w*|competitor\w*|rival\w*|from|away|off|stopped|ditched|"
                   r"dropped|abandon\w*|left|leaving|customers?|clients?|partners?|resell\w*|help\w*|"
                   r"support\w*|integrat\w*|alongside|instead|other|another)\b", re.I)
# The proper name a subject is written as: capitalised words (or all-caps, initials, words with digits), joined
# by the few small words names contain.
NAME_WORD = r"(?:[A-Z][\w'’&.-]*|[0-9][\w&.-]*[A-Za-z][\w&.-]*)"
NAME = rf"{NAME_WORD}(?:\s+(?:(?:&|and|of|de|du|der|la|le|the|for)\s+)?{NAME_WORD}){{0,7}}"
APPOSITIVE = r"(?:\s*,\s*[^,;.]{2,120}?,)?"
# Words that open a sentence or a clause before the name ("In 2019 CONMED", "Today Lick", "The ..."):
# determiners, pronouns, prepositions, conjunctions, time words and the verbs of a page's links. Stripped.
LEADING = {
    "a", "an", "the", "this", "that", "these", "those", "it", "its", "they", "their", "them", "we", "our", "us",
    "you", "your", "he", "she", "his", "her", "i", "my", "in", "on", "at", "by", "for", "with", "since", "after",
    "before", "when", "while", "today", "now", "then", "here", "there", "how", "why", "what", "who", "which",
    "where", "learn", "read", "see", "discover", "find", "watch", "download", "get", "about", "and", "or", "but",
    "so", "also", "as", "like", "such", "if", "although", "because", "once", "until", "over", "under", "from",
    "to", "of", "last", "next", "year", "january", "february", "march", "april", "june", "july",
    "august", "september", "october", "november", "december",
}
# The generic nouns and adjectives of a sentence about many organisations ("Companies using...", "Many leading
# retailers..."): a name made of nothing else is no name. Inside a real name they stay ("Western Global").
GENERIC = {
    "many", "most", "some", "all", "any", "every", "each", "other", "others", "several", "both", "one", "two",
    "three", "first", "new", "leading", "global", "companies", "company", "businesses", "business", "customers",
    "customer", "organisations", "organizations", "organisation", "organization", "brands", "brand",
    "retailers", "manufacturers", "firms", "firm", "users", "user", "clients", "client", "teams", "team",
    "enterprises", "enterprise", "people", "staff", "employees", "case", "study", "story", "success", "press",
    "release", "news", "update", "group", "groups",
}


@dataclass(frozen=True)
class RuleUse:
    organisation: str
    quote: str
    pattern: str  # "active" or "passive"


def _product_re(product: Product) -> str:
    names = sorted({n for n in product.names if n}, key=len, reverse=True)
    return r"(?:" + "|".join(rf"(?<![\w-]){re.escape(n)}(?![\w-])" for n in names) + r")"


def clean_name(raw: str) -> str:
    """The name without the words that open a sentence or a clause ("In 2019 CONMED Corporation" -> "CONMED
    Corporation"), or "" when nothing name-like is left ("Many Retailers", "The Companies")."""
    words = raw.strip(" ,;:-").split()
    while words and (words[0].lower().strip(".,") in LEADING or re.fullmatch(r"[0-9]{2,4}[,.]?", words[0])):
        words.pop(0)
    name = " ".join(words).strip(" ,;:")
    if len(name) < 2 or not re.match(r"[A-Z0-9]", name) or not re.search(r"[A-Za-z]", name):
        return ""
    if all(w.lower().strip(".,") in GENERIC | LEADING for w in words):
        return ""
    return name


def rule_uses(product: Product, sentences: list[str]) -> list[RuleUse]:
    """Organisations the sentences say use the product, by the adoption patterns above. Each sentence is judged
    on its own; a hedged, negated or "moved away" sentence yields nothing from that match (the model reads pages
    with no accepted sentence)."""
    prod = _product_re(product)
    active = re.compile(rf"(?P<org>{NAME}){APPOSITIVE}\s+{AUX}(?P<verb>{ACTIVE_VERBS})\s+{BRIDGE}{prod}")
    passive = re.compile(rf"{prod}\s+{PASSIVE}(?:the\s+)?(?P<org>{NAME})")
    product_words = {w.lower() for n in product.names for w in re.findall(r"[A-Za-z0-9]+", n)}
    out: list[RuleUse] = []
    for sentence in sentences:
        flat = " ".join(sentence.split())
        if re.search(r"\?\s*$", flat):
            continue  # a question asks, it does not report
        for kind, pattern in (("active", active), ("passive", passive)):
            for m in pattern.finditer(flat):
                # What joins the name to the product must not hedge or negate ("X does not use", "X plans to
                # deploy", "X migrated from"), and nothing just before the name may ("If X uses", "partners such
                # as X use"). The rest of the sentence may say anything.
                if kind == "active":
                    joint = flat[m.end("org"):m.end()]
                    before = flat[:m.start("org")].rsplit(",", 1)[-1][-40:]
                else:
                    joint, before = flat[m.start():m.start("org")], ""
                if HEDGE.search(joint) or HEDGE.search(before):
                    continue
                # "Emerald Technology implemented NetSuite for Heart of Midlothian": the subject did it for
                # someone else, who is the user. Which of the two is a reading task, left to the model.
                if kind == "active" and re.match(r"\s*(?:for|at|across|to|within)\s+(?:the\s+)?[A-Z]",
                                                 flat[m.end():]):
                    continue
                name = clean_name(m.group("org"))
                words = {w.lower() for w in re.findall(r"[A-Za-z0-9]+", name)}
                if not name or (words and words <= product_words):
                    continue  # the product's own name ("Oracle NetSuite users") is not a customer
                if any(r.organisation.casefold() == name.casefold() for r in out):
                    continue
                out.append(RuleUse(name, sentence, kind))
    return out
