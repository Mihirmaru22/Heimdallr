"""Heimdallr V5.2: ONION_CAPABILITY_GAP_V2 100-Task Frozen Benchmark Suite.

Constructs 100 independently graded tasks distributed across:
1. GROUP A — SOURCE DISCOVERY (20 tasks): Discovery from indexes, seeds, decoys, multiple sources.
2. GROUP B — ACQUISITION (20 tasks): Retrieval from known .onion URLs (accessible, redirects, retries, 404s, malformed, large, encoding).
3. GROUP C — CRAWLING (15 tasks): Recursive link traversal, cycles, depth limits, page budgets, stopping rules.
4. GROUP D — HANDED-DOCUMENT REASONING (15 tasks): Downstream entity/temporal/contradiction reasoning with handed documents.
5. GROUP E — END-TO-END INVESTIGATION (15 tasks): Multi-specialist chaining (Corporate, Identity, Infra, Sanctions).
6. GROUP F — NEGATIVE, BUDGET & EPISTEMIC (15 tasks): Absence calibration, exhausted budgets, conflicting claims.
"""

from __future__ import annotations

from typing import List
from argus.evals.onion_capability_gap_v2.corpus import (
    CAPABILITY_GAP_V2_CORPUS,
    get_normalized_document_for_task,
)
from argus.evals.onion_capability_gap_v2.models import GapV2Task, GapV2TaskGroup


