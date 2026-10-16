"""Context-Aware Relevance and Entity Attribution Engine.

Evaluates whether infrastructure endpoints, domain names, and extracted entities
are contextually relevant to an investigation, rather than relying on crude domain blacklists.

Principles:
1. Target-Attribution Relevance: If an infrastructure host belongs to or matches an entity
   under investigation (e.g. 'paramsoftware.com' for 'Param Software'), it is relevant.
2. Objective-Scope Relevance: If an investigation specifically targets or queries infrastructure,
   CDNs, streaming endpoints, DNS, or a platform like Google/YouTube, those hosts ARE relevant.
3. Incidental Third-Party Platform Discrimination: When researching an unrelated subject
   (e.g. a person or corporate entity), third-party hosting platforms (e.g. YouTube, Vimeo,
   LinkedIn, Twitter/X) deliver content via internal media streaming CDNs (e.g. googlevideo.com,
   ytimg.com, twimg.com, licdn.com). These endpoints belong to the hosting platform's transport
   fleet, NOT to the investigated subject.
4. Incidental Tracker/Ad-Tech Discrimination: Generic web trackers (e.g. Google Analytics,
   Google Tag Manager, DoubleClick, Sentry) embedded on third-party sites are transport/analytics
   instrumentation rather than subject infrastructure, unless tracking/telemetry is the focus.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse


# Mapping of third-party public hosting and telemetry platforms to their internal media/CDN/API fleets
THIRD_PARTY_PLATFORM_FLEETS: dict[str, set[str]] = {
    "youtube.com": {"googlevideo.com", "ytimg.com", "ggpht.com", "gstatic.com", "google.com", "googleapis.com"},
    "youtu.be": {"googlevideo.com", "ytimg.com", "ggpht.com", "gstatic.com", "google.com"},
    "linkedin.com": {"licdn.com", "linkedin.com"},
    "facebook.com": {"fbcdn.net", "facebook.com", "fbsbx.com"},
    "twitter.com": {"twimg.com", "twitter.com", "t.co", "x.com"},
    "x.com": {"twimg.com", "twitter.com", "t.co", "x.com"},
    "reddit.com": {"redditmedia.com", "redd.it", "reddit.com"},
    "medium.com": {"medium.com"},
    "github.com": {"githubusercontent.com", "github.com"},
    "vimeo.com": {"vimeocdn.com", "vimeo.com"},
    "theirstack.com": {"theirstack.com", "api.theirstack.com"},
    "enlyft.com": {"enlyft.com"},
    "6sense.com": {"6sense.com"},
    "rapidapi.com": {"rapidapi.com"},
    "slintel.com": {"slintel.com"},
    "appsruntheworld.com": {"appsruntheworld.com"},
    "datanyze.com": {"datanyze.com"},
    "zoominfo.com": {"zoominfo.com"},
}

GENERIC_TRACKERS: set[str] = {
    "doubleclick.net",
    "google-analytics.com",
    "googletagmanager.com",
    "sentry.io",
    "datadoghq.com",
    "recaptcha.net",
    "facebook.net",
}


def clean_entity_name(name: str) -> str:
    """Strip interview, headline, and article preamble to yield canonical entity name."""
    if not name:
        return "Unknown Entity"
    clean = name.strip()
    clean = re.sub(r"^In\s+Conversation\s+with\s+(?:Mr\.?|Ms\.?|Dr\.?)?\s*", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"^Meet\s+the\s+Maker\s*\|\s*", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"^Know\s+Our\s+IACC\s+Member\s*[-—:]?\s*", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\s*[-—|].*$", "", clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean or name.strip()


def is_contextually_relevant_host(
    host: str,
    doc_url: str = "",
    target_objective: str = "",
    target_entities: list[str] | None = None,
) -> bool:
    """Evaluate whether an infrastructure host is contextually relevant to the investigation.

    DOES NOT use a crude domain blacklist. A host like 'googlevideo.com' or 'google.com'
    is fully accepted if the investigation is investigating Google, YouTube, CDN infrastructure,
    video delivery, or network topology.
    It is rejected only when it represents an incidental media transport asset of a hosting platform
    during an investigation of an unrelated target.
    """
    if not host or not isinstance(host, str):
        return False

    host_clean = host.strip().lower()
    obj_clean = (target_objective or "").lower()
    entities_clean = [str(e).lower() for e in (target_entities or [])]

    # Extract target tokens (words of 3+ alphanumeric chars)
    target_tokens = set(re.findall(r"[a-z0-9]{3,}", obj_clean))
    for ent in entities_clean:
        target_tokens.update(re.findall(r"[a-z0-9]{3,}", ent))

    # 1. Target Affiliation Match:
    # If the host contains a target token (e.g. 'paramsoftware' in 'paramsoftware.com',
    # or 'google' in 'google.com' when Google is investigated), it is directly relevant.
    for tok in target_tokens:
        if tok in host_clean:
            return True

    # 2. Objective Infrastructure Scope:
    # If the objective specifically queries infrastructure, streaming, CDN, network topology,
    # or Google/YouTube, then infrastructure hosts belonging to those fleets ARE relevant.
    infra_intent_keywords = (
        "infrastructure", "network", "cdn", "streaming", "video delivery",
        "dns", "asn", "ip address", "server", "topology", "san", "certificate",
        "google", "youtube", "telemetry", "tracking"
    )
    is_infra_scoped_investigation = any(kw in obj_clean for kw in infra_intent_keywords)

    # 3. Third-Party Hosting Platform Transport Discrimination:
    # If the document originated from a public content platform (e.g. YouTube):
    if doc_url:
        parsed_doc = urlparse(doc_url if "://" in doc_url else f"https://{doc_url}")
        doc_domain = parsed_doc.netloc.lower()

        for platform, internal_hosts in THIRD_PARTY_PLATFORM_FLEETS.items():
            if platform in doc_domain:
                # The document is hosted on this public platform (e.g. YouTube).
                for ih in internal_hosts:
                    if ih in host_clean:
                        # If the investigation is NOT specifically investigating that platform
                        # and NOT investigating video streaming/CDN infrastructure, then this host
                        # is incidental transport, not target infrastructure.
                        platform_token = platform.split(".")[0]
                        if platform_token in target_tokens or is_infra_scoped_investigation:
                            return True
                        return False

    # 4. Standalone Host Platform Fleet Check (when doc_url is empty):
    # If a host belongs to a major platform fleet (e.g. googlevideo.com):
    for platform, internal_hosts in THIRD_PARTY_PLATFORM_FLEETS.items():
        for ih in internal_hosts:
            if ih in host_clean:
                platform_token = platform.split(".")[0]
                if platform_token in target_tokens or is_infra_scoped_investigation:
                    return True
                # If neither the target nor the objective touches this platform/infra,
                # it is an ungrounded third-party platform asset.
                return False

    # 5. Generic Public Tracking & Telemetry Discrimination:
    for tracker in GENERIC_TRACKERS:
        if tracker in host_clean:
            tracker_tok = tracker.split(".")[0]
            if tracker_tok in target_tokens or "telemetry" in obj_clean or "tracker" in obj_clean:
                return True
            return False

    return True
