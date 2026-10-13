"""Tests for Section 1: Benchmark Ground-Truth Isolation & Architectural Separation."""

import inspect
import pytest

from argus.investigation.orchestrator import InvestigationEngine
from argus.investigation.state import InvestigationState
from argus.investigation.benchmark.corpus import APEX_20_EXECUTIVES, INVESTIGATION_CORPUS_REGISTRY


def test_orchestrator_has_no_benchmark_ground_truth_imports():
    """Verify production orchestrator module does not import or reference APEX_20_EXECUTIVES."""
    import argus.investigation.orchestrator as orch_mod
    
    # 1. Module namespace check
    assert "APEX_20_EXECUTIVES" not in orch_mod.__dict__, (
        "Ground truth APEX_20_EXECUTIVES leaked into argus.investigation.orchestrator module namespace!"
    )
    
    # 2. Source code ast/text check
    src = inspect.getsource(orch_mod)
    assert "APEX_20_EXECUTIVES" not in src, (
        "Ground truth APEX_20_EXECUTIVES referenced in argus.investigation.orchestrator source!"
    )


def test_ordinary_investigation_without_benchmark_fixtures():
    """Verify production InvestigationEngine executes ordinary investigations without benchmark fixtures."""
    engine = InvestigationEngine()  # Standard instantiation
    
    objective = "Investigate Acme Corp. Identify officers and corporate registration."
    state = engine.start_investigation(objective=objective)
    
    # Verify state initializes cleanly
    assert isinstance(state, InvestigationState)
    assert state.objective == objective
    assert len(state.entities) >= 1  # Target entity registered
    assert len(state.claims) == 0
    
    # Execute step with mock observation containing generic text
    obs = {
        "observation_id": "obs_test_01",
        "action_id": "act_test_01",
        "documents": [
            {
                "url": "https://example.com/acme",
                "source_type": "web",
                "title": "Acme Corp Profile",
                "text": "Acme Corp was incorporated in Delaware.\n- Arthur Sterling: Chief Executive Officer (Executive leadership). Public Contact: arthur@acme.com.",
            }
        ],
        "combined_text": "Acme Corp was incorporated in Delaware.\n- Arthur Sterling: Chief Executive Officer (Executive leadership). Public Contact: arthur@acme.com.",
    }
    
    gain = engine._apply_observation(state, None, obs)
    assert gain > 0.0
    assert "Acme Corp" in state.entities or "Arthur Sterling" in state.entities
    
    # Ensure no benchmark ground-truth answers were spuriously injected
    apex_names = {ex["name"] for ex in APEX_20_EXECUTIVES}
    for entity_name in state.entities:
        assert entity_name not in apex_names, f"Spurious benchmark entity {entity_name} injected!"


def test_benchmark_answer_cannot_be_injected_via_fallback():
    """Verify that when an unknown executive is searched, ground truth answers are not fabricated."""
    engine = InvestigationEngine()
    state = engine.start_investigation(objective="Research Unknown Entity Leadership")
    
    # Text mentions a name not in corpus with no disclosed contact
    mock_obs = {
        "observation_id": "obs_unrelated",
        "action_id": "act_unrelated",
        "documents": [
            {
                "url": "https://example.com/random",
                "source_type": "web",
                "title": "Unrelated Schedule",
                "text": "- Random Nonexistent Officer: Vice President, Testing (Quality assurance). Public Contact: None disclosed.",
            }
        ],
        "combined_text": "- Random Nonexistent Officer: Vice President, Testing (Quality assurance). Public Contact: None disclosed.",
    }
    
    gain = engine._apply_observation(state, None, mock_obs)
    assert "Random Nonexistent Officer" in state.entities
    
    # Verify contact channel is legitimately extracted as NOT_FOUND, not hallucinated
    contact_claims = [c for c in state.claims if c.get("subject") == "Random Nonexistent Officer" and c.get("predicate") == "contact_channel"]
    assert len(contact_claims) == 1
    assert contact_claims[0]["object"] == "NOT_FOUND"
    assert contact_claims[0]["status"] == "NOT_FOUND"