def build_gap_v2_tasks() -> List[GapV2Task]:
    """Build the official 100-task suite for ONION_CAPABILITY_GAP_V2."""
    tasks: List[GapV2Task] = []

    # =========================================================================
    # GROUP A — SOURCE DISCOVERY (20 Tasks)
    # =========================================================================
    # Tests discovering relevant onion sources from search indexes, seed links, and among decoys
    disc_specs = [
        # (id, title, query, target_onion, entity, expected_entities, is_decoy, is_neg)
        ("GAP2_DISC_01", "Discover ALPHV BlackCat primary leak portal", "What is the primary Tor hidden service address for ALPHV BlackCat data leak portal?", "alphvmmm27yku4xb25v45w3h4vj3lsq4u7z3mefqfx42n3p4a23bfdqd.onion", "ALPHV Group", ["ALPHV Group", "BlackCat"], False, False),
        ("GAP2_DISC_02", "Discover LockBit 3.0 extortion blog among decoys", "Identify the authentic onion address of LockBit 3.0 data publication site, ignoring satirical decoys.", "lockbitapt6vx57t3eeqjofwgcglmutr3a35nygvokja5uuccip4ykyd.onion", "LockBit Supp", ["LockBit Supp", "LockBit 3.0"], False, False),
        ("GAP2_DISC_03", "Discover CL0P syndicate torrent drop service", "Locate the Tor v3 hidden service where CL0P posts corporate archive torrents.", "cl0p52gcvho3aveqmg7fvgarqvd2ek2gahqqqll4qjzn2vdre5ph4xqd.onion", "CL0P Syndicate", ["CL0P Syndicate"], False, False),
        ("GAP2_DISC_04", "Discover Dread darknet forum hidden service", "What is the official Tor onion address for the Dread darknet discussion forum?", "dread462g6f5mtyv5y52m6k7h27qeq4e44qndzfvj52vskb5k57n2zqd.onion", "Dread Forum", ["Dread Forum", "HugBunter"], False, False),
        ("GAP2_DISC_05", "Discover Sandworm C2 relay hidden service", "Find the operational onion descriptor for the GRU Sandworm C2 relay service.", "sandwrm74455c2relay7m24z2f3c7k7h9p4q2n6v8w0x2y4z6a8b0c2d4e.onion", "Sandworm", ["Sandworm", "GRU Unit 74455"], False, False),
        ("GAP2_DISC_06", "Discover Lazarus Group darknet escrow portal", "Identify the cryptocurrency escrow hidden service operated by Lazarus Group.", "lazescrow8934k2m7n9p1q3r5t7v9x1z3b5d7f9h1j3l5n7p9r1t3v5x7z.onion", "Lazarus Group", ["Lazarus Group", "TraderTraitor"], False, False),
        ("GAP2_DISC_07", "Discover SecureDrop whistleblower intake service", "What is the Tor hidden service address for Freedom Press SecureDrop intake?", "securedropwhistle77m24z2f3c7k7h9p4q2n6v8w0x2y4z6a8b0c2d4e.onion", "Freedom Press", ["Freedom Press", "SecureDrop"], False, False),
        ("GAP2_DISC_08", "Discover authentic ALPHV service vs phishing clone", "Identify the authentic ALPHV leak site and reject the clone ending in 'mmnnoo.onion'.", "alphvmmm27yku4xb25v45w3h4vj3lsq4u7z3mefqfx42n3p4a23bfdqd.onion", "ALPHV Group", ["ALPHV Group"], False, False),
        ("GAP2_DISC_09", "Discover Altai Shadow Holding offshore document portal", "Locate the hidden portal hosting Altai Shadow Holding shipping manifests.", "altaishadowportal7m24z2f3c7k7h9p4q2n6v8w0x2y4z6a8b0c2d4e.onion", "Altai Shadow Holding", ["Altai Shadow Holding"], False, False),
        ("GAP2_DISC_10", "Discover Orion Defense telemetry archive site", "Find the Tor hidden service hosting leaked Orion Defense System telemetry.", "orionleakarchive99m24z2f3c7k7h9p4q2n6v8w0x2y4z6a8b0c2d4e.onion", "Orion Defense Systems", ["Orion Defense Systems"], False, False),
        ("GAP2_DISC_11", "Discover authentic LockBit secondary mirror", "Locate the primary active onion address for LockBit ransomware.", "lockbitapt6vx57t3eeqjofwgcglmutr3a35nygvokja5uuccip4ykyd.onion", "LockBit Supp", ["LockBit Supp"], False, False),
        ("GAP2_DISC_12", "Discover hidden service from victim company name", "Search darknet for leak records concerning Apex Technologies compromise.", "alphvmmm27yku4xb25v45w3h4vj3lsq4u7z3mefqfx42n3p4a23bfdqd.onion", "Apex Technologies", ["Apex Technologies Group"], False, False),
        ("GAP2_DISC_13", "Discover MoveIT exploit discussion thread source", "Find darknet forum discussing MoveIT transfer vulnerability exploit chains.", "cl0p52gcvho3aveqmg7fvgarqvd2ek2gahqqqll4qjzn2vdre5ph4xqd.onion", "CL0P Syndicate", ["CL0P Syndicate"], False, False),
        ("GAP2_DISC_14", "Discover onion service among misleading decoy titles", "Identify authentic LockBit portal while filtering out research decoy 'LockBit Official Decoy Blog'.", "lockbitapt6vx57t3eeqjofwgcglmutr3a35nygvokja5uuccip4ykyd.onion", "LockBit Supp", ["LockBit Supp"], True, False),
        ("GAP2_DISC_15", "Discover whistleblowing drop using seed URL query", "Locate whistleblowing intake portal using search term 'Freedom Press submission key'.", "securedropwhistle77m24z2f3c7k7h9p4q2n6v8w0x2y4z6a8b0c2d4e.onion", "SecureDrop", ["SecureDrop"], False, False),
        ("GAP2_DISC_16", "Discover nation-state cyber infrastructure descriptor", "Search Tor directory for GRU Unit 74455 covert relays.", "sandwrm74455c2relay7m24z2f3c7k7h9p4q2n6v8w0x2y4z6a8b0c2d4e.onion", "Sandworm", ["Sandworm"], False, False),
        ("GAP2_DISC_17", "Discover multi-mirror cluster for Dread forum", "Find authenticated onion mirror list for Dread forum discussions.", "dread462g6f5mtyv5y52m6k7h27qeq4e44qndzfvj52vskb5k57n2zqd.onion", "Dread Forum", ["Dread Forum"], False, False),
        ("GAP2_DISC_18", "Discover illicit cryptocurrency mixer service", "Locate Lazarus multi-sig deposit endpoints and escrow service.", "lazescrow8934k2m7n9p1q3r5t7v9x1z3b5d7f9h1j3l5n7p9r1t3v5x7z.onion", "Lazarus Group", ["Lazarus Group"], False, False),
        ("GAP2_DISC_19", "Negative Discovery: Non-existent ransomware syndicate", "Search dark web for onion portal of non-existent entity 'CobaltViper Ransomware Syndicate'.", None, None, [], False, True),
        ("GAP2_DISC_20", "Negative Discovery: Unindexed private hidden service", "Search public darknet index for unindexed cryptographic key 'privkey999999999999.onion'.", None, None, [], False, True),
    ]

    for tid, title, q, target, ent, exp_ents, is_dec, is_neg in disc_specs:
        hdoc = get_normalized_document_for_task(target) if target else None
        tasks.append(GapV2Task(
            task_id=tid,
            group=GapV2TaskGroup.GROUP_A_DISCOVERY,
            title=title,
            query=q,
            target_onion=target,
            target_entity=ent,
            expected_sources=[target] if target else [],
            expected_entities=exp_ents,
            expected_claims=[{"field": "onion_address", "value": target}] if target else [],
            required_evidence_desc="Cryptographic onion descriptor discovered in index",
            handed_document_text=hdoc,
            is_negative=is_neg,
            is_decoy=is_dec,
            expected_epistemic_status="NOT_FOUND" if is_neg else "SUPPORTED",
        ))

    # =========================================================================
    # GROUP B — ACQUISITION (20 Tasks)
    # =========================================================================
    # Tests retrieving content from known .onion URLs under controlled transport conditions
    acq_specs = [
        ("GAP2_ACQ_01", "Acquire normal accessible page from ALPHV", "alphvmmm27yku4xb25v45w3h4vj3lsq4u7z3mefqfx42n3p4a23bfdqd.onion", "ALPHV Group", "NORMAL", False),
        ("GAP2_ACQ_02", "Acquire normal accessible page from LockBit", "lockbitapt6vx57t3eeqjofwgcglmutr3a35nygvokja5uuccip4ykyd.onion", "LockBit Supp", "NORMAL", False),
        ("GAP2_ACQ_03", "Acquire normal page from CL0P", "cl0p52gcvho3aveqmg7fvgarqvd2ek2gahqqqll4qjzn2vdre5ph4xqd.onion", "CL0P Syndicate", "NORMAL", False),
        ("GAP2_ACQ_04", "Acquire normal page from Dread forum", "dread462g6f5mtyv5y52m6k7h27qeq4e44qndzfvj52vskb5k57n2zqd.onion", "Dread Forum", "NORMAL", False),
        ("GAP2_ACQ_05", "Acquire page following HTTP 301 redirect chain", "redirectold112233445566778899aabbccddeeffgghhiijjkkllmmnno.onion", "LockBit Supp", "REDIRECT_301", False),
        ("GAP2_ACQ_06", "Acquire canonical mirror via redirect resolution", "redirectold112233445566778899aabbccddeeffgghhiijjkkllmmnno.onion", "LockBit 3.0", "REDIRECT_301", False),
        ("GAP2_ACQ_07", "Acquire page with transient 503 circuit retry", "retry503service7m24z2f3c7k7h9p4q2n6v8w0x2y4z6a8b0c2d4e.onion", "Apex Technologies", "RETRY_503", False),
        ("GAP2_ACQ_08", "Verify bounded retry on high-load leak service", "retry503service7m24z2f3c7k7h9p4q2n6v8w0x2y4z6a8b0c2d4e.onion", "Apex Technologies Group", "RETRY_503", False),
        ("GAP2_ACQ_09", "Acquire from dead/unavailable service (404/500)", "unavailable404onion7m24z2f3c7k7h9p4q2n6v8w0x2y4z6a8b0c2d4e.onion", None, "UNAVAILABLE", True),
        ("GAP2_ACQ_10", "Classify offline service without false pass", "unavailable404onion7m24z2f3c7k7h9p4q2n6v8w0x2y4z6a8b0c2d4e.onion", None, "UNAVAILABLE", True),
        ("GAP2_ACQ_11", "Acquire malformed HTML payload safely", "malformedhtml7m24z2f3c7k7h9p4q2n6v8w0x2y4z6a8b0c2d4e.onion", "John Doe", "MALFORMED", False),
        ("GAP2_ACQ_12", "Parse corrupted unclosed tags and extract claims", "malformedhtml7m24z2f3c7k7h9p4q2n6v8w0x2y4z6a8b0c2d4e.onion", "John Doe", "MALFORMED", False),
        ("GAP2_ACQ_13", "Acquire large multi-megabyte database export", "largedumpmulti88m24z2f3c7k7h9p4q2n6v8w0x2y4z6a8b0c2d4e.onion", "High-Volume SQL Dump", "LARGE_DOC", False),
        ("GAP2_ACQ_14", "Enforce buffer bound on large document fetch", "largedumpmulti88m24z2f3c7k7h9p4q2n6v8w0x2y4z6a8b0c2d4e.onion", "users", "LARGE_DOC", False),
        ("GAP2_ACQ_15", "Acquire non-UTF8 Cyrillic encoded forum post", "russianforumcyrillic7m24z2f3c7k7h9p4q2n6v8w0x2y4z6a8b0c2d4e.onion", "Apex Technologies", "ENCODING_CYRILLIC", False),
        ("GAP2_ACQ_16", "Decode Windows-1251 darknet thread without crash", "russianforumcyrillic7m24z2f3c7k7h9p4q2n6v8w0x2y4z6a8b0c2d4e.onion", "Apex Technologies", "ENCODING_CYRILLIC", False),
        ("GAP2_ACQ_17", "Repeated idempotent acquisition from ALPHV", "alphvmmm27yku4xb25v45w3h4vj3lsq4u7z3mefqfx42n3p4a23bfdqd.onion", "ALPHV Group", "IDEMPOTENT", False),
        ("GAP2_ACQ_18", "Repeated idempotent acquisition from LockBit", "lockbitapt6vx57t3eeqjofwgcglmutr3a35nygvokja5uuccip4ykyd.onion", "LockBit Supp", "IDEMPOTENT", False),
        ("GAP2_ACQ_19", "Timeout handling on unreachable circuit", "unavailable404onion7m24z2f3c7k7h9p4q2n6v8w0x2y4z6a8b0c2d4e.onion", None, "TIMEOUT", True),
        ("GAP2_ACQ_20", "Content acquisition requiring 2 bounded retries", "retry503service7m24z2f3c7k7h9p4q2n6v8w0x2y4z6a8b0c2d4e.onion", "Financial Audit Records", "RETRY_BOUNDED", False),
    ]

    for tid, title, target, ent, transport_mode, is_neg in acq_specs:
        hdoc = get_normalized_document_for_task(target)
        tasks.append(GapV2Task(
            task_id=tid,
            group=GapV2TaskGroup.GROUP_B_ACQUISITION,
            title=title,
            query=f"Retrieve and parse content from onion service {target}",
            target_onion=target,
            target_entity=ent,
            expected_sources=[target] if target else [],
            expected_entities=[ent] if ent else [],
            expected_claims=[{"field": "status", "value": "OFFLINE" if is_neg else "ACTIVE"}],
            required_evidence_desc=f"Acquired document payload via Tor SOCKS5 ({transport_mode})",
            handed_document_text=hdoc,
            is_negative=is_neg,
            is_redirect=("REDIRECT" in transport_mode),
            is_malformed=("MALFORMED" in transport_mode),
            is_large_document=("LARGE" in transport_mode),
            expected_epistemic_status="NOT_FOUND" if is_neg else "SUPPORTED",
        ))

    # =========================================================================
    # GROUP C — CRAWLING AND RELEVANT EXPANSION (15 Tasks)
    # =========================================================================
    # Tests following links, depth management, cycle detection, budgets, and stopping rules
    crawl_specs = [
        ("GAP2_CRW_01", "Follow relevant internal subpages on ALPHV leak portal", "alphvmmm27yku4xb25v45w3h4vj3lsq4u7z3mefqfx42n3p4a23bfdqd.onion", ["Apex Technologies Group"], False, False, False),
        ("GAP2_CRW_02", "Follow relevant subpages on LockBit extortion blog", "lockbitapt6vx57t3eeqjofwgcglmutr3a35nygvokja5uuccip4ykyd.onion", ["LockBit Supp", "LockBit 3.0"], False, False, False),
        ("GAP2_CRW_03", "Crawl outgoing mirror links to map replica cluster", "alphvmmm27yku4xb25v45w3h4vj3lsq4u7z3mefqfx42n3p4a23bfdqd.onion", ["ALPHV Group"], False, False, False),
        ("GAP2_CRW_04", "Filter irrelevant external clearnet links during crawl", "alphvmmm27yku4xb25v45w3h4vj3lsq4u7z3mefqfx42n3p4a23bfdqd.onion", ["BlackCat"], False, False, False),
        ("GAP2_CRW_05", "Reject social media decoy links during onion traversal", "dread462g6f5mtyv5y52m6k7h27qeq4e44qndzfvj52vskb5k57n2zqd.onion", ["Dread Forum"], False, False, False),
        ("GAP2_CRW_06", "Break circular link loop (A -> B -> A) without infinite loop", "cyclelooplinks7m24z2f3c7k7h9p4q2n6v8w0x2y4z6a8b0c2d4e.onion", ["cyber_ghost"], True, False, False),
        ("GAP2_CRW_07", "Reach target page via cyclic graph traversal", "cyclelooplinks7m24z2f3c7k7h9p4q2n6v8w0x2y4z6a8b0c2d4e.onion", ["cyber_ghost"], True, False, False),
        ("GAP2_CRW_08", "Deduplicate multiple paths leading to same document", "cyclelooplinks7m24z2f3c7k7h9p4q2n6v8w0x2y4z6a8b0c2d4e.onion", ["cyber_ghost"], False, False, False),
        ("GAP2_CRW_09", "Recognize identical page content across mirror URLs", "alphvmmm27yku4xb25v45w3h4vj3lsq4u7z3mefqfx42n3p4a23bfdqd.onion", ["ALPHV Group"], False, False, False),
        ("GAP2_CRW_10", "Enforce max_depth=1 limitation on crawl tree", "deeptreehierarchy7m24z2f3c7k7h9p4q2n6v8w0x2y4z6a8b0c2d4e.onion", ["Level 1 Directory"], False, True, False),
        ("GAP2_CRW_11", "Enforce max_depth=2 boundary on hierarchical directory", "deeptreehierarchy7m24z2f3c7k7h9p4q2n6v8w0x2y4z6a8b0c2d4e.onion", ["Level 2 Directory"], False, True, False),
        ("GAP2_CRW_12", "Comply with page budget limit (max_pages=5)", "lockbitapt6vx57t3eeqjofwgcglmutr3a35nygvokja5uuccip4ykyd.onion", ["LockBit Supp"], False, False, False),
        ("GAP2_CRW_13", "Comply with page budget limit on deep archive", "deeptreehierarchy7m24z2f3c7k7h9p4q2n6v8w0x2y4z6a8b0c2d4e.onion", ["Level 1 Directory"], False, False, False),
        ("GAP2_CRW_14", "Traverse multi-hop path to reach Level 3 target document", "deeptreehierarchy7m24z2f3c7k7h9p4q2n6v8w0x2y4z6a8b0c2d4e.onion", ["Altai Maritime Logistics"], False, False, False),
        ("GAP2_CRW_15", "Stop crawling when target claim is fully satisfied", "deeptreehierarchy7m24z2f3c7k7h9p4q2n6v8w0x2y4z6a8b0c2d4e.onion", ["Altai Maritime Logistics"], False, False, True),
    ]

    for tid, title, target, exp_ents, is_cyc, is_dep, is_stop in crawl_specs:
        hdoc = get_normalized_document_for_task(target)
        tasks.append(GapV2Task(
            task_id=tid,
            group=GapV2TaskGroup.GROUP_C_CRAWLING,
            title=title,
            query=f"Crawl hidden service {target} and extract target entities",
            target_onion=target,
            target_entity=exp_ents[0] if exp_ents else None,
            expected_sources=[target],
            expected_entities=exp_ents,
            expected_claims=[{"field": "crawl_status", "value": "COMPLETED"}],
            required_evidence_desc="Crawled HTML page snapshot and link tree",
            handed_document_text=hdoc,
            is_cycle=is_cyc,
            expected_epistemic_status="SUPPORTED",
        ))

    # =========================================================================
    # GROUP D — HANDED-DOCUMENT REASONING (15 Tasks)
    # =========================================================================
    # Critical test: provides Argus (Config B) with equivalent pre-acquired documents
    # to measure whether reasoning difference disappears when acquisition is removed.
    hdoc_specs = [
        ("GAP2_HDOC_01", "Entity extraction from ALPHV compromise disclosure", "alphv_blackcat", ["Apex Technologies Group Inc", "Delaware"], "Delaware"),
        ("GAP2_HDOC_02", "Entity extraction from LockBit affiliate portal", "lockbit_supp", ["LockBit Supp", "Dmitry Khoroshev"], "Russian Federation"),
        ("GAP2_HDOC_03", "Extract structured Bitcoin ransom address", "alphv_blackcat", ["ALPHV Group"], "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh"),
        ("GAP2_HDOC_04", "Extract structured Monero donation address", "alphv_blackcat", ["BlackCat"], "888tNkZrPN6JsEgekjMnABU4TBzc2Dt29EPAvkFxbANsAnJYPbb3iQ1YBRk1UXcdRsiKc9dhwMVgN5S9cQUiyoogDavup3H"),
        ("GAP2_HDOC_05", "Multi-hop relationship: ALPHV and Noberus malware lineage", "alphv_blackcat", ["ALPHV Group", "Noberus"], "Rust-based ransomware"),
        ("GAP2_HDOC_06", "Multi-hop relationship: Altai Shadow Holding and maritime link", "altai_shadow_holding_onion", ["Altai Shadow Holding", "Belize"], "Maritime logistics"),
        ("GAP2_HDOC_07", "Detect contradiction: Seizure banner vs claimed active operation", "alphv_blackcat", ["Federal Bureau of Investigation"], "SEIZED"),
        ("GAP2_HDOC_08", "Detect contradiction: Authentic mirror vs phishing clone", "alphv_phishing_clone", ["ALPHV Group"], "PHISHING_CLONE"),
        ("GAP2_HDOC_09", "Temporal reasoning: Establish ALPHV first_seen date", "alphv_blackcat", ["ALPHV Group"], "2021-11-15T08:00:00Z"),
        ("GAP2_HDOC_10", "Temporal reasoning: Establish LockBit last_seen date", "lockbit_supp", ["LockBit Supp"], "2024-02-20T10:00:00Z"),
        ("GAP2_HDOC_11", "Identify missing PGP key in anonymous paste document", "cl0p_torrent_drop", ["CL0P Syndicate"], "MISSING_PGP"),
        ("GAP2_HDOC_12", "Recognize missing corporate officer in offshore leak", "altai_shadow_holding_onion", ["Altai Shadow Holding"], "UNRESOLVED_OFFICER"),
        ("GAP2_HDOC_13", "Evidence grounding: Ground ransom demand in source HTML snippet", "alphv_blackcat", ["Apex Technologies Group"], "450 GB source code"),
        ("GAP2_HDOC_14", "Reject unsupported claim: LockBit claimed NASDAQ hack without proof", "lockbit_supp", ["LockBit Supp"], "UNSUPPORTED"),
        ("GAP2_HDOC_15", "Reject unsupported claim: Fictitious Russian military contract", "sandworm_telecom_c2", ["Sandworm"], "UNSUPPORTED"),
    ]

    for tid, title, corpus_key, exp_ents, claim_val in hdoc_specs:
        s = CAPABILITY_GAP_V2_CORPUS.get(corpus_key, {})
        target = s.get("onion_address")
        hdoc = get_normalized_document_for_task(target) if target else None
        is_cont = "contradiction" in title.lower()
        is_temp = "temporal" in title.lower()
        is_unsup = ("unsupported" in title.lower() or "missing" in title.lower())

        tasks.append(GapV2Task(
            task_id=tid,
            group=GapV2TaskGroup.GROUP_D_HANDED_REASONING,
            title=title,
            query=f"Analyze provided document for {s.get('service_name')} to verify claims regarding {claim_val}",
            target_onion=target,
            target_entity=exp_ents[0] if exp_ents else None,
            expected_sources=[target] if target else [],
            expected_entities=exp_ents,
            expected_claims=[{"field": "claim_value", "value": claim_val}],
            required_evidence_desc="Grounded normalized evidence text snippet",
            handed_document_text=hdoc,
            is_multihop=("multi-hop" in title.lower()),
            expected_epistemic_status="CONTRADICTED" if is_cont else ("UNKNOWN" if is_unsup else "SUPPORTED"),
        ))

    # =========================================================================
    # GROUP E — END-TO-END INVESTIGATION (15 Tasks)
    # =========================================================================
    # Full multi-specialist pipeline: Onion acquisition + Corporate, Identity, Infra, Sanctions
    e2e_specs = [
        ("GAP2_E2E_01", "Corporate cross-check: Link ALPHV victim to Delaware corporate registry", "alphv_blackcat", ["Apex Technologies Group Inc"], ["onion_intelligence", "corporate_registry_intelligence"]),
        ("GAP2_E2E_02", "Corporate cross-check: Correlate LockBit corporate victim with UK filings", "lockbit_supp", ["LockBit Supp"], ["onion_intelligence", "corporate_registry_intelligence"]),
        ("GAP2_E2E_03", "Corporate cross-check: Verify Altai Shadow Holding offshore parent in Belize", "altai_shadow_holding_onion", ["Altai Shadow Holding"], ["onion_intelligence", "corporate_registry_intelligence"]),
        ("GAP2_E2E_04", "Corporate cross-check: Correlate Orion Defense exfiltration with clearnet SEC filings", "orion_defense_exfil_onion", ["Orion Defense Systems"], ["onion_intelligence", "corporate_registry_intelligence"]),
        ("GAP2_E2E_05", "Identity canonicalization: Correlate 'LockBitSupp' to real-world threat actor identity", "lockbit_supp", ["LockBit Supp", "Dmitry Khoroshev"], ["onion_intelligence", "identity_resolution"]),
        ("GAP2_E2E_06", "Identity canonicalization: Resolve Dread forum administrator handle HugBunter", "dread_forum", ["HugBunter"], ["onion_intelligence", "identity_resolution"]),
        ("GAP2_E2E_07", "Identity canonicalization: Correlate BlackCat ransomware operator to Noberus author", "alphv_blackcat", ["ALPHV Group", "Noberus"], ["onion_intelligence", "identity_resolution"]),
        ("GAP2_E2E_08", "Identity canonicalization: Correlate Sandworm C2 operator to GRU Unit 74455 officers", "sandworm_telecom_c2", ["GRU Unit 74455"], ["onion_intelligence", "identity_resolution"]),
        ("GAP2_E2E_09", "Infrastructure correlation: Map Sandworm C2 onion service to clearnet ASN / IP", "sandworm_telecom_c2", ["Sandworm C2 Relay"], ["onion_intelligence", "infrastructure_discovery"]),
        ("GAP2_E2E_10", "Infrastructure correlation: Trace server nginx fingerprint across LockBit mirror farm", "lockbit_supp", ["nginx/1.18.0"], ["onion_intelligence", "infrastructure_discovery"]),
        ("GAP2_E2E_11", "Infrastructure correlation: Correlate clearnet mirror domains to Tor onion service", "alphv_blackcat", ["blackcat-leaks.info"], ["onion_intelligence", "infrastructure_discovery"]),
        ("GAP2_E2E_12", "Sanctions screening: Screen ALPHV Bitcoin ransom wallets against OFAC SDN list", "alphv_blackcat", ["bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh"], ["onion_intelligence", "sanctions_and_beneficial_ownership"]),
        ("GAP2_E2E_13", "Sanctions screening: Cross-reference Lazarus escrow Monero address with OFAC alerts", "lazarus_crypto_escrow", ["Lazarus Group"], ["onion_intelligence", "sanctions_and_beneficial_ownership"]),
        ("GAP2_E2E_14", "Sanctions screening: Check Dmitry Khoroshev OFAC sanctions and reward designation", "lockbit_supp", ["Dmitry Khoroshev"], ["onion_intelligence", "sanctions_and_beneficial_ownership"]),
        ("GAP2_E2E_15", "Sanctions screening: Beneficial ownership screening of Altai Maritime Logistics", "altai_shadow_holding_onion", ["Altai Maritime Logistics"], ["onion_intelligence", "sanctions_and_beneficial_ownership"]),
    ]

    for tid, title, corpus_key, exp_ents, req_specs in e2e_specs:
        s = CAPABILITY_GAP_V2_CORPUS.get(corpus_key, {})
        target = s.get("onion_address")
        hdoc = get_normalized_document_for_task(target) if target else None

        tasks.append(GapV2Task(
            task_id=tid,
            group=GapV2TaskGroup.GROUP_E_INVESTIGATION,
            title=title,
            query=f"Conduct multi-specialist investigation on {s.get('service_name')} to verify corporate, identity, infra, or sanctions links",
            target_onion=target,
            target_entity=exp_ents[0] if exp_ents else None,
            expected_sources=[target] if target else [],
            expected_entities=exp_ents,
            expected_claims=[{"field": "investigation_verdict", "value": "VERIFIED"}],
            required_evidence_desc="Corroborated evidence spanning Tor hidden service and clearnet specialist registries",
            handed_document_text=hdoc,
            required_specialists=req_specs,
            is_multihop=True,
            expected_epistemic_status="SUPPORTED",
        ))

    # =========================================================================
    # GROUP F — NEGATIVE, BUDGET, AND EPISTEMIC CASES (15 Tasks)
    # =========================================================================
    # Calibrated absence, budget ceilings, and epistemic precision
    neg_specs = [
        ("GAP2_NEG_01", "Absence: Non-existent ransomware group 'ViperShadow'", None, "NOT_FOUND", False),
        ("GAP2_NEG_02", "Absence: Non-existent darknet forum 'SilkWay Reloaded'", None, "NOT_FOUND", False),
        ("GAP2_NEG_03", "Absence: Target corporate database not breached on dark web", None, "NOT_FOUND", False),
        ("GAP2_NEG_04", "Inaccessible: Hidden service offline with zero reachable descriptors", "unavailable404onion7m24z2f3c7k7h9p4q2n6v8w0x2y4z6a8b0c2d4e.onion", "NOT_FOUND", False),
        ("GAP2_NEG_05", "Inaccessible: Seized forum displaying permanent law enforcement banner", "unavailable404onion7m24z2f3c7k7h9p4q2n6v8w0x2y4z6a8b0c2d4e.onion", "NOT_FOUND", False),
        ("GAP2_NEG_06", "Insufficient evidence: Unsubstantiated leak rumor on paste site", "malformedhtml7m24z2f3c7k7h9p4q2n6v8w0x2y4z6a8b0c2d4e.onion", "UNKNOWN", False),
        ("GAP2_NEG_07", "Insufficient evidence: Ambiguous cryptocurrency payment transaction", "retry503service7m24z2f3c7k7h9p4q2n6v8w0x2y4z6a8b0c2d4e.onion", "UNKNOWN", False),
        ("GAP2_NEG_08", "Conflicting sources: Disputed ransomware victim data ownership", "alphv_blackcat", "CONTRADICTED", False),
        ("GAP2_NEG_09", "Conflicting sources: Phishing mirror alleging authentic ownership", "alphv_phishing_clone", "CONTRADICTED", False),
        ("GAP2_NEG_10", "Stale content: Historical seized market claiming current active trade", "unavailable404onion7m24z2f3c7k7h9p4q2n6v8w0x2y4z6a8b0c2d4e.onion", "CONTRADICTED", False),
        ("GAP2_NEG_11", "Stale content: Expired negotiation session countdown timer", "lockbit_supp", "CONTRADICTED", False),
        ("GAP2_NEG_12", "Syndicated content: Deduplicate mirror clone without inflating confidence", "alphv_blackcat", "SUPPORTED", False),
        ("GAP2_NEG_13", "Budget exhausted: Terminate gracefully when search query budget is depleted", None, "UNKNOWN", True),
        ("GAP2_NEG_14", "Budget exhausted: Terminate gracefully when crawl depth ceiling is reached", "deeptreehierarchy7m24z2f3c7k7h9p4q2n6v8w0x2y4z6a8b0c2d4e.onion", "UNKNOWN", True),
        ("GAP2_NEG_15", "Tempting unsupported conclusion: Reject false claim that Tor implies guilt", "alphv_blackcat", "UNKNOWN", False),
    ]

    for tid, title, target, ep_status, is_budget in neg_specs:
        hdoc = get_normalized_document_for_task(target) if target else None
        tasks.append(GapV2Task(
            task_id=tid,
            group=GapV2TaskGroup.GROUP_F_NEGATIVE_EPISTEMIC,
            title=title,
            query=f"Evaluate darknet hypothesis: {title}",
            target_onion=target,
            target_entity=None,
            expected_sources=[] if ep_status in ("NOT_FOUND", "UNKNOWN") else ([target] if target else []),
            expected_entities=[],
            expected_claims=[],
            required_evidence_desc="Absence or calibrated epistemic status assertion",
            handed_document_text=hdoc,
            is_negative=True,
            expected_epistemic_status=ep_status,
        ))

    return tasks
