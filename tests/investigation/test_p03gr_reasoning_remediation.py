"""Tests for Milestone P0.3-GR: Generalization Reasoning Remediation.

Exercises:
1. Cross-document contradiction detection (numerical, categorical, unit handling, temporal succession).
2. Entity-scoped negative verification (parent vs child/department, explicit negative registry, absent relationships).
3. Epistemic abstention (preliminary findings, unverified rumors, proprietary trade secrets).
4. End-to-end investigation engine epistemic status synthesis.
"""

from __future__ import annotations

import pytest

from argus.investigation.contradiction_resolver import (
    ComparableClaim,
    ContradictionResolver,
    DiscrepancyType,
    EntityScopeVerifier,
    EpistemicSufficiencyEvaluator,
)
from argus.investigation.orchestrator import InvestigationEngine
from argus.investigation.question import QuestionStatus


# =============================================================================
# Phase 2: Contradiction Resolution Tests
# =============================================================================

def test_conflicting_numerical_values_detected():
    """Verify that numerical conflicts between independent sources are detected beyond tolerance."""
    resolver = ContradictionResolver()
    docs = [
        {
            "text": "The manufacturer press release asserts the heavy articulated Titan-6 robot achieves a maximum payload capacity of 600 kg for automotive assembly.",
            "url": "https://vendor-pr.example.com/titan-6",
            "source_type": "press_release",
            "evidence_id": "ev_pr_01",
        },
        {
            "text": "Official CE Machinery Directive Certificate: Type-examination confirms maximum certified rated payload capacity under ISO 10218-1 is strictly 450 kg.",
            "url": "https://tuv-cert.example.org/iso-titan6",
            "source_type": "official_certificate",
            "evidence_id": "ev_tuv_02",
        },
    ]
    claims = resolver.extract_comparable_claims(docs, target_subject="Titan-6")
    contras = resolver.detect_contradictions(claims)

    assert len(contras) >= 1
    c = contras[0]
    assert c.property_dim == "payload"
    assert c.discrepancy_type == DiscrepancyType.NUMERICAL_DISCREPANCY
    assert "600" in str(c.value_a) or "600" in str(c.value_b)
    assert "450" in str(c.value_a) or "450" in str(c.value_b)


def test_solar_efficiency_discrepancy():
    """Verify that certified lab test vs marketing claim triggers numerical contradiction."""
    resolver = ContradictionResolver()
    docs = [
        {
            "text": "Quasar Photovoltaics promotional brochure announces world record tandem solar cell efficiency exceeding 35.2% on experimental samples.",
            "url": "https://quasar-pv.example.de/brochure",
            "source_type": "promotional_brochure",
        },
        {
            "text": "Fraunhofer ISE Certified Test Report: Measured steady-state conversion efficiency of Quasar tandem cells is strictly 31.4% Efficiency under 1-sun conditions.",
            "url": "https://fraunhofer.example.de/cert",
            "source_type": "laboratory_certification",
        },
    ]
    claims = resolver.extract_comparable_claims(docs, target_subject="Quasar Photovoltaics")
    contras = resolver.detect_contradictions(claims)

    assert len(contras) >= 1
    assert contras[0].property_dim == "efficiency"
    assert contras[0].discrepancy_type == DiscrepancyType.NUMERICAL_DISCREPANCY


def test_categorical_mutual_exclusivity_battery_chemistry():
    """Verify that mutually exclusive categorical values (Sodium-Ion vs LFP) trigger contradiction."""
    resolver = ContradictionResolver()
    docs = [
        {
            "text": "Clean Energy Blog writes that Zephyr Microgrid chose conventional Lithium Iron Phosphate (LFP) battery chemistry for Gotland Island.",
            "url": "https://cleanenergy.example.org/zephyr",
            "source_type": "blog_post",
        },
        {
            "text": "Official Utility Dossier: Gotland facility for Zephyr Microgrid employs non-lithium Sodium-Ion battery chemistry with hard carbon anodes.",
            "url": "https://gotland-energy.example.se/filing/zephyr-microgrid",
            "source_type": "utility_dossier",
        },
    ]
    claims = resolver.extract_comparable_claims(docs, target_subject="Zephyr Microgrid")
    contras = resolver.detect_contradictions(claims)

    assert len(contras) >= 1
    assert contras[0].property_dim == "battery_chemistry"
    assert contras[0].discrepancy_type == DiscrepancyType.CATEGORICAL_DISPUTE


