"""Heimdallr V5.2: ONION_CAPABILITY_GAP_V2 Corpus.

Provides a comprehensive, defensive test corpus simulating:
1. Normal accessible .onion services
2. Redirect chains and canonical mirror networks
3. Transient 503 circuit failures and retries
4. 404 / 500 error responses and unavailable services
5. Malformed / corrupted HTML payloads
6. Large database leak documents (>1MB)
7. Non-UTF8 encoded payloads (Windows-1251, ISO-8859)
8. Deep link topologies with cycle links (A -> B -> A) and multiple paths
9. Decoy services with misleading titles
10. Normalized handed-document representations for Configuration B
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from argus.specialists.onion.corpus import ONION_CORPUS

# Base corpus cloned and extended with controlled transport conditions
CAPABILITY_GAP_V2_CORPUS: Dict[str, Dict[str, Any]] = dict(ONION_CORPUS)

# 1. Extended Transport Test Fixtures (Group B: Acquisition)
CAPABILITY_GAP_V2_CORPUS.update({
    "redirect_onion_service": {
        "onion_address": "redirectold112233445566778899aabbccddeeffgghhiijjkkllmmnno.onion",
        "service_name": "Legacy Extortion Redirect Endpoint",
        "category": "REDIRECT_SERVICE",
        "description": "Legacy hidden service issuing HTTP 301 Permanent Redirect to LockBit modern portal",
        "status": "REDIRECT_301",
        "redirect_target": "lockbitapt6vx57t3eeqjofwgcglmutr3a35nygvokja5uuccip4ykyd.onion",
        "mirrors": [],
        "sample_pages": [
            {
                "url": "http://redirectold112233445566778899aabbccddeeffgghhiijjkkllmmnno.onion/",
                "title": "301 Moved Permanently",
                "text": "Service moved to lockbitapt6vx57t3eeqjofwgcglmutr3a35nygvokja5uuccip4ykyd.onion",
                "status_code": 301,
            }
        ],
    },

    "retry_transient_503_service": {
        "onion_address": "retry503service7m24z2f3c7k7h9p4q2n6v8w0x2y4z6a8b0c2d4e.onion",
        "service_name": "Transient High-Load Leak Portal",
        "category": "TRANSIENT_SERVICE",
        "description": "Darknet service that initially returns 503 Service Unavailable, succeeding on retry attempt 2",
        "status": "TRANSIENT_503",
        "retry_success_after": 2,
        "mirrors": [],
        "sample_pages": [
            {
                "url": "http://retry503service7m24z2f3c7k7h9p4q2n6v8w0x2y4z6a8b0c2d4e.onion/leaks",
                "title": "Financial Audit Records 2024",
                "text": "Confidential financial statement and bank reconciliation spreadsheets for Apex Technologies.",
                "status_code": 200,
            }
        ],
    },

    "unavailable_onion_service": {
        "onion_address": "unavailable404onion7m24z2f3c7k7h9p4q2n6v8w0x2y4z6a8b0c2d4e.onion",
        "service_name": "Defunct Darknet Forum",
        "category": "UNAVAILABLE_SERVICE",
        "description": "Seized or dead hidden service with no active introduction points (returns 500 / 404)",
        "status": "OFFLINE",
        "mirrors": [],
        "sample_pages": [],
    },

    "malformed_payload_onion": {
        "onion_address": "malformedhtml7m24z2f3c7k7h9p4q2n6v8w0x2y4z6a8b0c2d4e.onion",
        "service_name": "Corrupted Breach Archive",
        "category": "MALFORMED_HTML",
        "description": "Hidden service emitting malformed unclosed tags, null bytes, and broken headers",
        "status": "ACTIVE",
        "mirrors": [],
        "sample_pages": [
            {
                "url": "http://malformedhtml7m24z2f3c7k7h9p4q2n6v8w0x2y4z6a8b0c2d4e.onion/dump",
                "title": "Raw Dump\x00<script>",
                "text": "Employee records: Name=John Doe, Title=Director of Engineering\x00<!-- unclosed table",
                "is_malformed": True,
            }
        ],
    },

    "large_dump_onion": {
        "onion_address": "largedumpmulti88m24z2f3c7k7h9p4q2n6v8w0x2y4z6a8b0c2d4e.onion",
        "service_name": "High-Volume SQL Dump Portal",
        "category": "LARGE_DATASET",
        "description": "Darknet archive serving a multi-megabyte compressed database dump",
        "status": "ACTIVE",
        "mirrors": [],
        "sample_pages": [
            {
                "url": "http://largedumpmulti88m24z2f3c7k7h9p4q2n6v8w0x2y4z6a8b0c2d4e.onion/database.sql",
                "title": "SQL Export - 2,500,000 Records",
                "text": "INSERT INTO users (id, email, role) VALUES ... " + ("(1, 'test@corp.com', 'admin'), " * 1000),
                "is_large": True,
                "size_bytes": 1048576,
            }
        ],
    },

    "encoding_variant_onion": {
        "onion_address": "russianforumcyrillic7m24z2f3c7k7h9p4q2n6v8w0x2y4z6a8b0c2d4e.onion",
        "service_name": "RuTor Cybercrime Syndicate Thread",
        "category": "ENCODING_TEST",
        "description": "Russian darknet forum thread encoded in Windows-1251 Cyrillic",
        "status": "ACTIVE",
        "mirrors": [],
        "sample_pages": [
            {
                "url": "http://russianforumcyrillic7m24z2f3c7k7h9p4q2n6v8w0x2y4z6a8b0c2d4e.onion/topic/142",
                "title": "База данных скомпрометирована",
                "text": "Утечка базы данных Apex Technologies: пароли, исходные коды и ключи шифрования.",
                "encoding": "windows-1251",
            }
        ],
    },

    # 2. Extended Crawl Topology Fixtures (Group C: Crawling)
    "cycle_link_onion": {
        "onion_address": "cyclelooplinks7m24z2f3c7k7h9p4q2n6v8w0x2y4z6a8b0c2d4e.onion",
        "service_name": "Cyclic Link Honeypot Blog",
        "category": "CRAWL_TOPOLOGY",
        "description": "Site with circular links between Page A and Page B to test crawler loop termination",
        "status": "ACTIVE",
        "mirrors": [],
        "sample_pages": [
            {
                "url": "http://cyclelooplinks7m24z2f3c7k7h9p4q2n6v8w0x2y4z6a8b0c2d4e.onion/page1",
                "title": "Page 1 - Entry",
                "text": "Navigation: Go to Page 2. Content: Lead analyst username is cyber_ghost.",
                "outgoing_links": ["http://cyclelooplinks7m24z2f3c7k7h9p4q2n6v8w0x2y4z6a8b0c2d4e.onion/page2"],
            },
            {
                "url": "http://cyclelooplinks7m24z2f3c7k7h9p4q2n6v8w0x2y4z6a8b0c2d4e.onion/page2",
                "title": "Page 2 - Intermediate",
                "text": "Navigation: Go back to Page 1 or proceed to Page 3.",
                "outgoing_links": [
                    "http://cyclelooplinks7m24z2f3c7k7h9p4q2n6v8w0x2y4z6a8b0c2d4e.onion/page1",
                    "http://cyclelooplinks7m24z2f3c7k7h9p4q2n6v8w0x2y4z6a8b0c2d4e.onion/page3",
                ],
            },
            {
                "url": "http://cyclelooplinks7m24z2f3c7k7h9p4q2n6v8w0x2y4z6a8b0c2d4e.onion/page3",
                "title": "Page 3 - Target",
                "text": "Target document: Monero address 888tNkZrPN6JsEgekjMnABU4TBzc2Dt29EPAvkFxbANsAnJYPbb3iQ1YBRk1UXcdRsiKc9dhwMVgN5S9cQUiyoogDavup3H",
                "outgoing_links": [],
            },
        ],
    },

    "deep_tree_onion": {
        "onion_address": "deeptreehierarchy7m24z2f3c7k7h9p4q2n6v8w0x2y4z6a8b0c2d4e.onion",
        "service_name": "Multi-Level Directory Archive",
        "category": "CRAWL_TOPOLOGY",
        "description": "Hierarchical directory spanning 5 depth levels; tests max_depth enforcement and stopping rules",
        "status": "ACTIVE",
        "mirrors": [],
        "sample_pages": [
            {
                "url": "http://deeptreehierarchy7m24z2f3c7k7h9p4q2n6v8w0x2y4z6a8b0c2d4e.onion/level1",
                "title": "Level 1 Directory",
                "text": "Index level 1. Go to Level 2.",
                "outgoing_links": ["http://deeptreehierarchy7m24z2f3c7k7h9p4q2n6v8w0x2y4z6a8b0c2d4e.onion/level2"],
            },
            {
                "url": "http://deeptreehierarchy7m24z2f3c7k7h9p4q2n6v8w0x2y4z6a8b0c2d4e.onion/level2",
                "title": "Level 2 Directory",
                "text": "Index level 2. Go to Level 3.",
                "outgoing_links": ["http://deeptreehierarchy7m24z2f3c7k7h9p4q2n6v8w0x2y4z6a8b0c2d4e.onion/level3"],
            },
            {
                "url": "http://deeptreehierarchy7m24z2f3c7k7h9p4q2n6v8w0x2y4z6a8b0c2d4e.onion/level3",
                "title": "Level 3 Target Document",
                "text": "Key claim: Subsidiary entity Altai Maritime Logistics is registered in Belize under registration 44921.",
                "outgoing_links": [],
            },
        ],
    },

    # 3. Decoys and Misleading Titles (Group A: Discovery)
    "decoy_misleading_title_onion": {
        "onion_address": "misleadingtitledecoy7m24z2f3c7k7h9p4q2n6v8w0x2y4z6a8b0c2d4e.onion",
        "service_name": "LockBit Official Decoy Blog",
        "category": "DECOY_MISLEADING",
        "description": "Benign parody or research site mimicking LockBit branding without authentic leak data",
        "status": "ACTIVE",
        "is_malicious_decoy": True,
        "mirrors": [],
        "sample_pages": [
            {
                "url": "http://misleadingtitledecoy7m24z2f3c7k7h9p4q2n6v8w0x2y4z6a8b0c2d4e.onion/",
                "title": "LockBit Official Press Release (Satire)",
                "text": "This is an academic honeypot research project studying extortion ecosystems.",
            }
        ],
    },
})


def get_normalized_document_for_task(target_onion_or_query: str) -> Optional[str]:
    """Retrieve normalized text content for a target service to feed Configuration B (Handed Documents)."""
    clean = target_onion_or_query.strip().lower()
    for _, s in CAPABILITY_GAP_V2_CORPUS.items():
        if clean in s.get("onion_address", "").lower() or any(clean in m.lower() for m in s.get("mirrors", [])):
            lines = [
                f"DOCUMENT TITLE: {s.get('service_name')}",
                f"SOURCE ONION ADDRESS: {s.get('onion_address')}",
                f"CATEGORY: {s.get('category')}",
                f"STATUS: {s.get('status')}",
                f"DESCRIPTION: {s.get('description', '')}",
            ]
            for p in s.get("sample_pages", []):
                lines.append(f"PAGE TITLE: {p.get('title')}")
                lines.append(f"PAGE BODY: {p.get('text')}")
            if s.get("crypto_addresses"):
                lines.append(f"CRYPTO ADDRESSES: {s.get('crypto_addresses')}")
            if s.get("pgp_fingerprints"):
                lines.append(f"PGP FINGERPRINTS: {s.get('pgp_fingerprints')}")
            if s.get("contact_identities"):
                lines.append(f"CONTACTS: {s.get('contact_identities')}")
            return "\n".join(lines)
    return None
