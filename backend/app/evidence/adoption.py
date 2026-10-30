"""A sentence that says, in so many words, that an organisation uses a product: proof that needs no model.

"Lick, a UK headquartered home décor brand, is using Oracle NetSuite", "In 2019 CONMED Corporation implemented PTC
Windchill", "DARING Foods has chosen Oracle NetSuite", "Oracle NetSuite was deployed at Wharton Electronics",
"Connect achieves 146% growth with NetSuite", "NetSuite powers GetBusy", "the company selected Oracle NetSuite"
(on a page whose title names one organisation). The sentence names the organisation (or points to the one the
title names), the product, and a verb of adoption or outcome joining them. That is general English, not a list of
companies or sites: the organisation is the proper name the verb's subject (or, in the passive, its agent) is
written as, the product is matched by its names in any letter case, and the verb is one of the ways a use is
reported.

Anything hedged, negated or about leaving the product ("plans to", "is not using", "migrated from") is not
accepted here; it goes to the model, which reads the page as before. So does a page that only lists names.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from app.evidence.products import Product

# How a use is reported, active voice: the verb comes right before the product, with a few words such as
# "its new cloud-based" allowed in between. Matched in any case, so a headline's "Selects" counts.
ACTIVE_VERBS = (r"uses|using|use|implemented|implements|implementing|deployed|deploys|deploying|"
                r"selected|selects|selecting|chose|chosen|chooses|choosing|adopted|adopts|adopting|"
                r"leveraged|leverages|leveraging|"
                r"rolled\s+out|rolls\s+out|rolling\s+out|standardi[sz]ed\s+on|standardi[sz]es\s+on|"
                r"relies\s+on|rely\s+on|relying\s+on|runs\s+on|running\s+on|runs|"
                r"(?:went|goes|gone|is|are)\s+live\s+(?:on|with)|"
                r"(?:migrated|migrates|migrating|moved|moves|moving|switched|switches|switching|upgraded|upgrades|"
                r"upgrading|transitioned|transitions|turned|turns|turning)\s+(?:over\s+)?to")
# What an organisation did with the product, reported as an outcome: "Connect achieves 146% growth in two years
# with NetSuite ERP", "Heart of Midlothian FC transforms financial operations with NetSuite".
OUTCOME_VERBS = (r"achieves|achieved|achieving|transforms|transformed|transforming|fuels|fuelled|fueled|"
                 r"scales|scaled|scaling|streamlines|streamlined|streamlining|grows|grew|growing|"
                 r"moderni[sz]es|moderni[sz]ed|moderni[sz]ing|boosts|boosted|unifies|unified|automates|automated|"
                 r"accelerates|accelerated|simplifies|simplified|centrali[sz]es|centrali[sz]ed")
# The product as the subject, the organisation as the object: "NetSuite powers GetBusy", "NetSuite helps Paysend".
PRODUCT_VERBS = r"powers|powered|helps|helped|enables|enabled|supports|supported|underpins|underpinned"
# The noun forms of adopting: "Acme's implementation of NetSuite", "its selection, implementation and use of".
NOUNS = r"implementation|selection|adoption|deployment|roll-?out|use"
# Words that may stand between the subject and the verb: "Lick is using", "DARING Foods has recently chosen",
# "M&C Saatchi has been using".
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
                   r"support\w*|integrat\w*|alongside|instead|other|another|vendors?|providers?|consultan\w*|"
                   r"integrators?|agency|agencies)\b", re.I)
# Done for someone else, who is the user: "implemented NetSuite for Heart of Midlothian", "for its clients" (not
# "for ERP implementation": that names no one).
FOR_WHOM = re.compile(r"\s*(?:for|at|across|to|within)\s+(?:the\s+|its\s+|their\s+|our\s+)?(?P<who>\S+(?:\s+\S+){0,5})")
CLIENT_WORDS = re.compile(r"(?:clients?|customers?|businesses|organi[sz]ations|brands|retailers)\b", re.I)
# The proper name a subject is written as: capitalised words (or all-caps, initials, words with digits), joined
# by the few small words names contain.
NAME_WORD = r"(?:[A-Z][\w'’&.-]*|[0-9][\w&.-]*[A-Za-z][\w&.-]*)"
NAME = rf"{NAME_WORD}(?:\s+(?:(?:&|and|of|de|du|der|la|le|the|for)\s+)?{NAME_WORD}){{0,7}}"
APPOSITIVE = r"(?:\s*,\s*[^,;.]{2,120}?,)?"
# A pointer to the organisation the page is about: "the company", "the club", "it".
POINTER = r"(?:[Tt]he\s+(?P<noun>[a-z][a-z-]+)|[Ii]t)"
# Words that open a sentence or a clause before the name ("In 2019 CONMED", "Today Lick", "The ..."):
# determiners, pronouns, prepositions, conjunctions, time words and the verbs of a page's links. Stripped.
LEADING = {
    "a", "an", "the", "this", "that", "these", "those", "it", "its", "they", "their", "them", "we", "our", "us",
    "you", "your", "he", "she", "his", "her", "i", "my", "in", "on", "at", "by", "for", "with", "since", "after",
    "before", "when", "while", "today", "now", "then", "here", "there", "how", "why", "what", "who", "which",
    "where", "learn", "read", "see", "discover", "find", "watch", "download", "get", "about", "and", "or", "but",
    "so", "also", "as", "like", "such", "if", "although", "because", "once", "until", "over", "under", "from",
    "to", "of", "last", "next", "year", "january", "february", "march", "april", "june", "july",
    "august", "september", "october", "november", "december", "choosing", "explore", "browse", "build",
    "meet", "join", "contact", "request", "book", "try", "start", "view", "more", "however", "meanwhile",
    "additionally", "moreover", "furthermore", "finally", "recently", "similarly", "instead", "therefore", "still",
    "yet", "indeed", "notably", "previously", "currently",
}
# The generic nouns and adjectives of a sentence about many organisations ("Companies using...", "Many leading
# retailers...") and the words of a page's own furniture ("Case Study", "Implementation Partner", "Review"): a name
# made of nothing else is no name. Inside a real name they stay ("Western Global", "Eureka Solutions").
GENERIC = {
    "many", "most", "some", "all", "any", "every", "each", "other", "others", "several", "both", "one", "two",
    "three", "first", "new", "leading", "global", "companies", "company", "businesses", "business", "customers",
    "customer", "organisations", "organizations", "organisation", "organization", "brands", "brand",
    "retailers", "manufacturers", "firms", "firm", "users", "user", "clients", "client", "teams", "team",
    "enterprises", "enterprise", "people", "staff", "employees", "case", "studies", "study", "story", "stories",
    "success", "press", "release", "releases", "news", "newsroom", "update", "updates", "group", "groups",
    "implementation", "partner", "partners", "partnership", "consulting", "consultancy", "consultants",
    "services", "service", "solution", "solutions", "support", "review", "reviews", "guide", "overview",
    "pricing", "price", "modules", "module", "blog", "insights", "portal", "webinar", "report", "article",
    "edition", "integration", "health", "check", "cloud", "erp", "crm", "software", "platform", "suite",
    "financials", "provider", "experts", "expert", "certified", "award", "winning", "starter", "managed",
    "proven", "latest", "application", "applications", "developers", "developer", "vision", "home", "page",
    "products", "product", "features", "feature", "capabilities", "benefits", "faq", "faqs", "resources",
    "work", "projects", "testimonials", "industries", "industry", "europe", "world", "worldwide",
}


# Words that end a page's furniture, not a name: "Millwall Case Study", "Tomatin Review".
FURNITURE = {"case", "study", "studies", "story", "stories", "review", "reviews", "guide", "overview", "blog",
             "webinar", "report", "article", "news", "press", "release", "update", "updates", "success"}
# A description written where a name would be ("A Global CRM Leader", "Leading Senior Living Organisation"),
# which anonymised case studies use: a scale word and a kind of organisation, not a name anyone is registered as.
SCALE = {"global", "leading", "largest", "fast-growth", "fast-growing", "growing", "major", "top", "international",
         "national", "regional", "multinational", "independent", "specialist", "premier", "large", "mid-sized",
         "midsize", "mid-market"}
KINDS = {"company", "maker", "manufacturer", "provider", "distributor", "dealer", "retailer", "organisation",
         "organization", "consultancy", "leader", "platform", "firm", "business", "brand", "wholesaler", "group",
         "supplier", "producer", "operator", "agency", "chain", "network", "institution"}
# Plural nouns that end a phrase about many ("Microsoft Customers", "Hospitality Leaders"), never one name.
PLURAL_KINDS = {"customers", "users", "clients", "companies", "organisations", "organizations", "businesses",
                "brands", "retailers", "manufacturers", "partners", "leaders", "managers", "teams", "firms",
                "enterprises", "professionals", "owners", "buyers", "sellers", "merchants", "industries"}
# Words of a sentence, capitalised by a headline, that a name never has inside it ("Leaders In The UK Are").
NOT_IN_NAMES = {"in", "the", "are", "is", "was", "were", "be", "been", "should", "ask", "can", "will", "why",
                "how", "what", "when", "before", "after", "to", "for", "with", "your", "our", "their", "its"}
CONTRACTION = re.compile(r"[’']\s*(?:t|ve|re|ll|d|m)$", re.I)


@dataclass(frozen=True)
class RuleUse:
    organisation: str
    quote: str
    pattern: str  # active, passive, outcome, product subject, noun, pointer


def product_re(product: Product) -> str:
    """The product's names, in any letter case ("Oracle Netsuite" is "Oracle NetSuite")."""
    names = sorted({n for n in product.names if n}, key=len, reverse=True)
    return r"(?i:" + "|".join(rf"(?<![\w-]){re.escape(n)}(?![\w-])" for n in names) + r")"