def test_temporal_succession_not_flagged_as_contradiction():
    """Verify that temporal rebranding (Twitter -> X Corp) is recognized as succession, not contradiction."""
    resolver = ContradictionResolver()
    docs = [
        {
            "text": "Twitter operated as a leading microblogging service founded in 2006.",
            "url": "https://history.example.com/twitter",
        },
        {
            "text": "In 2023, the platform was officially rebranded to X Corp following its acquisition by Elon Musk.",
            "url": "https://news.example.com/x-rebrand",
        },
    ]
    claims = resolver.extract_comparable_claims(docs, target_subject="Twitter")
    contras = resolver.detect_contradictions(claims)

    assert len(contras) == 0


def test_same_domain_syndicated_duplicate_not_contradiction():
    """Verify that two identical syndicated articles from the same domain do not create conflicts."""
    resolver = ContradictionResolver()
    docs = [
        {
            "text": "Kuka Titan-6 boasts 600 kg payload capacity.",
            "url": "https://newswire.com/article1",
        },
        {
            "text": "Kuka Titan-6 boasts 600 kg payload capacity.",
            "url": "https://newswire.com/article2",
        },
    ]
    claims = resolver.extract_comparable_claims(docs, target_subject="Kuka")
    contras = resolver.detect_contradictions(claims)
    assert len(contras) == 0


# =============================================================================
# Phase 3: Entity-Scoped Negative Verification Tests
# =============================================================================

def test_parent_company_does_not_imply_nonexistent_department():
    """Verify that parent existence does not substantiate a nonexistent department."""
    docs = [
        {
            "text": "Commercial Register of Munich: Kuka Dynamics AG was established in Munich specializing in industrial robotics.",
            "url": "https://register.de/kuka",
        },
        {
            "text": "Official Registry: Exhaustive search of commercial registers confirms Kuka Dynamics Subterranean Mining Division does not exist. Kuka Dynamics Department of Anti-Gravity Propulsion does not exist.",
            "url": "https://register.de/negative-inquiry",
        },
    ]
    target_dept = "Kuka Dynamics AG Department of Anti-Gravity"
    is_grounded, is_absent, rationale = EntityScopeVerifier.verify_entity_presence(target_dept, docs)

    assert not is_grounded
    assert is_absent
    assert "explicitly confirmed negative finding" in rationale


def test_fictitious_entity_absence_detected():
    """Verify that a fictitious entity absent from domain evidence is flagged as absent."""
    docs = [
        {
            "text": "Zephyr Microgrid Systems deployed a 50 MWh facility on Gotland Island.",
            "url": "https://zephyr.example.com/press",
        }
    ]
    target_fictitious = "Zephyr Lunar Technologies LLC"
    is_grounded, is_absent, rationale = EntityScopeVerifier.verify_entity_presence(target_fictitious, docs)

    assert not is_grounded
    assert not is_absent  # not explicitly disavowed, but absent
    assert "absent from all retrieved evidence" in rationale


# =============================================================================
# Phase 4: Epistemic Abstention Tests
# =============================================================================

def test_preliminary_inconclusive_findings_abstain():
    """Verify that preliminary or unconfirmed findings are rejected from SUPPORTED status."""
    docs = [
        {
            "text": "Preliminary physics notes: A single four-probe resistivity drop was observed at 294 K. However, zero resistance could not be sustained and independent reproduction failed. Evidence for room-temperature superconductivity is inconclusive.",
            "url": "https://arxiv.org/abs/test",
        }
    ]
    is_sufficient, reason = EpistemicSufficiencyEvaluator.evaluate_sufficiency(
        docs, objective="Verify whether room-temperature superconductivity is proven."
    )

    assert not is_sufficient
    assert "inconclusive or preliminary" in reason


