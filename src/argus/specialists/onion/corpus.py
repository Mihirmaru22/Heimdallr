"""Heimdallr V5: Onion & Dark-Web Frozen Intelligence Corpus.

Comprehensive frozen benchmark corpus containing realistic defensive intelligence
profiles for Tor hidden services across 60+ scenarios.
Used for deterministic, non-leaking evaluation of discovery, crawling, extraction,
temporal analysis, and cross-specialist multi-hop reasoning.
"""

from __future__ import annotations

from typing import Any, Dict, List
from argus.specialists.onion.models import OnionService, OnionServiceStatus


ONION_CORPUS: Dict[str, Dict[str, Any]] = {
    # 1. Ransomware & Data Extortion Portals
    "alphv_blackcat": {
        "onion_address": "alphvmmm27yku4xb25v45w3h4vj3lsq4u7z3mefqfx42n3p4a23bfdqd.onion",
        "service_name": "ALPHV / BlackCat Data Leak Portal",
        "category": "RANSOMWARE_LEAK_SITE",
        "description": "Public data extortion and victim publication blog associated with ALPHV / BlackCat threat group.",
        "first_seen": "2021-11-15T08:00:00Z",
        "last_seen": "2023-12-19T14:30:00Z",
        "status": "SEIZED",
        "mirrors": [
            "alphvmirror1123456789abcdefghijklmnopqrstuvwxyz123456789ab.onion",
            "alphvbackup2987654321abcdefghijklmnopqrstuvwxyz123456789ab.onion",
        ],
        "clearnet_domains": ["blackcat-leaks.info", "alphv-press.org"],
        "associated_entities": ["ALPHV Group", "BlackCat", "Noberus", "Dmitry Khoroshev"],
        "crypto_addresses": {
            "BTC": ["bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh", "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"],
            "XMR": ["888tNkZrPN6JsEgekjMnABU4TBzc2Dt29EPAvkFxbANsAnJYPbb3iQ1YBRk1UXcdRsiKc9dhwMVgN5S9cQUiyoogDavup3H"],
        },
        "contact_identities": ["alphv_support@xmpp.is", "blackcat_ops@jabber.ru", "tox:78A9C12..."],
        "pgp_fingerprints": ["4A8B 9C1D 2E3F 4A5B 6C7D  8E9F 0A1B 2C3D 4E5F 6A7B"],
        "server_fingerprint": "nginx/1.18.0 (Debian) [Tor-v3]",
        "indexed_pages_count": 142,
        "is_malicious_decoy": False,
        "sample_pages": [
            {
                "url": "http://alphvmmm27yku4xb25v45w3h4vj3lsq4u7z3mefqfx42n3p4a23bfdqd.onion/posts/apex-tech",
                "title": "Apex Technologies Group - Compromise Disclosure",
                "text": "Apex Technologies Group Inc (Delaware). 450 GB source code and telemetry clusters archived. Negotiate via Tox ID or Tor portal.",
            },
            {
                "url": "http://alphvmmm27yku4xb25v45w3h4vj3lsq4u7z3mefqfx42n3p4a23bfdqd.onion/seizure_notice",
                "title": "Law Enforcement Seizure Notice",
                "text": "This hidden site has been seized by the Federal Bureau of Investigation, Department of Justice, in coordination with international partners.",
            }
        ]
    },

    "lockbit_supp": {
        "onion_address": "lockbitapt6vx57t3eeqjofwgcglmutr3a35nygvokja5uuccip4ykyd.onion",
        "service_name": "LockBit 3.0 Extortion & Affiliate Portal",
        "category": "RANSOMWARE_LEAK_SITE",
        "description": "LockBit Supp leak site publishing stolen corporate archives, negotiations, and bounty programs.",
        "first_seen": "2019-09-03T12:00:00Z",
        "last_seen": "2024-02-20T10:00:00Z",
        "status": "SEIZED",
        "mirrors": [
            "lockbit7xxxyyyzzz123456789abcdefghijklmnopqrstuvwxyz123456.onion",
            "lockbitbackup333444555666777888999aaabbbcccdddeeefffggghh.onion",
        ],
        "clearnet_domains": ["lockbit-blog.com"],
        "associated_entities": ["LockBit Supp", "Dmitry Yuryevich Khoroshev", "LockBit 3.0", "Operation Cronos"],
        "crypto_addresses": {
            "BTC": ["bc1q9876543210zyxwvu9876543210zyxwvu987654", "3J98t1WpEZ73CNmQviecrnyiWrnqRhWNLy"],
            "XMR": ["84vxKSmzNfX7Z9eQUiyoogDavup3H888tNkZrPN6JsEgekjMnABU4TBzc2Dt29EPAvkFxbANsAnJYPbb3iQ1YBRk1UXcdRsi"],
        },
        "contact_identities": ["lockbitsupp@tox.chat", "lockbit_press@jabber.cd"],
        "pgp_fingerprints": ["E7C2 B89A 1D34 5F67 89AB  CDEF 0123 4567 89AB CDEF"],
        "server_fingerprint": "Apache/2.4.41 (Ubuntu)",
        "indexed_pages_count": 512,
        "is_malicious_decoy": False,
        "sample_pages": [
            {
                "url": "http://lockbitapt6vx57t3eeqjofwgcglmutr3a35nygvokja5uuccip4ykyd.onion/rules",
                "title": "LockBit Affiliate Terms and Bug Bounty",
                "text": "Deposit required for affiliate panel access. Minimum payout 20% to core operator. PGP encrypted negotiations only.",
            }
        ]
    },

    "cl0p_torrent_drop": {
        "onion_address": "cl0p52gcvho3aveqmg7fvgarqvd2ek2gahqqqll4qjzn2vdre5ph4xqd.onion",
        "service_name": "CL0P MOVEit Transfer Leak Repository",
        "category": "DATA_EXTORTION",
        "description": "Torrent index and direct download repository for MOVEit vulnerability extortion dumps.",
        "first_seen": "2023-06-05T09:15:00Z",
        "last_seen": "2024-05-01T16:00:00Z",
        "status": "ACTIVE",
        "mirrors": [
            "cl0p4x3b2v5q7y9z1a3c5e7g9i1k3m5o7q9s1u3w5y7a9b1c3d5e7f9g.onion",
            "cl0pmirror2233445566778899aabbccddeeffgghhiijjkkllmmnnoopp.onion",
        ],
        "clearnet_domains": [],
        "associated_entities": ["CL0P Syndicate", "CL0P Ransomware Team", "Lace Tempest", "FIN11", "TA505"],
        "crypto_addresses": {
            "BTC": ["bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4"],
        },
        "contact_identities": ["cl0p_press@xmpp.ru", "moveit_negotiate@onionmail.org"],
        "pgp_fingerprints": ["98BA 76DC 54FE 3210 FEDC  BA98 7654 3210 1234 5678"],
        "server_fingerprint": "caddy/v2.6.4",
        "indexed_pages_count": 89,
        "is_malicious_decoy": False,
        "sample_pages": [
            {
                "url": "http://cl0p52gcvho3aveqmg7fvgarqvd2ek2gahqqqll4qjzn2vdre5ph4xqd.onion/apex-europe",
                "title": "Apex Technologies Europe Ltd - Internal Financials",
                "text": "All UK and German internal communications leaked. 180 GB torrent published. No ransom agreed.",
            }
        ]
    },

    # 2. Threat Actor Infrastructure & C2 Relays
    "sandworm_telecom_c2": {
        "onion_address": "sandwrm74455c2relay7m24z2f3c7k7h9p4q2n6v8w0x2y4z6a8b0c2d4e.onion",
        "service_name": "Sandworm Unit 74455 Hidden Relay",
        "category": "THREAT_INFRASTRUCTURE",
        "description": "Tactical onion relay used for out-of-band telemetry and satellite command forwarding.",
        "first_seen": "2022-03-10T11:00:00Z",
        "last_seen": "2023-08-14T19:22:00Z",
        "status": "HISTORICAL_OFFLINE",
        "mirrors": ["sandwormc2relay736481928374659102938475610293847561029384.onion"],
        "clearnet_domains": ["telemetry-cluster-01.apex-telemetry.co.uk"],
        "associated_entities": ["Sandworm", "GRU Unit 74455", "Main Directorate of the General Staff", "Maksim Yakubets"],
        "crypto_addresses": {},
        "contact_identities": ["c2admin@sandworm-relay.sec"],
        "pgp_fingerprints": [],
        "server_fingerprint": "OpenSSH_8.2p1 Debian",
        "indexed_pages_count": 3,
        "is_malicious_decoy": False,
        "sample_pages": [
            {
                "url": "http://sandwrm74455c2relay7m24z2f3c7k7h9p4q2n6v8w0x2y4z6a8b0c2d4e.onion/status",
                "title": "Relay Node Status",
                "text": "Relay node operational. Upstream peer connected: telemetry-cluster-01.apex-telemetry.co.uk. Cryptographic session active.",
            }
        ]
    },

    "lazarus_crypto_escrow": {
        "onion_address": "lazescrow8934k2m7n9p1q3r5t7v9x1z3b5d7f9h1j3l5n7p9r1t3v5x7z.onion",
        "service_name": "Lazarus OTC Crypto Escrow",
        "category": "ILLICIT_FINANCE",
        "description": "Underground over-the-counter automated crypto swapping desk associated with DPRK Reconnaissance General Bureau.",
        "first_seen": "2020-05-18T14:00:00Z",
        "last_seen": "2024-04-10T08:45:00Z",
        "status": "ACTIVE",
        "mirrors": [
            "lazarusescrow777888999aaabbbcccdddeeefffggghhhiiijjjkkklll.onion",
            "lazarusbackup111222333444555666777888999aaabbbcccdddeeefff.onion",
        ],
        "clearnet_domains": [],
        "associated_entities": ["Lazarus Group", "Reconnaissance General Bureau", "Kim Il", "Chosun Expo", "Andiel"],
        "crypto_addresses": {
            "BTC": ["1F1tAaz5x1HUXrCNLbtMDqcw6o5GNn4xqX", "bc1qgdjqv0av3q56jvd82tkdjpy7gdp9ut8tlqmgrpmv24sq90ecnvqqjwvw97"],
            "ETH": ["0x098B716B8Aaf21512996dC57EB0615e2383E2f96"],
        },
        "contact_identities": ["lazarus_escrow@xmpp.jp"],
        "pgp_fingerprints": ["B5E1 38F9 2A4C 7D0E 1B8F  9C2A 4E6D 8F0A 1C3E 5B7D"],
        "server_fingerprint": "nginx/1.20.1",
        "indexed_pages_count": 28,
        "is_malicious_decoy": False,
        "sample_pages": [
            {
                "url": "http://lazescrow8934k2m7n9p1q3r5t7v9x1z3b5d7f9h1j3l5n7p9r1t3v5x7z.onion/exchange",
                "title": "Automated Cross-Chain Asset Liquidation",
                "text": "Instant liquidation for BTC/XMR/ETH with zero KYC requirements. Backed by syndicated reserve pool.",
            }
        ]
    },

    # 3. Darknet Forums, PGP Repositories & Hacker Hubs
    "dread_forum": {
        "onion_address": "dread462g6f5mtyv5y52m6k7h27qeq4e44qndzfvj52vskb5k57n2zqd.onion",
        "service_name": "Dread Community & OSINT Forum",
        "category": "COMMUNITY_FORUM",
        "description": "Reddit-style Tor hidden discussion forum focusing on darknet markets, opsec, PGP, and reviews.",
        "first_seen": "2018-02-15T00:00:00Z",
        "last_seen": "2026-10-01T12:00:00Z",
        "status": "ACTIVE",
        "mirrors": [
            "dreadf37yku4xb25v45w3h4vj3lsq4u7z3mefqfx42n3p4a23bfdqd123.onion",
            "dreadmirror23456789abcdefghijklmnopqrstuvwxyz123456789abcd.onion",
            "dreadbackup9876543210abcdefghijklmnopqrstuvwxyz123456789ab.onion",
        ],
        "clearnet_domains": [],
        "associated_entities": ["Dread Forum", "HugBunter", "Paris", "Dread Community"],
        "crypto_addresses": {
            "BTC": ["bc1q7dreaddonationaddress00011122233344455566677"],
            "XMR": ["888dreadxmrsupportaddress000111222333444555666777888999aaabbbcccdddeeefffggghhhiiijjjkkklll"],
        },
        "contact_identities": ["hugbunter@dread.onion", "staff@dread.onion"],
        "pgp_fingerprints": ["9A3B 7C1D 4E2F 8A0B 5C9D  1E3F 7A2B 4C8D 0E1F 3A5B"],
        "server_fingerprint": "Custom Epoll Daemon / Tor-v3",
        "indexed_pages_count": 8420,
        "is_malicious_decoy": False,
        "sample_pages": [
            {
                "url": "http://dread462g6f5mtyv5y52m6k7h27qeq4e44qndzfvj52vskb5k57n2zqd.onion/d/cybersec",
                "title": "Analysis of Horizon Aerospace Acquisition",
                "text": "Thread by @dr_kroll: Reverse engineering of telemetry firmware acquired from Nordic Space GmbH.",
            }
        ]
    },

    # 4. Whistleblower & Investigative Disclosures
    "secure_drop_whistleblower": {
        "onion_address": "securedropwhistle77m24z2f3c7k7h9p4q2n6v8w0x2y4z6a8b0c2d4e.onion",
        "service_name": "International Transparency SecureDrop",
        "category": "WHISTLEBLOWER_PORTAL",
        "description": "Encrypted whistleblower submission system for corporate governance, offshore corruption, and compliance violations.",
        "first_seen": "2020-01-10T10:00:00Z",
        "last_seen": "2026-10-08T00:00:00Z",
        "status": "ACTIVE",
        "mirrors": [
            "securedrop777888999aaabbbcccdddeeefffggghhhiiijjjkkklllmmmn.onion",
            "transparencybackup111222333444555666777888999aaabbbcccddd.onion",
        ],
        "clearnet_domains": ["transparency-international.org", "freedom.press"],
        "associated_entities": ["Freedom of the Press Foundation", "ICIJ", "OCCRP", "SecureDrop Consortium"],
        "crypto_addresses": {},
        "contact_identities": ["press@freedom.press"],
        "pgp_fingerprints": ["1122 3344 5566 7788 9900  AABB CCDD EEFF 0011 2233"],
        "server_fingerprint": "SecureDrop/2.7.0 (Debian)",
        "indexed_pages_count": 12,
        "is_malicious_decoy": False,
        "sample_pages": [
            {
                "url": "http://securedropwhistle77m24z2f3c7k7h9p4q2n6v8w0x2y4z6a8b0c2d4e.onion/submissions",
                "title": "Secure Submission Gateway",
                "text": "Submit confidential documents regarding BVI offshore trusts, Altai Resources, and nominee ownership chains.",
            }
        ]
    },

    # 5. Phishing Clones & Adversarial Decoys
    "alphv_phishing_clone": {
        "onion_address": "alphvphish112233445566778899aabbccddeeffgghhiijjkkllmmnnoo.onion",
        "service_name": "ALPHV Phishing Replica (Adversarial Decoy)",
        "category": "PHISHING_CLONE",
        "description": "Fraudulent lookalike mirror copying ALPHV branding designed to steal ransom payments via address substitution.",
        "first_seen": "2023-01-15T12:00:00Z",
        "last_seen": "2023-05-10T18:00:00Z",
        "status": "DEFACED",
        "mirrors": ["lockb1tsupp0rtph1sh1ngc10ne7m24z2f3c7k7h9p4q2n6v8w0x2y4z6.onion"],
        "clearnet_domains": [],
        "associated_entities": ["Unknown Phishing Actor", "Imposter Network"],
        "crypto_addresses": {
            "BTC": ["1FakePhishingBtcAddressScamActor9999999999"],
        },
        "contact_identities": ["fake_alphv@onionmail.com"],
        "pgp_fingerprints": ["DEAD BEEF 0000 1111 2222  3333 4444 5555 6666 7777"],
        "server_fingerprint": "nginx/1.14.0",
        "indexed_pages_count": 8,
        "is_malicious_decoy": True,
        "sample_pages": [
            {
                "url": "http://alphvphish112233445566778899aabbccddeeffgghhiijjkkllmmnnoo.onion/pay",
                "title": "Payment Portal (Spoofed)",
                "text": "Send ransom directly to 1FakePhishingBtcAddressScamActor9999999999. Do not contact negotiation desk.",
            }
        ]
    },

    # 6. Corporate Leaks & Offshore Shadow Services
    "altai_shadow_holding_onion": {
        "onion_address": "altaishadowportal7m24z2f3c7k7h9p4q2n6v8w0x2y4z6a8b0c2d4e.onion",
        "service_name": "Altai Resources Offshore Confidential Portal",
        "category": "OFFSHORE_PORTAL",
        "description": "Private client document repository for Altai Resources International BVI and associated Cypriot nominees.",
        "first_seen": "2021-04-12T10:00:00Z",
        "last_seen": "2025-01-10T16:00:00Z",
        "status": "ACTIVE",
        "mirrors": [
            "altaitrust777888999aaabbbcccdddeeefffggghhhiiijjjkkklllmmmo.onion",
            "altaibackup222333444555666777888999aaabbbcccdddeeefffggghh.onion",
        ],
        "clearnet_domains": ["altai-resources.com"],
        "associated_entities": ["Altai Resources International BVI", "Altai Shadow Holding", "Dmitri Volkov", "Cyprus Corporate Services Trust"],
        "crypto_addresses": {
            "BTC": ["bc1qaltai9999888877776666555544443333222211"],
        },
        "contact_identities": ["trustee@altaitrust.onion", "dvolkov@altai-resources.com"],
        "pgp_fingerprints": ["6B8A 1D2C 3E4F 5A6B 7C8D  9E0F 1A2B 3C4D 5E6F 7A8B"],
        "server_fingerprint": "lighttpd/1.4.59",
        "indexed_pages_count": 34,
        "is_malicious_decoy": False,
        "sample_pages": [
            {
                "url": "http://altaishadowportal7m24z2f3c7k7h9p4q2n6v8w0x2y4z6a8b0c2d4e.onion/docs/deed",
                "title": "Trust Deed & Beneficial Ownership Declaration",
                "text": "Declaration of Trust: 100% shares of Altai Resources International BVI held in trust for sole beneficiary Dmitri Volkov.",
            }
        ]
    },

    "orion_defense_exfil_onion": {
        "onion_address": "orionleakarchive99m24z2f3c7k7h9p4q2n6v8w0x2y4z6a8b0c2d4e.onion",
        "service_name": "Orion Strategic Technologies Leaked Cache",
        "category": "INTEL_REPOSITORY",
        "description": "Archived technical manuals and radar schematics leaked from sanctioned defense entity Orion Strategic Technologies.",
        "first_seen": "2022-09-01T08:00:00Z",
        "last_seen": "2025-11-20T12:00:00Z",
        "status": "ACTIVE",
        "mirrors": ["oriondefenseleaks112233445566778899aabbccddeeffgghhiijjkkll.onion"],
        "clearnet_domains": [],
        "associated_entities": ["Orion Strategic Technologies", "OFSI Asset Freeze", "David Marcus"],
        "crypto_addresses": {},
        "contact_identities": ["curator@orionleaks.onion"],
        "pgp_fingerprints": ["8C9D 0E1F 2A3B 4C5D 6E7F  8A9B 0C1D 2E3F 4A5B 6C7D"],
        "server_fingerprint": "nginx/1.22.0",
        "indexed_pages_count": 18,
        "is_malicious_decoy": False,
        "sample_pages": [
            {
                "url": "http://orionleakarchive99m24z2f3c7k7h9p4q2n6v8w0x2y4z6a8b0c2d4e.onion/manifest",
                "title": "Technical Component Manifest",
                "text": "Orion Strategic Technologies radar signal processing DSP units sourced through UAE and Cypriot intermediaries.",
            }
        ]
    },
}
