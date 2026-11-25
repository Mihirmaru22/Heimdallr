"""The names a product goes by, and how to tell a mention of it from a look-alike word.

"Teamcenter" is unmistakable; "SAP" is also a word in other contexts and a ticker, so a short name is never
searched or matched alone: only its longer names ("SAP S/4HANA", "SAP ERP") count as a mention.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Common enterprise products and the names filings, job ads and case studies use for them. Keys are lower-case.
KNOWN: dict[str, list[str]] = {
    "teamcenter": ["Teamcenter", "Siemens Teamcenter", "TcPLM", "Teamcenter X"],
    "sap": ["SAP S/4HANA", "S/4HANA", "SAP ERP", "SAP ECC", "SAP R/3", "SAP Business One", "SAP SuccessFactors",
            "SAP Ariba"],
    "sap erp": ["SAP S/4HANA", "S/4HANA", "SAP ERP", "SAP ECC", "SAP R/3"],
    "s/4hana": ["S/4HANA", "SAP S/4HANA"],
    "windchill": ["Windchill", "PTC Windchill"],
    "solidworks": ["SolidWorks", "SOLIDWORKS"],
    "catia": ["CATIA"],
    "3dexperience": ["3DEXPERIENCE"],
    "salesforce": ["Salesforce.com", "Salesforce CRM", "Salesforce Sales Cloud", "Salesforce Service Cloud"],
    "workday": ["Workday HCM", "Workday Financials", "Workday Human Capital"],
    "servicenow": ["ServiceNow"],
    "netsuite": ["NetSuite", "Oracle NetSuite"],
    "oracle erp": ["Oracle ERP Cloud", "Oracle E-Business Suite", "Oracle Fusion", "JD Edwards", "PeopleSoft"],
    "dynamics 365": ["Microsoft Dynamics 365", "Dynamics 365", "Dynamics AX", "Dynamics NAV"],
    "epicor": ["Epicor"],
    "infor": ["Infor CloudSuite", "Infor LN", "Infor M3", "Infor SyteLine"],
    "snowflake": ["Snowflake Data Cloud"],
    "autocad": ["AutoCAD"],
    "ansys": ["Ansys Fluent", "Ansys Mechanical", "ANSYS"],
}
SHORT = re.compile(r"^[A-Za-z]{1,4}$")  # SAP, PTC, IFS: too short to trust on its own
# A one-word name this common in everyday English ("Vault", "Fusion", "Dynamics", "Cloud") names many other things:
# "Vault" alone matched HashiCorp Vault, Veeam's data vault and Vault Platform, and delivered Neptune Energy as a
# Veeva Vault user (2026-11-25). Coined names sit well below it: Windchill 2.1, NetSuite 2.1, Workday 2.9,
# Snowflake 3.3; Vault 3.9 (Zipf scale, wordfreq).
COMMON_WORD_ZIPF = 3.5


@dataclass
class Product:
    name: str  # as the person typed it
    names: list[str] = field(default_factory=list)  # every name that counts as a mention

    @property
    def patterns(self) -> list[re.Pattern[str]]:
        out = []
        for n in self.names:
            # Case matters for short all-caps names (CATIA, ANSYS) so "Catia" the first name does not count.
            flags = 0 if n.isupper() and len(n) <= 6 else re.I
            out.append(re.compile(rf"(?<![\w/]){re.escape(n)}(?![\w/])", flags))
        return out

    def mentioned_in(self, text: str) -> bool:
        return any(p.search(text) for p in self.patterns)


def product_for(name: str, aliases: list[str] | None = None) -> Product:
    """The product and its names: the typed name, the known names, and any the planner suggested."""
    key = re.sub(r"\s+", " ", name.strip().lower())
    names = list(KNOWN.get(key, []))
    known = {n.lower() for n in names}
    for n in [name.strip(), *(aliases or [])]:
        n = n.strip()
        # A known name keeps its own spelling: "catia" typed must not undo matching "CATIA" by case.
        if n and n.lower() not in known and not SHORT.match(n) and len(n) <= 60:
            names.append(n)
    if not names:  # only a short name was given and it is not one we know: use it, case-sensitively
        names = [name.strip()]
    names = list(dict.fromkeys(names))
    distinct = [n for n in names if not common_word(n)]
    return Product(name.strip(), distinct or names)  # a common word alone is kept only when it is the only name


def common_word(name: str) -> bool:
    """One everyday English word, too common to count as a mention of a product on its own."""
    if " " in name.strip() or not name.strip().isalpha():
        return False
    try:
        from wordfreq import zipf_frequency
    except ImportError:  # the word list is an optional dependency: without it no name is dropped
        return False
    return zipf_frequency(name.strip().lower(), "en") >= COMMON_WORD_ZIPF