def test_unverified_forum_rumor_abstains():
    """Verify that unverified single-source forum rumors cause epistemic abstention."""
    docs = [
        {
            "text": "Unconfirmed forum chatter mentions an employee was questioned. No formal report has been made and details remain completely unverified.",
            "url": "https://rumor.example.com/post",
        }
    ]
    is_sufficient, reason = EpistemicSufficiencyEvaluator.evaluate_sufficiency(
        docs, objective="Investigate internal cybersecurity compromise."
    )

    assert not is_sufficient
    assert "inconclusive or preliminary" in reason


def test_proprietary_trade_secret_query_abstains():
    """Verify that queries for proprietary unreleased trade secrets abstain with insufficient evidence."""
    docs = [
        {
            "text": "Google operates Tensor Processing Unit v5p pods for large-scale model training.",
            "url": "https://cloud.google.com/tpu",
        }
    ]
    is_sufficient, reason = EpistemicSufficiencyEvaluator.evaluate_sufficiency(
        docs, objective="Investigate Gemini training cluster internal topology details and interconnect layout."
    )

    assert not is_sufficient
    assert "non-public or proprietary" in reason


# =============================================================================
# End-to-End Orchestrator Epistemic Status Synthesis Tests
# =============================================================================

def test_orchestrator_contradiction_synthesis():
    """Verify that an investigation containing unresolved contradictions synthesizes CONTRADICTED."""
    engine = InvestigationEngine()
    state = engine.start_investigation(
        objective="Examine competing claims on Titan-6 robot payload capacity.",
        contract={"target_entities": ["Titan-6"]},
    )
    state.contradictions.append({
        "topic": "Conflicting payload accounts",
        "claim_a": "600 kg payload",
        "claim_b": "450 kg payload",
        "status": "UNRESOLVED_CONTRADICTION",
    })
    status = engine.synthesize_epistemic_status(state)
    assert status == "CONTRADICTED"


def test_orchestrator_negative_finding_synthesis():
    """Verify that an investigation targeting a nonexistent department synthesizes NOT_FOUND."""
    engine = InvestigationEngine()
    state = engine.start_investigation(
        objective="Verify whether Kuka Dynamics operates a Department of Anti-Gravity Propulsion.",
        contract={"target_entities": ["Kuka Dynamics AG Department of Anti-Gravity"]},
    )
    # Simulate question resolved as NOT_FOUND
    for q_id, q in state.questions.items():
        q["status"] = QuestionStatus.NOT_FOUND.value
    status = engine.synthesize_epistemic_status(state)
    assert status == "NOT_FOUND"


def test_orchestrator_insufficient_evidence_synthesis():
    """Verify that an investigation with insufficient evidence synthesizes INSUFFICIENT_EVIDENCE."""
    engine = InvestigationEngine()
    state = engine.start_investigation(
        objective="Investigate unverified preliminary room-temperature superconductivity claims.",
        contract={"target_entities": ["Room-Temperature Superconductor"]},
    )
    # Simulate critical question resolved as INSUFFICIENT_EVIDENCE
    for q_id, q in state.questions.items():
        q["status"] = QuestionStatus.INSUFFICIENT_EVIDENCE.value
    status = engine.synthesize_epistemic_status(state)
    assert status == "INSUFFICIENT_EVIDENCE"


# =============================================================================
# General-Purpose Contradiction Precision Regression Suite
# =============================================================================

def test_different_time_periods_temporal_succession_not_contradicted():
    """Verify that temporal succession across distinct years is not treated as a contradiction."""
    resolver = ContradictionResolver()
    docs = [
        {
            "text": "In 2021, Alice Vance was appointed CEO of Quantex Dynamics following seed capitalization.",
            "url": "https://news.example.com/alice-ceo-2021",
            "source_type": "press_release",
        },
        {
            "text": "In 2024, Robert Martinez was appointed CEO of Quantex Dynamics after Vance stepped down.",
            "url": "https://industry-times.example.com/martinez-ceo-2024",
            "source_type": "press_release",
        },
    ]
    claims = resolver.extract_comparable_claims(docs, target_subject="Quantex Dynamics")
    contras = resolver.detect_contradictions(claims)
    assert len(contras) == 0, f"Expected 0 contradictions for temporal succession, found: {contras}"


