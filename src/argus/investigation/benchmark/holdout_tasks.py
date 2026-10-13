"""P0.3-R: 10 Unfamiliar Holdout Tasks for Generalization Evaluation.

These 10 tasks test the engine's generalization on completely unseen domains
and materials not used during development:
1. Unseen entity: Acrobotix Dynamic Systems
2. Unseen technical question: Calypso Consensus Protocol
3. Unseen historical question: First Solvay Conference 1911
4. Unseen scientific claim: Fermilab Muon g-2 Anomaly
5. Unseen conflicting sources: 1908 Tunguska Event blast mechanism
6. Unseen insufficient evidence: 1989 Fleischmann-Pons Cold Fusion Replication
7. Unseen misleading source: reqeusts-py typosquatted malware package
8. Unseen multi-hop research question: Helios Energy AG to SCADA gateway
9. Unseen negative case: Acrobotix Department of Teleportation
10. Unseen temporal succession: Synthetix Bio Labs Q3 2025 CEO transition
"""

from __future__ import annotations

from argus.investigation.benchmark.tasks import (
    InvestigationCategory,
    InvestigationDifficulty,
    InvestigationTask,
)


def build_holdout_tasks() -> list[InvestigationTask]:
    """Generate the 10 unfamiliar holdout benchmark tasks."""
    return [
        InvestigationTask(
            task_id="holdout_task_01_unseen_entity",
            title="Acrobotix Dynamic Systems Founding and Product Line",
            objective="Investigate Acrobotix Dynamic Systems. Identify the founder, primary quadruped robotics product, and actuation technology.",
            category=InvestigationCategory.TECHNICAL_ENGINEERING,
            difficulty=InvestigationDifficulty.HARD,
            contract={"target_entities": ["Acrobotix Dynamic Systems"]},
            expected_entities=["Acrobotix Dynamic Systems", "Dr. Elena Voronova", "Centaur-4 Quadruped"],
            expected_epistemic_status="SUPPORTED",
            min_steps_required=3,
        ),
        InvestigationTask(
            task_id="holdout_task_02_unseen_technical",
            title="Calypso Byzantine Fault Tolerant Consensus Protocol Architecture",
            objective="Analyze the Calypso Consensus Protocol. Determine the fault tolerance bound, leader election mechanism, and log compaction method.",
            category=InvestigationCategory.TECHNICAL_ENGINEERING,
            difficulty=InvestigationDifficulty.HARD,
            contract={"target_entities": ["Calypso Consensus Protocol"]},
            expected_entities=["Calypso Consensus Protocol", "Dr. Tariq Vance", "Marcus Sterling"],
            expected_epistemic_status="SUPPORTED",
            min_steps_required=3,
        ),
        InvestigationTask(
            task_id="holdout_task_03_unseen_historical",
            title="1911 First Solvay Conference Proceedings and Leadership",
            objective="Investigate the First Solvay Conference held in Brussels in 1911. Identify the scientific chair, host Ernest Solvay, and key attendees who debated quantum radiation.",
            category=InvestigationCategory.HISTORICAL,
            difficulty=InvestigationDifficulty.HARD,
            contract={"target_entities": ["First Solvay Conference"]},
            expected_entities=["First Solvay Conference", "Hendrik Lorentz", "Marie Curie", "Albert Einstein"],
            expected_epistemic_status="SUPPORTED",
            min_steps_required=3,
        ),
        InvestigationTask(
            task_id="holdout_task_04_unseen_scientific",
            title="Fermilab Muon g-2 Anomaly Measurement and Standard Model Tension",
            objective="Analyze the Fermilab Muon g-2 Experiment findings regarding muon anomalous magnetic dipole moment and reported statistical tension with the Standard Model.",
            category=InvestigationCategory.SCIENTIFIC_POLICY,
            difficulty=InvestigationDifficulty.HARD,
            contract={"target_entities": ["Muon g-2 Experiment"]},
            expected_entities=["Muon g-2 Experiment", "Fermilab"],
            expected_epistemic_status="SUPPORTED",
            min_steps_required=3,
        ),
        InvestigationTask(
            task_id="holdout_task_05_unseen_conflicting",
            title="1908 Tunguska Event Explosion: Asteroid Airburst vs Cometary Hypothesis",
            objective="Examine competing scientific accounts of the 1908 Tunguska Event. Resolve whether consensus attributes the blast to a stony asteroid airburst or cometary fragment.",
            category=InvestigationCategory.CONFLICTING_AMBIGUOUS,
            difficulty=InvestigationDifficulty.HARD,
            contract={"target_entities": ["Tunguska Event"]},
            expected_entities=["Tunguska Event"],
            has_contradiction=True,
            expected_epistemic_status="CONTRADICTED",
            min_steps_required=3,
        ),
        InvestigationTask(
            task_id="holdout_task_06_unseen_insufficient",
            title="Fleischmann-Pons Cold Fusion Independent Replication Attempts",
            objective="Investigate whether independent laboratories replicated excess heat and nuclear products in the 1989 Fleischmann-Pons palladium-deuterium electrolytic experiment.",
            category=InvestigationCategory.INSUFFICIENT_EVIDENCE,
            difficulty=InvestigationDifficulty.HARD,
            contract={"target_entities": ["Martin Fleischmann", "Cold Fusion"]},
            expected_entities=["Martin Fleischmann", "Stanley Pons", "Cold Fusion"],
            expected_epistemic_status="INSUFFICIENT_EVIDENCE",
            min_steps_required=3,
        ),
        InvestigationTask(
            task_id="holdout_task_07_unseen_misleading",
            title="Typosquatted Package reqeusts-py vs Legitimate Requests Library",
            objective="Investigate the Python package 'reqeusts-py'. Determine whether it is an official HTTP library or a typosquatted malware package exfiltrating environment credentials.",
            category=InvestigationCategory.MISLEADING_RESULTS,
            difficulty=InvestigationDifficulty.HARD,
            contract={"target_entities": ["reqeusts-py"]},
            expected_entities=["reqeusts-py"],
            expected_epistemic_status="SUPPORTED",
            min_steps_required=3,
        ),
        InvestigationTask(
            task_id="holdout_task_08_unseen_multihop",
            title="Helios Energy AG Corporate Acquisition and SCADA Gateway Infrastructure",
            objective="Conduct a multi-hop investigation starting from Helios Energy AG to its acquisition SolarGrid Networks and trace the designated operational SCADA telemetry gateway.",
            category=InvestigationCategory.INTERDISCIPLINARY,
            difficulty=InvestigationDifficulty.HARD,
            contract={"target_entities": ["Helios Energy AG"]},
            expected_entities=["Helios Energy AG", "SolarGrid Networks", "scada-gw01.solargrid-net.de"],
            requires_multi_specialist=True,
            expected_epistemic_status="SUPPORTED",
            min_steps_required=4,
        ),
        InvestigationTask(
            task_id="holdout_task_09_unseen_negative",
            title="Acrobotix Dynamic Systems Department of Teleportation Verification",
            objective="Verify whether Acrobotix Dynamic Systems operates an active Department of Teleportation or Quantum Teleportation division.",
            category=InvestigationCategory.NEGATIVE_NOT_FOUND,
            difficulty=InvestigationDifficulty.HARD,
            contract={"target_entities": ["Acrobotix Dynamic Systems Department of Teleportation"]},
            expected_entities=["Acrobotix Dynamic Systems"],
            is_negative=True,
            expected_epistemic_status="NOT_FOUND",
            min_steps_required=3,
        ),
        InvestigationTask(
            task_id="holdout_task_10_unseen_temporal",
            title="Synthetix Bio Labs Q3 2025 CEO Succession and Interim Appointment",
            objective="Reconstruct executive leadership changes at Synthetix Bio Labs during the Q3 2025 board restructuring and resolve competing claims regarding the current chief executive officer.",
            category=InvestigationCategory.TIME_SENSITIVE,
            difficulty=InvestigationDifficulty.HARD,
            contract={"target_entities": ["Synthetix Bio Labs"]},
            expected_entities=["Synthetix Bio Labs", "Dr. Arthur Bell", "Dr. Clara Oswald", "Marcus Thorne"],
            has_temporal_trap=True,
            has_contradiction=True,
            expected_epistemic_status="CONTRADICTED",
            min_steps_required=3,
        ),
    ]