def _words(text: str) -> set[str]:
    return {w.lower() for w in re.findall(r"[A-Za-z0-9]+", text)}


def headline(text: str, ignore: set[str] = frozenset()) -> bool:
    """Written in title case ("Early Investment in NetSuite Enables Growth"), where capitals mark words, not names.
    `ignore`: words that are capitalised anyway (the product's names)."""
    words = [w for w in re.findall(r"[A-Za-z][\w'’-]*", text) if len(w) > 3 and w.lower() not in ignore]
    return len(words) >= 4 and sum(w[0].isupper() for w in words) / len(words) >= 0.6


def plain_word(name: str) -> bool:
    """One ordinary capitalised word ("Growth", "Outcomes"), as opposed to "GetBusy", "3EN", "Heart of Midlothian"."""
    return len(name.split()) == 1 and not re.search(r"[A-Z0-9&]", name[1:])


def done_for_someone(rest: str, product: Product) -> bool:
    """The words after the product say it was done for another organisation, who is the user."""
    m = FOR_WHOM.match(rest)
    if not m:
        return False
    who = m.group("who")
    if CLIENT_WORDS.match(who):
        return True
    named = re.match(NAME, who)
    return bool(named and _not_the_product(named.group(), product))


def _is_country(name: str) -> bool:
    """A country, or countries joined ("UK and Ireland"): a place, not an organisation."""
    from app.discovery.relevance import COUNTRY_NAMES

    parts = [p.strip(" .") for p in re.split(r"\s*(?:,|&|\band\b)\s*", name.lower()) if p.strip(" .")]
    return bool(parts) and all(p in COUNTRY_NAMES for p in parts)