def test_different_units_equivalent_values_not_contradicted():
    """Verify that equivalent values across different units (kg vs tons, ms vs s) do not contradict."""
    resolver = ContradictionResolver()
    # Test mass: 5000 kg vs 5 metric tons
    docs_mass = [
        {
            "text": "Factory datasheet: The Atlas Gantry Crane delivers a rated maximum payload of 5000 kg under normal hoist configuration.",
            "url": "https://atlas-crane.example.com/datasheet",
            "source_type": "official_certificate",
        },
        {
            "text": "Industrial Heavy Machinery Review: The Atlas Gantry Crane is certified to safely hoist 5 metric tons of cargo.",
            "url": "https://heavy-machinery.example.com/atlas-crane",
            "source_type": "trade_magazine",
        },
    ]
    claims_mass = resolver.extract_comparable_claims(docs_mass, target_subject="Atlas Gantry Crane")
    contras_mass = resolver.detect_contradictions(claims_mass)
    assert len(contras_mass) == 0, f"Equivalent mass in kg and tons should not contradict: {contras_mass}"

    # Test time: 120 ms vs 0.12 s
    docs_time = [
        {
            "text": "Telecommunications lab report: Edge router switching latency was measured at 120 ms under heavy burst traffic.",
            "url": "https://router-test.example.org/latency-ms",
            "source_type": "laboratory_certification",
        },
        {
            "text": "Network engineering whitepaper: Benchmark evaluation confirms mean edge router switching latency is 0.12 s across all tests.",
            "url": "https://network-whitepapers.example.org/router-sec",
            "source_type": "trade_magazine",
        },
    ]
    claims_time = resolver.extract_comparable_claims(docs_time, target_subject="Edge router")
    contras_time = resolver.detect_contradictions(claims_time)
    assert len(contras_time) == 0, f"Equivalent latency in ms and s should not contradict: {contras_time}"


def test_different_units_divergent_values_contradicted():
    """Verify that genuinely conflicting numbers across different units are detected."""
    resolver = ContradictionResolver()
    # 5000 kg vs 2 metric tons (5000 kg vs 2000 kg = 60% discrepancy)
    docs = [
        {
            "text": "Engineering certificate: The Heavy Transporter payload capacity is rated strictly at 5000 kg under axle limits.",
            "url": "https://cert.example.org/heavy-transporter-5000kg",
            "source_type": "official_certificate",
        },
        {
            "text": "Trade article: Transporter logistics review states maximum payload capacity is only 2 metric tons for municipal routes.",
            "url": "https://trade.example.org/heavy-transporter-2t",
            "source_type": "trade_magazine",
        },
    ]
    claims = resolver.extract_comparable_claims(docs, target_subject="Heavy Transporter")
    contras = resolver.detect_contradictions(claims)
    assert len(contras) >= 1, "Conflicting mass values (5000 kg vs 2 t) must trigger a numerical contradiction"
    assert contras[0].property_dim == "payload"


def test_different_operational_conditions_not_contradicted():
    """Verify that measurements under distinct operating conditions (sea-level vs vacuum, peak vs continuous) do not contradict."""
    resolver = ContradictionResolver()
    # Sea-level vs Vacuum thrust
    docs_thrust = [
        {
            "text": "Static test stand results: The Aether-1 rocket engine generates 85 kN sea-level thrust during ground firing.",
            "url": "https://aether-propulsion.example.com/sea-level",
            "source_type": "laboratory_certification",
        },
        {
            "text": "High-altitude chamber simulation: The Aether-1 rocket engine delivers 110 kN vacuum thrust in upper stage operation.",
            "url": "https://aether-propulsion.example.com/vacuum",
            "source_type": "laboratory_certification",
        },
    ]
    claims_thrust = resolver.extract_comparable_claims(docs_thrust, target_subject="Aether-1")
    contras_thrust = resolver.detect_contradictions(claims_thrust)
    assert len(contras_thrust) == 0, f"Distinct operational conditions (sea-level vs vacuum) should not contradict: {contras_thrust}"

    # Peak vs Continuous efficiency
    docs_eff = [
        {
            "text": "Power electronics test: The SolarMax inverter achieves 99.2% peak conversion efficiency under optimal irradiance.",
            "url": "https://solarmax.example.com/peak",
            "source_type": "trade_magazine",
        },
        {
            "text": "Continuous thermal run: The SolarMax inverter maintains 96.5% continuous steady-state conversion efficiency under full thermal load.",
            "url": "https://solarmax.example.com/continuous",
            "source_type": "laboratory_certification",
        },
    ]
    claims_eff = resolver.extract_comparable_claims(docs_eff, target_subject="SolarMax")
    contras_eff = resolver.detect_contradictions(claims_eff)
    assert len(contras_eff) == 0, f"Peak vs continuous steady-state efficiency should not contradict: {contras_eff}"


