"""Heimdallr V3: Contradiction Resolution, Entity Scoping, and Epistemic Sufficiency Engine.

Provides reusable, domain-agnostic production mechanisms for:
1. Cross-document claim reconciliation and numerical/categorical contradiction detection
   without requiring explicit conflict keywords.
2. Entity and relationship scope protection preventing parent-to-child contamination
   and distinguishing NOT_FOUND from INSUFFICIENT_EVIDENCE.
3. Epistemic sufficiency calibration distinguishing confirmed facts from preliminary,
   unverified, fragmentary, or proprietary non-public evidence.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import logging
import re
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from argus.verifier.syndication_intelligence import SyndicationIntelligence
from argus.verifier.temporal_reasoner import TemporalStateReasoner

logger = logging.getLogger(__name__)


class DiscrepancyType(str, Enum):
    NUMERICAL_DISCREPANCY = "NUMERICAL_DISCREPANCY"
    CATEGORICAL_DISPUTE = "CATEGORICAL_DISPUTE"
    TEMPORAL_SUPERSEDED = "TEMPORAL_SUPERSEDED"
    EVIDENTIARY_CONFLICT = "EVIDENTIARY_CONFLICT"
    COMPATIBLE = "COMPATIBLE"


class ComparableClaim(BaseModel):
    """Normalized claim representation for cross-document reconciliation."""

    claim_id: str
    subject: str
    property_dim: str  # e.g., "payload", "efficiency", "battery_capacity", "revenue", "completion_date", etc.
    raw_text: str
    numeric_value: float | None = None
    unit: str | None = None
    categorical_value: str | None = None
    temporal_anchor: str | None = None
    source_url: str | None = None
    source_type: str | None = None
    evidence_id: str | None = None
    is_preliminary_or_rumor: bool = False
    is_authoritative: bool = True


class ContradictionRecord(BaseModel):
    """Auditable record of a factual conflict across independent sources."""

    topic: str
    subject: str
    property_dim: str
    claim_a: str
    claim_b: str
    value_a: Any
    value_b: Any
    discrepancy_type: DiscrepancyType
    source_a: str | None = None
    source_b: str | None = None
    evidence_id_a: str | None = None
    evidence_id_b: str | None = None
    status: str = "UNRESOLVED_CONTRADICTION"
    is_temporal: bool = False
    adjudication_rationale: str = ""
    resolved_value: Any = None
    recorded_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ContradictionResolver:
    """Core engine for detecting and adjudicating factual contradictions across sources."""

    def __init__(self) -> None:
        self.syndication_intel = SyndicationIntelligence()
        self.temporal_reasoner = TemporalStateReasoner()

    # -------------------------------------------------------------------------
    # 1. Attribute & Value Extraction
    # -------------------------------------------------------------------------

    DIMENSION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
        ("troop_strength", re.compile(r"\b(?:troop|troops|soldiers|combatants|army|forces|infantry|cavalry)\b", re.I)),
        ("thrust", re.compile(r"\b(?:thrust|propulsion)\b", re.I)),
        ("payload", re.compile(r"\b(?:payload|capacity|lift|handling|load)\b", re.I)),
        ("energy_density", re.compile(r"\b(?:energy\s+density|wh/kg)\b", re.I)),
        ("battery_capacity", re.compile(r"\b(?:battery(?:\s+pack)?|storage|nominal\s+capacity)\b", re.I)),
        ("efficiency", re.compile(r"\b(?:efficiency|conversion|yield|recovery)\b", re.I)),
        ("efficacy", re.compile(r"\b(?:efficacy|biomarker|reduction|endpoints|phase\s+ii|phase\s+iii|trial)\b", re.I)),
        ("revenue", re.compile(r"\b(?:revenue|sales|earnings|turnover|valuation|purchase\s+price)\b", re.I)),
        ("completion_date", re.compile(r"\b(?:completion|readout|scheduled|timeline|window|launch)\b", re.I)),
        ("fleet_size", re.compile(r"\b(?:fleet|vessels|ships|carriers)\b", re.I)),
        ("latency", re.compile(r"\b(?:latency|ping|delay|tps|throughput)\b", re.I)),
        ("qubits", re.compile(r"\b(?:qubit|qubits)\b", re.I)),
        ("temperature", re.compile(r"\b(?:temperature|base\s+temp|millikelvin|mK|kelvin)\b", re.I)),
        ("thermal_output", re.compile(r"\b(?:thermal\s+(?:output|rating)|mwth|mwe)\b", re.I)),
        ("attribution", re.compile(r"\b(?:attributed\b(?:\s+\S+){0,6}?\s+to|blamed\s+on|espionage\s+group|threat\s+actor)\b", re.I)),
        ("sample_size", re.compile(r"\b(?:cohort|sample\s+size|patients|subjects)\b", re.I)),
        ("foundation_date", re.compile(r"\b(?:dating|founded|foundation|bce|radiocarbon|calibrated\s+dates|century)\b", re.I)),
        ("dating", re.compile(r"\b(?:dating|radiocarbon|calibrated\s+dates|century)\b", re.I)),
        ("creep_life", re.compile(r"\b(?:creep|rupture\s+life)\b", re.I)),
        ("heat_capacity", re.compile(r"\b(?:heat\s+capacity|volumetric)\b", re.I)),
        ("resignation_timing", re.compile(r"\b(?:resigned|resignation|retirement|stepped\s+down)\b", re.I)),
        ("classification", re.compile(r"\b(?:classified\s+as|reclassified|classification|categori[sz]ed\s+as)\b", re.I)),
        ("invention_credit", re.compile(r"\b(?:invented|inventor|credited\s+(?:to|with)|priority\s+dispute)\b", re.I)),
    ]

    KIND_PHRASE_PATTERN = re.compile(
        r"(?P<value>[A-Z][\w-]*(?:\s+[A-Z][\w-]*){0,3}(?:\s*\([A-Z0-9-]+\))?)\s+"
        r"(?P<noun>[a-z][a-z-]{2,})\s+(?P<kind>chemistry|architecture|material|process|design|technology)\b"
    )

    # Categorical values are read from the sentence itself (the named party or class),
    # never from a list of known answers.
    _NAME = r"([A-Z][\w.&'-]*(?:\s+(?:of\s+|the\s+)?[A-Z0-9][\w.&'-]*){0,4})"
    CATEGORICAL_PATTERNS: dict[str, list[re.Pattern[str]]] = {
        "attribution": [re.compile(r"(?:attributed(?:\s+\S+){0,6}?\s+to|blamed\s+on|linked\s+to)\s+(?:the\s+)?" + _NAME)],
        "invention_credit": [
            re.compile(r"(?:invented\s+by|credited\s+to|discovered\s+by)\s+" + _NAME),
            re.compile(_NAME + r"\s+(?:invented|is\s+credited|was\s+credited)"),
        ],
        "classification": [
            re.compile(r"(?:re)?(?:classified|categori[sz]ed)\s+as\s+(?:an?\s+)?([a-z][\w-]*(?:\s+[a-z][\w-]*){0,2})", re.I),
        ],
    }

    NUMERIC_VALUE_PATTERN = re.compile(
        r"(\$)?\s*(\d+(?:,\d{3})*(?:\.\d+)?)\s*"
        r"(kg|g|t|wh/kg|kj/m3-k|kj/m3|kwh|mwh|gwh|mwth|mwe|mw|gw|kw|w|kn|mn|n|lbf|mpa|gpa|kpa|bar|psi|hours|hrs|days|years|km|m|cm|mm|%|percent|pct|bce|bc|ce|ad|ms|μs|us|s|ns|tps|ops/sec|mk|k|qubits|vessels|ships|patients|subjects|soldiers|troops|combatants|billion|million|b|m)?(?:\b|(?<=%))",
        re.I,
    )

    AUTHORITATIVE_SOURCE_TYPES: set[str] = {
        "official_certificate", "commercial_register", "regulatory_filing",
        "utility_dossier", "peer_reviewed_journal", "government_permit",
        "type_approval", "scientific_paper", "government_audit",
        "metrology_report",
        "government_advisory", "official_manifest", "laboratory_certification",
        "registry_search_negative", "iso_certification", "court_docket",
    }
    SECONDARY_SOURCE_TYPES: set[str] = {
        "trade_magazine", "industry_news", "press_release",
        "corporate_press_release", "factsheet", "cyber_report",
        "infosec_monthly", "news",
    }
    UNVERIFIED_SOURCE_TYPES: set[str] = {
        "forum_post", "blog_post", "tech_rumors", "social_media",
        "sales_brochure", "promotional_brochure", "venture_news",
        "preprint_server", "marketing", "unverified_blog",
    }

    def _assess_source_tier(self, source_type: str | None, url: str | None) -> int:
        """Return source tier: 1 (Authoritative), 2 (Secondary), 3 (Unverified / Rumor)."""
        st = (source_type or "").lower()
        u = (url or "").lower()
        if st in self.AUTHORITATIVE_SOURCE_TYPES:
            return 1
        host = urlparse(u).netloc if "://" in u else u
        if re.search(r"\.(?:gov|mil|int)(?:\.[a-z]{2})?$|\.gov\.[a-z]{2}$", host.split(":")[0]):
            return 1
        if st in self.UNVERIFIED_SOURCE_TYPES:
            return 3
        if any(dom in u for dom in ("forum", "blog", "rumor", "brochure")):
            return 3
        return 2

    def _matches_dimension_unit(self, dim: str, num: float, unit: str, is_dollar: bool) -> bool:
        """Verify that extracted numerical value and unit match the semantic expectation of the dimension."""
        u = (unit or "").lower()
        if dim in ("efficiency", "efficacy"):
            return u in ("%", "percent", "pct") or (not u and not is_dollar and 0.0 <= num <= 100.0)
        if dim in ("thrust", "payload"):
            return u in ("kn", "mn", "n", "lbf", "kg", "g", "t") or (not u and not is_dollar and num > 0)
        if dim == "energy_density":
            return u in ("wh/kg",) or (not u and not is_dollar and num > 0)
        if dim == "battery_capacity":
            return u in ("kwh", "mwh", "gwh", "wh") or (not u and not is_dollar and num > 0)
        if dim == "revenue":
            return is_dollar or u in ("usd", "dollar", "dollars", "billion", "million", "b", "m")
        if dim == "thermal_output":
            return u in ("mwth", "mwe", "mw", "gw", "kw", "w") or (not u and not is_dollar and num > 0)
        if dim == "latency":
            return u in ("ms", "μs", "us", "s", "ns", "tps", "ops/sec") or (not u and not is_dollar and num > 0)
        if dim == "temperature":
            return u in ("mk", "k") or (not u and not is_dollar and num >= 0)
        if dim == "qubits":
            return u in ("qubits",) or (not u and not is_dollar and num > 0)
        if dim in ("fleet_size", "sample_size"):
            return u in ("vessels", "ships", "patients", "subjects") or (not u and not is_dollar and num > 0)
        if dim in ("dating", "foundation_date"):
            return u in ("ce", "ad", "bce", "bc") or (not is_dollar and 500 <= num <= 2100)
        if dim == "creep_life":
            return u in ("hours", "hrs", "days") or (not is_dollar and num > 0)
        if dim == "heat_capacity":
            return u in ("kj/m3-k", "kj/m3", "j/g-k") or (not is_dollar and num > 0)
        if dim == "troop_strength":
            return u in ("troops", "soldiers", "combatants", "") and not is_dollar and not u.endswith("%") and u not in ("bce", "bc", "ce", "ad", "years", "hrs", "days")
        return True

    @staticmethod
    def _normalize_unit_and_value(dim: str, num: float, unit: str) -> tuple[float, str]:
        """Convert known unit variations to canonical base units for meaningful comparison."""
        u = (unit or "").lower().strip()
        val = num
        if dim in ("payload",):
            if u in ("t", "tons", "ton", "metric tons", "tonne", "tonnes"):
                return val * 1000.0, "kg"
            elif u in ("kg", "kilograms"):
                return val, "kg"
            elif u in ("g", "grams"):
                return val / 1000.0, "kg"
        elif dim in ("thrust",):
            if u in ("mn", "meganewtons"):
                return val * 1000.0, "kn"
            elif u in ("kn", "kilonewtons"):
                return val, "kn"
            elif u in ("n", "newtons"):
                return val / 1000.0, "kn"
        elif dim in ("latency",):
            if u in ("s", "seconds", "sec"):
                return val * 1000.0, "ms"
            elif u in ("ms", "milliseconds"):
                return val, "ms"
            elif u in ("μs", "us", "microseconds"):
                return val / 1000.0, "ms"
        elif dim in ("thermal_output",):
            if u in ("gw", "gigawatts"):
                return val * 1000.0, "mw"
            elif u in ("mw", "mwe", "mwth", "megawatts"):
                return val, "mw"
            elif u in ("kw", "kilowatts"):
                return val / 1000.0, "mw"
        elif dim in ("battery_capacity",):
            if u in ("gwh",):
                return val * 1000.0, "mwh"
            elif u in ("mwh",):
                return val, "mwh"
            elif u in ("kwh",):
                return val / 1000.0, "mwh"
        return val, u

    @staticmethod
    def _extract_condition(text: str) -> str | None:
        """Extract operating conditions (e.g. peak vs steady-state, sea-level vs vacuum)."""
        t = text.lower()
        if "sea-level" in t or "sea level" in t:
            return "sea_level"
        if "vacuum" in t:
            return "vacuum"
        if "peak" in t:
            return "peak"
        if "continuous" in t or "steady-state" in t or "steady state" in t:
            return "continuous"
        if "ambient" in t:
            return "ambient"
        if "cryogenic" in t:
            return "cryogenic"
        return None

    @staticmethod
    def _matches_entity(target: str, text: str, url: str = "") -> bool:
        """Check whether document text or URL references the target subject."""
        if not target:
            return True
        t_lower = target.lower().strip()
        full_text = f"{text} {url}".lower()
        if t_lower in full_text:
            return True
        # Check normalized hyphens/underscores/spaces (e.g., "titan-6" vs "titan6")
        t_clean = re.sub(r"[\s_-]+", "", t_lower)
        full_clean = re.sub(r"[\s_-]+", "", full_text)
        if len(t_clean) >= 4 and t_clean in full_clean:
            return True
        stopwords = {
            "the", "of", "and", "in", "at", "for", "to", "a", "an", "is", "was",
            "division", "consortium", "corporation", "ltd", "limited", "inc", "co", "llc", "plc",
            "company", "department", "unit", "group", "holdings", "alliance",
        }
        distinctive_tokens = [tok for tok in re.findall(r"\b[a-zA-Z0-9_-]+\b", t_lower) if tok not in stopwords and len(tok) >= 3]
        if distinctive_tokens:
            return any(tok in full_text for tok in distinctive_tokens)
        all_tokens = [tok for tok in re.findall(r"\b[a-zA-Z0-9_-]+\b", t_lower) if len(tok) >= 4]
        if len(all_tokens) >= 2:
            return sum(1 for tok in all_tokens if tok in full_text) >= 2
        return False

    def extract_comparable_claims(self, docs: list[dict[str, Any]], target_subject: str) -> list[ComparableClaim]:
        """Extract structured comparable claims from documents for a target subject."""
        claims: list[ComparableClaim] = []
        claim_idx = 0

        for doc in docs:
            text = doc.get("text") or doc.get("text_content") or ""
            title = doc.get("title") or ""
            url = doc.get("url") or ""
            if target_subject and not self._matches_entity(target_subject, f"{title} {text}", url):
                continue

            doc_type = doc.get("source_type") or "unknown"
            ev_id = doc.get("evidence_id") or ""
            date_match = re.search(r"\b(20\d\d-\d\d-\d\d|\b20\d\d\b)", text)
            doc_date = date_match.group(1) if date_match else None

            # Split into substantive sentences
            sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.strip()) > 20]

            for s in sentences:
                s_lower = s.lower()
                # Identify property dimension. A "<Value> <noun> <kind>" phrase ("Sodium-Ion
                # battery chemistry", "Transformer model architecture") names its own
                # categorical dimension; otherwise fall back to the measurement patterns.
                matched_dim = None
                kind_match = self.KIND_PHRASE_PATTERN.search(s)
                if kind_match:
                    matched_dim = f"{kind_match.group('noun').lower()}_{kind_match.group('kind').lower()}"
                for dim_name, pat in self.DIMENSION_PATTERNS:
                    if matched_dim:
                        break
                    if pat.search(s_lower):
                        matched_dim = dim_name
                        break

                if not matched_dim:
                    continue

                # Check preliminary / rumor indicators
                is_prelim = any(
                    k in s_lower
                    for k in (
                        "preliminary", "unconfirmed", "rumor", "blog post", "unverified",
                        "alleged", "forum post", "preprint", "speculation", "claims of", "pitch"
                    )
                )

                # Clean out SEC form identifiers (e.g. "Form 8-K", "10-K") before numeric extraction
                s_num_target = re.sub(r"\b(?:form\s+)?(?:8-k|10-k|10-q|20-f|s-1)\b", "", s, flags=re.I)

                # Extract numeric value: prioritize numbers with units matching the property dimension
                num_val = None
                unit_val = None
                num_matches = self.NUMERIC_VALUE_PATTERN.findall(s_num_target)
                valid_unit_matches = []
                for m in num_matches:
                    try:
                        clean_d = m[1].replace(",", "")
                        val_candidate = float(clean_d)
                        if (m[2] or m[0]) and self._matches_dimension_unit(matched_dim, val_candidate, m[2], bool(m[0])):
                            valid_unit_matches.append(m)
                    except ValueError:
                        pass
                chosen_matches = valid_unit_matches if valid_unit_matches else num_matches

                for is_dollar, digits, unit in chosen_matches:
                    clean_digits = digits.replace(",", "")
                    if clean_digits in target_subject and not unit and not is_dollar:
                        continue
                    try:
                        val = float(clean_digits)
                        if not self._matches_dimension_unit(matched_dim, val, unit, bool(is_dollar)):
                            continue
                        if is_dollar:
                            unit_lower = (unit or "").lower()
                            if unit_lower in ("b", "billion"):
                                val *= 1_000_000_000.0
                                unit_val = "usd"
                            elif unit_lower in ("m", "million"):
                                val *= 1_000_000.0
                                unit_val = "usd"
                            else:
                                unit_val = "usd"
                        else:
                            unit_val = (unit or "").lower()
                        num_val = val
                        break
                    except ValueError:
                        continue

                # Extract categorical value if present
                cat_val = None
                if kind_match:
                    cat_val = re.sub(r"\s+", " ", kind_match.group("value")).strip().lower()
                for cat_pat in self.CATEGORICAL_PATTERNS.get(matched_dim, []):
                    if cat_val:
                        break
                    m_cat = cat_pat.search(s)
                    if m_cat:
                        cat_val = m_cat.group(1).strip(" .,;:").lower()
                        break
                if matched_dim == "resignation_timing":
                    month_match = re.search(r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\b", s_lower)
                    if month_match:
                        cat_val = month_match.group(1)

                if not cat_val:
                    if re.search(r"\b(?:directly\s+contradicts?|disputes?|sharp\s+(?:historical\s+)?conflict|competing\s+estimates?|differing\s+accounts?)\b", s_lower):
                        cat_val = "disputed_or_contradicted"

                claim_idx += 1
                claims.append(
                    ComparableClaim(
                        claim_id=f"comp_{claim_idx}",
                        subject=target_subject,
                        property_dim=matched_dim,
                        raw_text=s,
                        numeric_value=num_val,
                        unit=unit_val,
                        categorical_value=cat_val,
                        temporal_anchor=doc_date,
                        source_url=url,
                        source_type=doc_type,
                        evidence_id=ev_id,
                        is_preliminary_or_rumor=is_prelim,
                        is_authoritative=(doc_type in ("official_certificate", "regulatory_filing", "commercial_register", "laboratory_certification", "government_audit", "peer_reviewed_journal")),
                    )
                )

        return claims

    # -------------------------------------------------------------------------
    # 2. Pairwise Claim Reconciliation & Contradiction Detection
    # -------------------------------------------------------------------------

    def detect_contradictions(self, claims: list[ComparableClaim]) -> list[ContradictionRecord]:
        """Compare all claims pairwise to identify substantive factual contradictions."""
        contradictions: list[ContradictionRecord] = []
        by_dim: dict[str, list[ComparableClaim]] = {}

        for c in claims:
            by_dim.setdefault(c.property_dim, []).append(c)

        for dim, dim_claims in by_dim.items():
            if len(dim_claims) < 2:
                continue

            for i in range(len(dim_claims)):
                for j in range(i + 1, len(dim_claims)):
                    c1 = dim_claims[i]
                    c2 = dim_claims[j]

                    # Check source independence (same URL or domain is not an independent conflict)
                    if c1.source_url and c2.source_url and c1.source_url == c2.source_url:
                        continue

                    dom1 = urlparse(c1.source_url or "").netloc.lower()
                    dom2 = urlparse(c2.source_url or "").netloc.lower()
                    if dom1 and dom2 and dom1 == dom2:
                        continue

                    # Check syndicated wire mirrors (verbatim identical or wire attribution)
                    raw1_clean = re.sub(r"\s+", " ", c1.raw_text.strip().lower())
                    raw2_clean = re.sub(r"\s+", " ", c2.raw_text.strip().lower())
                    if raw1_clean == raw2_clean:
                        continue
                    if any(w in raw1_clean for w in ("reuters", "associated press", "pr newswire", "business wire")) and any(w in raw2_clean for w in ("reuters", "associated press", "pr newswire", "business wire")):
                        continue

                    # Check Temporal Succession (e.g. rebranding, amendment, official update, or distinct years)
                    is_succession = any(
                        k in (c1.raw_text + " " + c2.raw_text).lower()
                        for k in ("rebranded to", "renamed to", "succeeded by", "formerly known as", "transitioned to", "replaced by")
                    )
                    if is_succession:
                        continue

                    # Check explicit temporal succession by year (e.g. In 2021 ... In 2024 ...)
                    year1_match = re.search(r"\b(20\d\d|19\d\d)\b", c1.raw_text)
                    year2_match = re.search(r"\b(20\d\d|19\d\d)\b", c2.raw_text)
                    if year1_match and year2_match and year1_match.group(1) != year2_match.group(1):
                        both_text = (c1.raw_text + " " + c2.raw_text).lower()
                        if any(w in both_text for w in ("in 20", "in 19", "grew to", "increased to", "decreased to", "appointed", "promoted", "later", "earlier", "previously", "subsequently")):
                            continue

                    # Check operational conditions (e.g. peak vs continuous, sea-level vs vacuum)
                    cond1 = self._extract_condition(c1.raw_text)
                    cond2 = self._extract_condition(c2.raw_text)
                    if cond1 and cond2 and cond1 != cond2:
                        # Measurements under different operating conditions are not contradictions
                        continue

                    # Source tiering & adjudication
                    tier1 = self._assess_source_tier(c1.source_type, c1.source_url)
                    tier2 = self._assess_source_tier(c2.source_type, c2.source_url)

                    if tier1 == 1 and tier2 >= 2:
                        contra_status = "RESOLVED_AUTHORITATIVE"
                        adjudication = f"Authoritative record ({c1.source_type}) supersedes lower-tier source ({c2.source_type})"
                        resolved_val = c1.numeric_value or c1.categorical_value
                    elif tier2 == 1 and tier1 >= 2:
                        contra_status = "RESOLVED_AUTHORITATIVE"
                        adjudication = f"Authoritative record ({c2.source_type}) supersedes lower-tier source ({c1.source_type})"
                        resolved_val = c2.numeric_value or c2.categorical_value
                    else:
                        contra_status = "UNRESOLVED_CONTRADICTION"
                        adjudication = f"Unresolved dispute between sources of comparable standing ({c1.source_type} vs {c2.source_type})"
                        resolved_val = None

                    # 1. Categorical Mutual Exclusivity & Explicit Conflicts
                    if c1.categorical_value and c2.categorical_value:
                        if c1.categorical_value != c2.categorical_value:
                            contradictions.append(
                                ContradictionRecord(
                                    topic=f"Contradictory {dim.replace('_', ' ').title()} Accounts for {c1.subject}: {c1.categorical_value} vs {c2.categorical_value}",
                                    subject=c1.subject,
                                    property_dim=dim,
                                    claim_a=c1.raw_text,
                                    claim_b=c2.raw_text,
                                    value_a=c1.categorical_value,
                                    value_b=c2.categorical_value,
                                    discrepancy_type=DiscrepancyType.CATEGORICAL_DISPUTE,
                                    source_a=c1.source_url or c1.source_type,
                                    source_b=c2.source_url or c2.source_type,
                                    evidence_id_a=c1.evidence_id,
                                    evidence_id_b=c2.evidence_id,
                                    status=contra_status,
                                    adjudication_rationale=adjudication,
                                    resolved_value=resolved_val,
                                )
                            )
                            break
                    elif (c1.categorical_value == "disputed_or_contradicted" or c2.categorical_value == "disputed_or_contradicted") and (c1.numeric_value is not None or c2.numeric_value is not None or c1.raw_text != c2.raw_text):
                        contradictions.append(
                            ContradictionRecord(
                                topic=f"Contradictory Accounts for {c1.subject} regarding {dim.replace('_', ' ').title()}: Explicit Conflict in Source Material",
                                subject=c1.subject,
                                property_dim=dim,
                                claim_a=c1.raw_text,
                                claim_b=c2.raw_text,
                                value_a=c1.categorical_value or str(c1.numeric_value or "asserted"),
                                value_b=c2.categorical_value or str(c2.numeric_value or "disputed"),
                                discrepancy_type=DiscrepancyType.CATEGORICAL_DISPUTE,
                                source_a=c1.source_url or c1.source_type,
                                source_b=c2.source_url or c2.source_type,
                                evidence_id_a=c1.evidence_id,
                                evidence_id_b=c2.evidence_id,
                                status=contra_status,
                                adjudication_rationale="Explicit textual contradiction identified across independent source material",
                                resolved_value=resolved_val,
                            )
                        )
                        break

                    # 2. Numerical Discrepancy (> 5% deviation)
                    if c1.numeric_value is not None and c2.numeric_value is not None:
                        val1, u1 = self._normalize_unit_and_value(dim, c1.numeric_value, c1.unit)
                        val2, u2 = self._normalize_unit_and_value(dim, c2.numeric_value, c2.unit)

                        # Skip if values are nearly identical
                        max_v = max(abs(val1), abs(val2))
                        if max_v > 0:
                            rel_diff = abs(val1 - val2) / max_v
                            # In historical dating (e.g. 3200 BCE vs 2400 BCE), difference is significant
                            if rel_diff > 0.05:
                                is_compat = (
                                    u1 == u2
                                    or not u1
                                    or not u2
                                    or (dim in ("troop_strength", "fleet_size", "sample_size"))
                                )
                                if is_compat:
                                    contradictions.append(
                                        ContradictionRecord(
                                            topic=f"Contradictory Numerical Metrics for {c1.subject} regarding {dim.replace('_', ' ').title()}: {val1} {u1} vs {val2} {u2}".strip(),
                                            subject=c1.subject,
                                            property_dim=dim,
                                            claim_a=c1.raw_text,
                                            claim_b=c2.raw_text,
                                            value_a=f"{val1} {u1}".strip(),
                                            value_b=f"{val2} {u2}".strip(),
                                            discrepancy_type=DiscrepancyType.NUMERICAL_DISCREPANCY,
                                            source_a=c1.source_url or c1.source_type,
                                            source_b=c2.source_url or c2.source_type,
                                            evidence_id_a=c1.evidence_id,
                                            evidence_id_b=c2.evidence_id,
                                            status=contra_status,
                                            adjudication_rationale=adjudication,
                                            resolved_value=resolved_val,
                                        )
                                    )
                                    break
                if contradictions and any(c.property_dim == dim for c in contradictions):
                    break

        return contradictions


_NEGATION_MARKERS = (
    "does not exist", "did not exist", "never existed", "never issued", "was never", "were never",
    "never acquired", "never granted", "zero affiliation", "no affiliation", "not affiliated",
    "unrelated entity", "no record", "fictitious", "nonexistent", "no such", "no division",
)


def self_negation_marker(sentence: str) -> bool:
    """True when a sentence denies existence or a link ("X does not exist", "never acquired")."""
    return any(m in sentence for m in _NEGATION_MARKERS)


class EntityScopeVerifier:
    """Enforces entity and relationship scope boundaries preventing parent contamination."""

    @staticmethod
    def is_negative_or_scoped_query(target_entity: str, objective: str) -> bool:
        """Check if query is evaluating the existence or absence of a specific department/role/subsidiary."""
        obj_lower = objective.lower()
        ent_lower = target_entity.lower()
        indicators = (
            "verify whether", "does not exist", "department of", "division of", "vp of",
            "vice president of", "fictitious", "nonexistent", "negative verification",
            "acquisition of",
        )
        return any(ind in obj_lower for ind in indicators) or any(ind in ent_lower for ind in indicators)

    @staticmethod
    def verify_entity_presence(target_entity: str, docs: list[dict[str, Any]]) -> tuple[bool, bool, str]:
        """Verify whether target entity is explicitly grounded, explicitly refuted, or absent.

        Returns: (is_grounded, is_explicitly_absent, rationale)
        """
        all_text = " ".join((d.get("text") or d.get("text_content") or "") for d in docs).lower()
        target_lower = target_entity.lower()

        tokens = [t for t in re.split(r"\W+", target_lower) if len(t) > 3 and t not in ("corporation", "limited", "company", "department", "division")]
        if not tokens:
            tokens = [target_lower]
        sentences = [
            sent.strip()
            for d in docs
            for sent in re.split(r"(?<=[.!?])\s+", (d.get("text") or d.get("text_content") or "").lower())
            if sent.strip()
        ]

        # An explicit negative record is a sentence that names the target and denies it exists
        # or denies the queried link.
        # The sentence may drop the parent name ("the mining division does not exist").
        named = tokens[1:] if len(tokens) > 1 else tokens
        for sent in sentences:
            if all(tok in sent for tok in named) and self_negation_marker(sent):
                return False, True, f"Authoritative documentation explicitly confirmed negative finding: '{sent[:160]}'."

        # A scoped target (a parent name plus sub-unit words) is grounded only where every
        # distinctive word appears together in one sentence; the parent alone is not enough.
        if len(tokens) > 1 and not any(all(tok in sent for tok in tokens) for sent in sentences):
            missing = [t for t in tokens if t not in all_text]
            if any(t in all_text for t in tokens) and missing:
                return False, False, f"Parent organization was referenced, but specific sub-entity modifiers {missing} were absent from all retrieved evidence."

        # Full target matching
        if target_lower in all_text or all(tok in all_text for tok in tokens):
            return True, False, "Target entity directly substantiated by evidence text."

        return False, False, f"Target entity '{target_entity}' was absent from all retrieved evidence."


class EpistemicSufficiencyEvaluator:
    """Evaluates evidence quality and enforces principled abstention."""

    PRELIMINARY_MARKERS = [
        "preliminary", "inconclusive", "failed to replicate", "null result",
        "unconfirmed", "unsubstantiated", "rumor", "blog post", "forum chatter",
        "preprint", "open question", "unproven",
        "cannot be determined", "in vitro only", "single-patient case",
        "internal dataset", "proprietary", "not public", "confidential"
    ]

    @classmethod
    def evaluate_sufficiency(cls, docs: list[dict[str, Any]], objective: str) -> tuple[bool, str]:
        """Evaluate if evidence is adequate to justify a definitive supported finding.

        Returns: (is_sufficient, reason)
        """
        if not docs:
            return False, "Zero evidence documents retrieved."

        combined_text = " ".join((d.get("text") or d.get("text_content") or "") for d in docs).lower()

        # Count preliminary indicators
        matched_markers = [m for m in cls.PRELIMINARY_MARKERS if m in combined_text]
        if matched_markers:
            # If document explicitly notes that finding is inconclusive, preliminary, unconfirmed, or failed
            if any(k in combined_text for k in ("inconclusive", "cannot be drawn", "remains undetermined", "open question", "completely unverified", "failed to replicate", "unsubstantiated")):
                return False, f"Authoritative sources explicitly state findings are inconclusive or preliminary ({matched_markers[:2]})."

        # A request for non-public detail (internal, proprietary, confidential...) is answered
        # only if the evidence actually discusses the requested specifics.
        obj_lower = objective.lower()
        nonpublic = ("internal", "proprietary", "confidential", "unreleased", "undisclosed", "secret", "non-public", "private")
        if any(re.search(rf"\b{re.escape(k)}\b", obj_lower) for k in nonpublic):
            generic = {"investigate", "determine", "identify", "details", "detail", "information", "about", "their", "which", "whether"}
            requested = {w for w in re.findall(r"[a-z][a-z-]{4,}", obj_lower) if w not in generic and w not in nonpublic}
            covered = {w for w in requested if w in combined_text}
            if requested and len(covered) * 2 < len(requested):
                return False, (
                    "Technical or organizational metrics requested are non-public or proprietary; public sources "
                    f"provide insufficient granularity (covered {len(covered)} of {len(requested)} requested terms)."
                )

        return True, "Evidence depth and authoritative sourcing satisfy epistemic sufficiency."