def clean_name(raw: str) -> str:
    """The name without the words that open a sentence or a clause ("In 2019 CONMED Corporation" -> "CONMED
    Corporation") or end a page's furniture ("Millwall Case Study" -> "Millwall"), or "" when what is left is no
    name: nothing name-like ("Many Retailers", "The Companies", "UK"), a contraction ("Don't", "We've"), a
    description ("A Global CRM Leader", "Leading Senior Living Organisation"), a phrase about many ("Microsoft
    Customers") or a headline's words ("Hospitality Leaders In The UK Are")."""
    words = raw.strip(" ,;:-").split()
    if words and words[0] in ("A", "An"):
        return ""  # "a Global Food Distributor": a description, not a name
    while words and (words[0].lower().strip(".,") in LEADING or re.fullmatch(r"[0-9]{2,4}[,.]?", words[0])):
        words.pop(0)
    while len(words) > 1 and words[-1].lower().strip(".,") in FURNITURE:
        words.pop()
    if words:
        words[-1] = re.sub(r"[’']s$", "", words[-1])  # "Tomatin’s" -> "Tomatin"
    name = " ".join(words).strip(" ,;:")
    if len(name) < 2 or not re.match(r"[A-Z0-9]", name) or not re.search(r"[A-Za-z]", name):
        return ""
    lower = [w.lower().strip(".,") for w in words]
    if any(CONTRACTION.search(w) for w in words) or _is_country(name):
        return ""
    if all(w in GENERIC | LEADING or not re.search(r"[a-z0-9]", w) for w in lower):
        return ""
    if lower[-1] in PLURAL_KINDS or (len(words) > 1 and lower[0] in SCALE and lower[-1] in KINDS):
        return ""
    if any(w[:1].isupper() and w.lower() in NOT_IN_NAMES for w in words[1:]):
        return ""
    if any(re.search(r"[’']s$", a) and re.search(r"(?i)est$", b) for a, b in zip(words, words[1:], strict=False)):
        return ""  # "Vancouver’s Largest Guided Tour Company": a description of someone, not their name
    return name