def test_identical_conditions_divergent_metrics_contradicted():
    """Verify that genuinely incompatible claims under identical conditions trigger contradiction."""
    resolver = ContradictionResolver()
    docs = [
        {
            "text": "Vendor Press Release: Static firing confirms the Phoenix-1 engine achieved 120 kN sea-level thrust on the test stand.",
            "url": "https://vendor.example.com/phoenix-120kn",
            "source_type": "press_release",
        },
        {
            "text": "Independent ESA Audit: Validated load-cell telemetry confirms Phoenix-1 delivers strictly 85 kN sea-level thrust under standard atmosphere.",
            "url": "https://esa.int/audits/phoenix-85kn",
            "source_type": "laboratory_certification",
        },
    ]
    claims = resolver.extract_comparable_claims(docs, target_subject="Phoenix-1")
    contras = resolver.detect_contradictions(claims)
    assert len(contras) >= 1
    assert contras[0].property_dim == "thrust"
    assert "85" in str(contras[0].value_a) or "85" in str(contras[0].value_b)
    assert "120" in str(contras[0].value_a) or "120" in str(contras[0].value_b)


def test_different_entity_scopes_not_contradicted():
    """Verify that different models or distinct entities do not collide or trigger false contradictions."""
    resolver = ContradictionResolver()
    docs = [
        {
            "text": "Robotics catalog: The Titan-6 articulated arm features a certified payload capacity of 450 kg for standard cells.",
            "url": "https://robotics.example.com/titan-6",
            "source_type": "official_certificate",
        },
        {
            "text": "Robotics catalog: The heavy-duty Titan-8 articulated arm features a certified payload capacity of 900 kg for foundry work.",
            "url": "https://robotics.example.com/titan-8",
            "source_type": "official_certificate",
        },
    ]
    # Querying Titan-6 specifically should only extract claims for Titan-6
    claims_6 = resolver.extract_comparable_claims(docs, target_subject="Titan-6")
    contras_6 = resolver.detect_contradictions(claims_6)
    assert len(contras_6) == 0, f"Titan-6 query should not collide with Titan-8: {contras_6}"
    assert len(claims_6) == 1
    assert "450" in claims_6[0].raw_text


def test_syndicated_wire_mirrors_not_flagged_as_conflicting():
    """Verify that identical syndicated wire reports on different domains are not treated as independent conflicting sources."""
    resolver = ContradictionResolver()
    verbatim_text = "Associated Press: Energy regulators approved the NordLink interconnector project with an initial transmission capacity of 1400 MW."
    docs = [
        {
            "text": verbatim_text,
            "url": "https://news-mirror-a.example.com/ap-nordlink",
            "source_type": "news",
        },
        {
            "text": verbatim_text,
            "url": "https://news-mirror-b.example.org/nordlink-dispatch",
            "source_type": "news",
        },
    ]
    claims = resolver.extract_comparable_claims(docs, target_subject="NordLink")
    contras = resolver.detect_contradictions(claims)
    assert len(contras) == 0, f"Syndicated wire mirrors should not trigger a contradiction: {contras}"


# =============================================================================
# Semantic Verification Weakness Remediation Tests
# =============================================================================