def test_evaluation_harness_compares_independent_outputs():
    """Verify the evaluation harness independently evaluates state against APEX_20_EXECUTIVES ground truth."""
    engine = InvestigationEngine(corpus=INVESTIGATION_CORPUS_REGISTRY)
    objective = (
        "Research Apex Technologies Group. Identify 20 current VP/SVP-level executives. For each executive determine: "
        "name, current title, responsibility, organization, current status, career history, professional identity, "
        "and publicly documented business contact channel. Do NOT invent contact information."
    )
    contract = {"expected_executive_count": 20, "max_steps": 12}
    
    # Engine executes without benchmark leakage
    state = engine.run_to_completion(objective=objective, contract=contract, max_steps=12)
    
    # Evaluation harness checks independently
    evaluator_scores = {}
    for ex in APEX_20_EXECUTIVES:
        name = ex["name"]
        entity_found = name in state.entities
        title_claims = [c for c in state.claims if c.get("subject") == name and c.get("predicate") == "title"]
        contact_claims = [c for c in state.claims if c.get("subject") == name and c.get("predicate") == "contact_channel"]
        
        evaluator_scores[name] = {
            "entity_found": entity_found,
            "title_matched": len(title_claims) > 0 and title_claims[0]["object"] == ex["title"],
            "contact_matched": len(contact_claims) > 0 and contact_claims[0]["object"] == (ex["email"] if ex["email"] else "NOT_FOUND"),
        }
    
    # Verify evaluation harness scores all 20 correctly
    assert len(evaluator_scores) == 20
    assert all(s["entity_found"] for s in evaluator_scores.values())
    assert all(s["title_matched"] for s in evaluator_scores.values())
    assert all(s["contact_matched"] for s in evaluator_scores.values())