def _not_the_product(name: str, product: Product) -> str:
    """The name with the product's own names taken out ("NetSuite Case Study" -> "Case Study"), cleaned."""
    for n in sorted(product.names, key=len, reverse=True):
        name = re.sub(rf"(?i)(?<![\w-]){re.escape(n)}(?![\w-])", " ", name)
    return clean_name(" ".join(name.split()))


def organisations_named(product: Product, texts: list[str], openers: bool = False) -> list[str]:
    """The proper names of organisations the texts write, other than the product's own: candidates, not proof.
    A single capitalised word that only opens a sentence ("Purpose-built ...", "Three things ...") is a sentence's
    first word, not a name, unless it is written that way elsewhere too (or `openers` keeps such words)."""
    out: list[str] = []
    for text in texts:
        flat = " ".join(text.split())
        for m in re.finditer(NAME, flat):
            raw = m.group()
            name = _not_the_product(raw, product)
            if not name:
                continue
            opens = m.start() == 0 or re.search(r"[.!?:|,–—-]\s*$", flat[:m.start()])
            if not openers and plain_word(name) and (opens or headline(flat)) and not any(
                    re.search(rf"\b{re.escape(name)}\b", t) for t in texts if t is not text):
                continue
            if name.casefold() not in {o.casefold() for o in out}:
                out.append(name)
    return out


def _never(_name: str) -> bool:
    return False


def slug_words(url: str) -> set[str]:
    """The words of a page's address after its site ("/case-studies/millwall" -> {"case", "studies", "millwall"})."""
    path = url.split("://", 1)[-1].split("/", 1)[1] if "/" in url.split("://", 1)[-1] else ""
    return {w for w in re.findall(r"[a-z0-9]+", path.split("?", 1)[0].lower()) if len(w) > 1}


def title_organisation(title: str, product: Product, other: Callable[[str], bool] = _never, url: str = "") -> str:
    """The one organisation a page is about: the one its title names ("NetSuite Case Study - Tomatin Distillery -
    NetSuite Review" -> "Tomatin Distillery"), or, when the title names several, the one its address names too
    ("NetSuite for Football Clubs - Millwall NetSuite Case Study" at /case-studies/millwall -> "Millwall"); ""
    otherwise. Names `other` says yes to do not count (the product's maker, the site's owner)."""
    slug = slug_words(url)
    # The address names the subject: that settles it, even for a one-word name a title opens a part with.
    named = [n for n in organisations_named(product, [title], openers=True)
             if slug and _words(n) and _words(n) <= slug and not other(n)]
    if len(named) == 1:
        return named[0]
    names = [n for n in organisations_named(product, [title]) if not other(n)]
    return names[0] if len(names) == 1 else ""


def fullest_name(name: str, texts: list[str], product: Product) -> str:
    """The fullest form of a name the page writes: "Wharton" -> "Wharton Electronics" when the page also says
    "Wharton Electronics". Only capitalised words that are not the product's, a verb of use, or a sentence's
    opening word extend it; the longest form found wins."""
    stop = _words(" ".join(product.names))
    verbs = re.compile(rf"(?i:{ACTIVE_VERBS}|{OUTCOME_VERBS}|{PRODUCT_VERBS})")
    best = name
    for text in texts:
        flat = " ".join(text.split())
        if headline(flat, stop):
            continue  # a headline's capitals mark every word, not the name's
        for m in re.finditer(rf"(?<![\w-]){re.escape(name)}((?:\s+(?:(?:of|de|the)\s+)?{NAME_WORD}){{1,4}})",
                             flat):
            words = []
            for w in m.group(1).split():
                bare = w.rstrip(".,;:")
                if bare.lower() in stop or bare.lower() in LEADING - {"&", "and", "of", "de", "the"} \
                        or verbs.fullmatch(bare):
                    break
                words.append(w)
                if w != bare:  # "Wharton Electronics." ends the name with the sentence
                    break
            while words and words[-1].rstrip(".,;:").lower() in {"of", "de", "the"}:
                words.pop()
            longer = f"{name} {' '.join(words)}".rstrip(".,;: ") if words else name
            if len(longer) > len(best):
                best = longer
    return best