def test_unsupported_hedged_claim_not_marked_supported():
    """Verify that claims with epistemic hedging (alleged, preliminary, unconfirmed) are NOT marked SUPPORTED."""
    engine = InvestigationEngine()
    state = engine.start_investigation(
        objective="Investigate alleged superconducting properties of LK-99",
        contract={"target_entities": ["LK-99"]},
    )
    docs = [
        {
            "evidence_id": "ev_hedged_01",
            "url": "https://preprint.example.org/lk99-hedged",
            "source_type": "scientific_preprint",
            "title": "Preliminary LK-99 Report",
            "text": "Preliminary laboratory tests suggest LK-99 exhibits alleged room-temperature superconductivity, though findings remain unconfirmed.",
        }
    ]
    engine._apply_observation(state, action=None, observation={"documents": docs, "combined_text": docs[0]["text"]})

    # Claims extracted for LK-99 must not be SUPPORTED
    lk99_claims = [c for c in state.claims if c.get("subject") == "LK-99"]
    assert len(lk99_claims) >= 1
    for c in lk99_claims:
        assert c.get("status") != "SUPPORTED", f"Hedged claim must NOT be marked SUPPORTED: {c}"
        assert c.get("status") in ("INSUFFICIENT_EVIDENCE", "UNVERIFIED")

    # Epistemic status of investigation should be INSUFFICIENT_EVIDENCE, not SUPPORTED
    status = engine.synthesize_epistemic_status(state)
    assert status == "INSUFFICIENT_EVIDENCE"


def test_refuted_contradictory_claim_not_marked_supported():
    """Verify that claims with explicit refutation or disproof are marked CONTRADICTED, never SUPPORTED."""
    engine = InvestigationEngine()
    state = engine.start_investigation(
        objective="Determine whether LK-99 superconductivity was verified",
        contract={"target_entities": ["LK-99"]},
    )
    docs = [
        {
            "evidence_id": "ev_refuted_01",
            "url": "https://journal.example.org/lk99-refuted",
            "source_type": "peer_reviewed_journal",
            "title": "LK-99 Replication Assessment",
            "text": "Independent replication studies refuted and disproved claims that LK-99 operates as a superconductor at ambient pressure.",
        }
    ]
    engine._apply_observation(state, action=None, observation={"documents": docs, "combined_text": docs[0]["text"]})

    lk99_claims = [c for c in state.claims if c.get("subject") == "LK-99"]
    assert len(lk99_claims) >= 1
    for c in lk99_claims:
        assert c.get("status") != "SUPPORTED", f"Refuted claim must NOT be marked SUPPORTED: {c}"
        assert c.get("status") in ("CONTRADICTED", "INSUFFICIENT_EVIDENCE")


def test_evaluator_rejects_unsupported_claim_despite_long_passage():
    """Verify that GeneralizationV2Evaluator rejects an unsupported claim even if evidence text is > 100 characters."""
    from argus.investigation.benchmark.v2.evaluator import GeneralizationV2Evaluator
    from argus.investigation.benchmark.tasks import (
        InvestigationCategory,
        InvestigationDifficulty,
        InvestigationTask,
    )
    from argus.investigation.state import InvestigationState

    evaluator = GeneralizationV2Evaluator()
    task = InvestigationTask(
        task_id="test_task_unsupported_gate",
        title="Test Unsupported Gate",
        objective="Verify whether Apex Aerospace launched a lunar probe in 2024",
        category=InvestigationCategory.ORGANIZATIONAL_CORPORATE,
        difficulty=InvestigationDifficulty.HARD,
        expected_epistemic_status="NOT_FOUND",
        expected_entities=["Apex Aerospace"],
    )

    state = InvestigationState(investigation_id="test_inv_01", objective=task.objective)
    # Long evidence passage (> 200 chars) discussing completely unrelated topics
    long_unrelated_passage = (
        "The municipality of Gothenburg completed construction of the new urban tramway extension in December 2023. "
        "The project encompassed twelve kilometers of modernized track and seven upgraded transit stations with "
        "automated signaling systems and zero emissions rolling stock."
    )
    state.evidence = [
        {"evidence_id": "ev_unrelated_long", "url": "https://transit.example.se", "text_content": long_unrelated_passage}
    ]
    # Unsupported claim citing the long passage
    state.claims = [
        {
            "claim_id": "c1",
            "subject": "Apex Aerospace",
            "predicate": "lunar_mission",
            "object": "Apex Aerospace launched a lunar probe in 2024",
            "status": "SUPPORTED",
            "evidence_id": "ev_unrelated_long",
        }
    ]

    res = evaluator.evaluate_single_task(task, state=state)
    claim_metrics = res["claims"]
    # The claim must NOT be counted as semantically supported despite > 100 char passage
    assert claim_metrics["semantically_supported"] == 0, "Unsupported claim must not pass semantic verification simply due to passage length!"
    assert claim_metrics["semantic_support_rate"] == 0.0