def test_adversarial_extraction_scenarios():
    """Adversarial stress-testing of production extraction against corrupted, complex, and deceptive inputs."""
    engine = InvestigationEngine()

    # 1. Two executives with similar names in the same document
    state1 = engine.start_investigation(objective="Investigate Apex leadership")
    obs1 = {
        "observation_id": "obs_adv_1",
        "action_id": "act_adv_1",
        "documents": [
            {
                "url": "https://example.com/sched1",
                "source_type": "sec_filing",
                "title": "SEC Schedule",
                "text": (
                    "- David J. Marcus: Senior Vice President (Machine Learning). Public Contact: djm@apex.com.\n"
                    "- David M. Marcus: Vice President (Data Engineering). Public Contact: dmm@apex.com."
                ),
            }
        ],
        "combined_text": (
            "- David J. Marcus: Senior Vice President (Machine Learning). Public Contact: djm@apex.com.\n"
            "- David M. Marcus: Vice President (Data Engineering). Public Contact: dmm@apex.com."
        ),
    }
    engine._apply_observation(state1, None, obs1)
    assert "David J. Marcus" in state1.entities
    assert "David M. Marcus" in state1.entities
    contacts = {c["subject"]: c["object"] for c in state1.claims if c.get("predicate") == "contact_channel"}
    assert contacts["David J. Marcus"] == "djm@apex.com"
    assert contacts["David M. Marcus"] == "dmm@apex.com"

    # 2. Accented characters, apostrophes, hyphens, and initials
    state2 = engine.start_investigation(objective="Investigate Apex leadership")
    obs2 = {
        "observation_id": "obs_adv_2",
        "action_id": "act_adv_2",
        "documents": [
            {
                "url": "https://example.com/sched2",
                "source_type": "sec_filing",
                "title": "SEC Schedule Unicode",
                "text": "- René Müller-Thorne: Executive Vice President (European Operations). Public Contact: rene.muller@apex-eu.com.",
            }
        ],
        "combined_text": "- René Müller-Thorne: Executive Vice President (European Operations). Public Contact: rene.muller@apex-eu.com.",
    }
    engine._apply_observation(state2, None, obs2)
    assert "René Müller-Thorne" in state2.entities
    c_rene = [c for c in state2.claims if c.get("subject") == "René Müller-Thorne" and c.get("predicate") == "contact_channel"]
    assert len(c_rene) == 1
    assert c_rene[0]["object"] == "rene.muller@apex-eu.com"

    # 3. Misordered biography fields and multiple people in one passage without field bleed
    state3 = engine.start_investigation(objective="Investigate Apex portal biographies")
    obs3 = {
        "observation_id": "obs_adv_3",
        "action_id": "act_adv_3",
        "documents": [
            {
                "url": "https://example.com/portal",
                "source_type": "portal",
                "title": "Corporate Bios",
                "text": (
                    "BIOGRAPHY: Dr. J. R. O'Connor\n"
                    "Scope: Quantum cryptographic algorithms\n"
                    "Title: Vice President, Cryptography\n"
                    "Business Inquiries: jroconnor@apex-quantum.com\n"
                    "Career History: 15 years in government defense research\n\n"
                    "BIOGRAPHY: Elena Rostova\n"
                    "Business Inquiries: None disclosed\n"
                    "Title: Managing Director, Steppe Resources\n"
                    "Career History: Former corporate executive\n"
                ),
            }
        ],
        "combined_text": (
            "BIOGRAPHY: Dr. J. R. O'Connor\n"
            "Scope: Quantum cryptographic algorithms\n"
            "Title: Vice President, Cryptography\n"
            "Business Inquiries: jroconnor@apex-quantum.com\n"
            "Career History: 15 years in government defense research\n\n"
            "BIOGRAPHY: Elena Rostova\n"
            "Business Inquiries: None disclosed\n"
            "Title: Managing Director, Steppe Resources\n"
            "Career History: Former corporate executive\n"
        ),
    }
    engine._apply_observation(state3, None, obs3)
    assert "Dr. J. R. O'Connor" in state3.entities
    assert "Elena Rostova" in state3.entities
    # Check fields correctly isolated without bleed
    oc_titles = [c["object"] for c in state3.claims if c.get("subject") == "Dr. J. R. O'Connor" and c.get("predicate") == "title"]
    er_titles = [c["object"] for c in state3.claims if c.get("subject") == "Elena Rostova" and c.get("predicate") == "title"]
    assert oc_titles == ["Vice President, Cryptography"]
    assert er_titles == ["Managing Director, Steppe Resources"]
    # Check contact: O'Connor has email, Rostova has NOT_FOUND
    contacts3 = {c["subject"]: c["object"] for c in state3.claims if c.get("predicate") == "contact_channel"}
    assert contacts3["Dr. J. R. O'Connor"] == "jroconnor@apex-quantum.com"
    assert contacts3["Elena Rostova"] == "NOT_FOUND"

    # 4. Text that resembles a benchmark answer but lacks supporting executive credentials
    state4 = engine.start_investigation(objective="Investigate Apex leadership")
    obs4 = {
        "observation_id": "obs_adv_4",
        "action_id": "act_adv_4",
        "documents": [
            {
                "url": "https://example.com/unsupported",
                "source_type": "press_release",
                "title": "Unsubstantiated text",
                "text": "Sarah Lin is an attendee at the technology symposium. No titles or roles mentioned.",
            }
        ],
        "combined_text": "Sarah Lin is an attendee at the technology symposium. No titles or roles mentioned.",
    }
    engine._apply_observation(state4, None, obs4)
    # No executive claims should be fabricated for Sarah Lin when merely an attendee
    exec_claims = [c for c in state4.claims if c.get("subject") == "Sarah Lin"]
    assert len(exec_claims) == 0

    # 5. Empty and malformed documents produce zero fabricated claims without crashing
    state5 = engine.start_investigation(objective="Investigate Apex leadership")
    obs5 = {
        "observation_id": "obs_adv_5",
        "action_id": "act_adv_5",
        "documents": [
            {"url": "https://example.com/empty", "source_type": "web", "title": "Empty", "text": ""},
            {"url": "https://example.com/garbage", "source_type": "web", "title": "Corrupt", "text": "===---###$$$%%% \x00\x01\x02"},
        ],
        "combined_text": "===---###$$$%%% \x00\x01\x02",
    }
    gain5 = engine._apply_observation(state5, None, obs5)
    assert gain5 == 0.0
    assert len(state5.claims) == 0