def rule_uses(product: Product, sentences: list[str], title: str = "", other: Callable[[str], bool] = _never,
              url: str = "") -> list[RuleUse]:
    """Organisations the sentences (and the page's title, read as one more sentence) say use the product, by the
    patterns above. Each sentence is judged on its own; a hedged, negated or "moved away" sentence yields nothing
    from that match (the model reads pages with no accepted sentence). A pointer ("the company", "it") stands for
    the one organisation the title names, if it names exactly one; names `other` says yes to (the maker, the
    site's owner) never count as that organisation."""
    prod = product_re(product)
    patterns = (
        ("active", re.compile(rf"(?P<org>{NAME}){APPOSITIVE}\s+{AUX}(?P<verb>(?i:{ACTIVE_VERBS}))\s+{BRIDGE}{prod}")),
        ("outcome", re.compile(rf"(?P<org>{NAME}){APPOSITIVE}\s+{AUX}(?P<verb>(?i:{OUTCOME_VERBS}))\s+"
                               rf"[^.;:!?]{{0,80}}?\s(?i:with|on|using|through)\s+(?:(?i:the|its|their|new)\s+)*"
                               rf"{prod}")),
        ("passive", re.compile(rf"{prod}\s+{PASSIVE}(?:the\s+)?(?P<org>{NAME})")),
        ("product subject", re.compile(rf"{prod}\s+(?i:{PRODUCT_VERBS})\s+(?P<org>{NAME})")),
        ("noun", re.compile(rf"(?P<org>{NAME})['’]s\s+(?:[\w-]+\s+){{0,2}}?(?i:{NOUNS})\s+of\s+(?:the\s+)?{prod}")),
        ("pointer", re.compile(rf"(?<![\w-]){POINTER}\s+{AUX}(?P<verb>(?i:{ACTIVE_VERBS}))\s+{BRIDGE}{prod}")),
        ("pointer", re.compile(rf"(?<![\w-])(?i:its|their)\s+(?:[\w-]+\s+){{0,2}}?(?i:{NOUNS})"
                               rf"(?:\s*,?\s*(?:and\s+)?(?i:{NOUNS}))*\s+of\s+(?:the\s+)?{prod}")),
    )
    product_words = _words(" ".join(product.names))
    page_org = title_organisation(title, product, other, url) if title else ""
    out: list[RuleUse] = []
    for sentence in [*sentences, *([title] if title else [])]:
        flat = " ".join(sentence.split())
        if re.search(r"\?\s*$", flat):
            continue  # a question asks, it does not report
        for kind, pattern in patterns:
            for m in pattern.finditer(flat):
                has_org = "org" in pattern.groupindex and m.group("org")
                # What joins the name to the product must not hedge or negate ("X does not use", "X plans to
                # deploy", "X migrated from"), and nothing just before the name may ("If X uses", "partners such
                # as X use"). The rest of the sentence may say anything.
                if kind in ("passive", "product subject"):
                    joint, before = flat[m.start():m.start("org")], ""
                elif has_org:
                    joint, before = flat[m.end("org"):m.end()], flat[:m.start("org")].rsplit(",", 1)[-1][-40:]
                else:
                    joint, before = flat[m.start():m.end()], flat[:m.start()].rsplit(",", 1)[-1][-40:]
                if HEDGE.search(joint) or HEDGE.search(before):
                    continue
                if re.search(r"(?i)\b(?:and|or|including|such\s+as|like|as\s+well\s+as)\s*$", before):
                    continue  # "... Healthcare, and Senior Living transformed ...": the last item of a list
                # "Emerald Technology implemented NetSuite for Heart of Midlothian": the subject did it for
                # someone else, who is the user. Which of the two is a reading task, left to the model.
                if kind not in ("passive", "product subject") and done_for_someone(flat[m.end():], product):
                    continue
                if kind == "pointer":
                    noun = m.groupdict().get("noun")
                    if not page_org or (noun and HEDGE.search(noun)):
                        continue  # no one organisation to point to, or "the partner implemented ..."
                    name = page_org
                else:
                    name = clean_name(m.group("org"))
                clause = flat[max([0, *[i + 1 for i, c in enumerate(flat[:m.start()]) if c in ".:!?|"]]):m.end()]
                if headline(clause, product_words) and (kind == "product subject" or plain_word(name)):
                    continue  # "Early Investment in NetSuite Enables Growth": a capitalised word, not a name
                words = _words(name)
                if not name or (words and words <= product_words):
                    continue  # the product's own name ("Oracle NetSuite users") is not a customer
                if any(r.organisation.casefold() == name.casefold() for r in out):
                    continue
                out.append(RuleUse(name, sentence, kind))
    return out