def test_unresolved_contradiction_updates_existing_claims_to_contradicted():
    """Verify that when an unresolved numerical contradiction is detected, existing conflicting claims in state are updated to CONTRADICTED."""
    engine = InvestigationEngine()
    state = engine.start_investigation(
        objective="Determine the static sea-level thrust of the Phoenix-1 engine",
        contract={"target_entities": ["Phoenix-1"]},
    )
    docs = [
        {
            "evidence_id": "ev_p1_stand",
            "url": "https://news-outlet-a.example.com/phoenix-120kn",
            "source_type": "news",
            "title": "Phoenix-1 Test Stand",
            "text": "Independent aerospace reporter asserts the Phoenix-1 engine achieved 120 kN sea-level thrust on the horizontal test stand.",
        },
        {
            "evidence_id": "ev_p1_audit",
            "url": "https://news-outlet-b.example.com/phoenix-85kn",
            "source_type": "news",
            "title": "Phoenix-1 Telemetry",
            "text": "Independent telemetry analyst reports the Phoenix-1 engine delivers strictly 85 kN sea-level thrust under standard atmosphere.",
        },
    ]

    engine._apply_observation(state, action=None, observation={"documents": docs, "combined_text": docs[0]["text"] + "\n" + docs[1]["text"]})

    assert len(state.contradictions) >= 1
    # For equal-tier unresolved contradiction, all conflicting values must be CONTRADICTED, never SUPPORTED
    phoenix_claims = [c for c in state.claims if c.get("subject") == "Phoenix-1" and ("120" in c.get("object", "") or "85" in c.get("object", ""))]
    assert len(phoenix_claims) >= 2
    for c in phoenix_claims:
        assert c.get("status") == "CONTRADICTED", f"Conflicting claim must be updated to CONTRADICTED: {c}"

    # Overall epistemic status must be CONTRADICTED
    assert engine.synthesize_epistemic_status(state) == "CONTRADICTED"


def test_resolved_authority_supersedes_inferior_claim_to_contradicted():
    """Verify that when an authoritative source resolves a conflict, the inferior claim is marked CONTRADICTED while the authoritative claim is SUPPORTED."""
    engine = InvestigationEngine()
    state = engine.start_investigation(
        objective="Determine certified payload of Titan-6",
        contract={"target_entities": ["Titan-6"]},
    )
    docs = [
        {
            "evidence_id": "ev_t6_pr",
            "url": "https://vendor.example.com/pr",
            "source_type": "press_release",
            "title": "Vendor PR",
            "text": "Vendor press release asserts Titan-6 payload capacity is 600 kg for automotive assembly.",
        },
        {
            "evidence_id": "ev_t6_cert",
            "url": "https://tuv.example.com/cert",
            "source_type": "official_certificate",
            "title": "ISO Certificate",
            "text": "Official CE Machinery Directive Certificate: Type-examination for Titan-6 confirms certified rated payload capacity under ISO 10218-1 is strictly 450 kg.",
        },
    ]

    engine._apply_observation(state, action=None, observation={"documents": docs, "combined_text": docs[0]["text"] + "\n" + docs[1]["text"]})

    # The superseded 600 kg claim must be CONTRADICTED
    c_600 = [c for c in state.claims if "600" in c.get("object", "")]
    assert len(c_600) >= 1
    assert c_600[0].get("status") == "CONTRADICTED", f"Superseded 600 kg claim must be CONTRADICTED: {c_600[0]}"



