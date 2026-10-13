"""P0.3-R: Unfamiliar Holdout Benchmark Corpus for Generalization Evaluation.

Contains realistic synthetic and documented facts for 10 holdout tasks completely
isolated from development and tuning:
1. Acrobotix Dynamic Systems (unseen robotics entity)
2. Calypso Consensus Protocol (unseen distributed systems technical topic)
3. First Solvay Conference 1911 (unseen historical physics conference)
4. Fermilab Muon g-2 Anomaly (unseen particle physics experimental claim)
5. Tunguska Event blast mechanism (unseen conflicting scientific hypotheses)
6. Fleischmann-Pons Cold Fusion 1989 (unseen unconfirmed claim with insufficient evidence)
7. reqeusts-py typosquatted package (unseen misleading/adversarial security topic)
8. Helios Energy AG -> SolarGrid Networks -> SCADA gateway (unseen multi-hop org-to-infra)
9. Acrobotix Department of Teleportation (unseen negative / non-existent entity)
10. Synthetix Bio Labs Q3 2025 executive succession (unseen temporal succession)
"""

from __future__ import annotations

from argus.investigation.benchmark.corpus import (
    InvestigationCorpusRegistry,
    InvestigationDocument,
)


def build_holdout_corpus() -> InvestigationCorpusRegistry:
    """Build and return the isolated 10-task holdout corpus registry."""
    corpus = InvestigationCorpusRegistry()
    corpus.documents = {}
    corpus._discoverable_entities = set()

    docs = {
        # Task 1: Acrobotix Dynamic Systems
        "holdout_doc_01": InvestigationDocument(
            doc_id="holdout_doc_01",
            title="Acrobotix Dynamic Systems Company Overview",
            url="https://acrobotix.tech/about",
            text_content=(
                "Acrobotix Dynamic Systems was founded in 2021 by Dr. Elena Voronova in Munich. "
                "The company specializes in dynamic legged robotics, developing the Centaur-4 Quadruped. "
                "The Centaur-4 Quadruped utilizes proprietary quasi-direct drive electro-hydraulic actuators "
                "for all-terrain mobility and payload transport up to 35 kilograms."
            ),
            source_type="corporate_overview",
        ),
        "holdout_doc_02": InvestigationDocument(
            doc_id="holdout_doc_02",
            title="Centaur-4 Technical Datasheet - Acrobotix",
            url="https://acrobotix.tech/products/centaur4",
            text_content=(
                "Centaur-4 Quadruped is manufactured by Acrobotix Dynamic Systems. "
                "Chief Executive Officer Dr. Elena Voronova confirmed field trials with civil rescue units. "
                "The primary actuation system combines quasi-direct drive brushless motors with planetary gearboxes."
            ),
            source_type="technical_specification",
        ),

        # Task 2: Calypso Consensus Protocol
        "holdout_doc_03": InvestigationDocument(
            doc_id="holdout_doc_03",
            title="Calypso Consensus: A Pipelined Byzantine Fault Tolerant Protocol",
            url="https://calypso-consensus.org/whitepaper.pdf",
            text_content=(
                "Calypso Consensus Protocol was specified by Dr. Tariq Vance and Marcus Sterling in 2023. "
                "The protocol guarantees safety and liveness under partial synchrony with a fault tolerance bound "
                "of 3f+1 replicas. Leader election operates via verifiable random function leader rotation, "
                "while log compaction is performed using cryptographic Merkle tree state snapshots."
            ),
            source_type="academic_whitepaper",
        ),
        "holdout_doc_04": InvestigationDocument(
            doc_id="holdout_doc_04",
            title="Calypso Consensus Engineering Implementation Guidelines",
            url="https://calypso-consensus.org/docs/implementation",
            text_content=(
                "Engineers implementing the Calypso Consensus Protocol must verify state snapshots. "
                "Co-creator Marcus Sterling presented benchmark results demonstrating 45,000 transactions per second "
                "across 128 geo-distributed nodes using verifiable random function leader rotation."
            ),
            source_type="technical_documentation",
        ),

        # Task 3: 1911 First Solvay Conference
        "holdout_doc_05": InvestigationDocument(
            doc_id="holdout_doc_05",
            title="The 1911 First Solvay Council on Physics",
            url="https://history-of-physics.org/solvay-1911",
            text_content=(
                "The First Solvay Conference took place in Brussels in late autumn 1911, sponsored by industrialist Ernest Solvay. "
                "The scientific proceedings were presided over by Hendrik Lorentz as scientific chair. "
                "Notable attendees included Marie Curie, Albert Einstein, Henri Poincaré, Ernest Rutherford, and Max Planck. "
                "The central agenda was titled 'The Theory of Radiation and Quanta', debating the breakdown of classical physics."
            ),
            source_type="historical_archive",
        ),
        "holdout_doc_06": InvestigationDocument(
            doc_id="holdout_doc_06",
            title="Letters of Albert Einstein on the 1911 Solvay Meeting",
            url="https://einstein-papers.org/letters/solvay1911",
            text_content=(
                "Writing from Zurich after attending the 1911 First Solvay Conference, Albert Einstein praised Hendrik Lorentz "
                "for his skillful leadership as chair of the discussions. Einstein noted intense exchanges with Marie Curie "
                "and Henri Poincaré regarding quantum discontinuity and specific heat anomalies."
            ),
            source_type="primary_source_correspondence",
        ),

        # Task 4: Fermilab Muon g-2 Anomaly
        "holdout_doc_07": InvestigationDocument(
            doc_id="holdout_doc_07",
            title="Fermilab Muon g-2 Collaboration First Results Announcement",
            url="https://fnal.gov/press-releases/muon-g2-2021",
            text_content=(
                "The Muon g-2 Experiment collaboration at Fermilab published its landmark measurement of the muon anomalous "
                "magnetic dipole moment. The experimental value showed a discrepancy of 4.2 sigma from the Standard Model "
                "prediction computed by the Muon g-2 Theory Initiative, hinting at possible undiscovered particles or interactions."
            ),
            source_type="laboratory_press_release",
        ),
        "holdout_doc_08": InvestigationDocument(
            doc_id="holdout_doc_08",
            title="Physical Review Letters: Measurement of the Positive Muon Anomalous Magnetic Moment",
            url="https://journals.aps.org/prl/abstract/10.1103/PhysRevLett.126.141801",
            text_content=(
                "The Fermilab Muon g-2 Experiment reports a combined precision of 460 parts per billion. "
                "Comparing the Brookhaven National Laboratory and Fermilab measurements against the Standard Model prediction "
                "yields a 4.2 sigma statistical tension, strengthening evidence for new physics in leptonic loops."
            ),
            source_type="peer_reviewed_paper",
        ),

        # Task 5: 1908 Tunguska Event Conflicting Hypotheses
        "holdout_doc_09": InvestigationDocument(
            doc_id="holdout_doc_09",
            title="The 1908 Tunguska Explosion: Asteroid Airburst Model",
            url="https://planetary-science.org/tunguska/asteroid-airburst",
            text_content=(
                "The 1908 Tunguska Event flattened over 2,000 square kilometers of Siberian taiga. "
                "Planetary dynamics simulations by Vasilyev and modern computational fluid models demonstrate "
                "the blast was caused by a stony asteroid airburst entering the atmosphere at 15 kilometers per second, "
                "disintegrating between 5 and 10 kilometers altitude with no macroscopic impact crater."
            ),
            source_type="scientific_journal_article",
        ),
        "holdout_doc_10": InvestigationDocument(
            doc_id="holdout_doc_10",
            title="The Cometary Hypothesis for the Tunguska Event: Competing Accounts",
            url="https://astronomy-historical.org/tunguska/comet-fragment",
            text_content=(
                "Historical astronomer Fred Whipple and later researchers argued the Tunguska Event was caused by a low-density "
                "cometary core fragment or ice-rich debris from Comet Encke. However, contemporary astronomical analyses contradict "
                "the cometary model, showing a cometary nucleus would have detonated much higher in the stratosphere. "
                "The competing accounts remain a subject of active historical and geophysical debate."
            ),
            source_type="scientific_review",
        ),

        # Task 6: 1989 Fleischmann-Pons Cold Fusion Replication
        "holdout_doc_11": InvestigationDocument(
            doc_id="holdout_doc_11",
            title="1989 University of Utah Electrochemistry Press Conference",
            url="https://historical-chem.org/fleischmann-pons-1989",
            text_content=(
                "In March 1989, Martin Fleischmann and Stanley Pons reported sustained nuclear fusion in a tabletop "
                "electrolytic cell using heavy water and a palladium cathode, claiming significant excess heat and neutron emission."
            ),
            source_type="historical_press_conference",
        ),
        "holdout_doc_12": InvestigationDocument(
            doc_id="holdout_doc_12",
            title="Comprehensive Analysis of Cold Fusion Replication Attempts",
            url="https://energy-eval.org/reports/cold-fusion-replications",
            text_content=(
                "Independent laboratories worldwide, including Caltech, MIT, and Harwell, attempted rigorous replications of the "
                "Martin Fleischmann and Stanley Pons electrolytic apparatus. Comprehensive calorimetric and gamma-ray measurements "
                "yielded a null result, failing to replicate excess heat or nuclear products. The global scientific consensus concluded "
                "there is insufficient evidence and unconfirmed claims for tabletop low-energy nuclear fusion."
            ),
            source_type="independent_meta_analysis",
        ),

        # Task 7: Misleading-Source Typosquatted Package reqeusts-py
        "holdout_doc_13": InvestigationDocument(
            doc_id="holdout_doc_13",
            title="PyPI Security Advisory: Malicious Typosquatting of requests",
            url="https://pypi-security.org/advisories/reqeusts-py",
            text_content=(
                "Security researchers discovered a malicious typosquatted package named 'reqeusts-py' published to public repositories. "
                "While claiming in its setup.py metadata to be an HTTP requests library, the package executes an obfuscated post-install "
                "hook that exfiltrates local AWS credentials, environment variables, and SSH keys to an unauthorized drop host. "
                "It is confirmed malware and completely distinct from Kenneth Reitz's legitimate 'requests' package."
            ),
            source_type="security_advisory",
        ),

        # Task 8: Helios Energy AG -> SolarGrid Networks -> SCADA Gateway
        "holdout_doc_14": InvestigationDocument(
            doc_id="holdout_doc_14",
            title="Helios Energy AG Corporate Profile and Acquisitions",
            url="https://helios-energy.de/about",
            text_content=(
                "Helios Energy AG is a renewable energy conglomerate headquartered in Frankfurt. "
                "In January 2024, Helios Energy AG completed the strategic acquisition of SolarGrid Networks GmbH, "
                "a specialist in decentralized photovoltaic power telemetry and substation communications."
            ),
            source_type="corporate_registry",
        ),
        "holdout_doc_15": InvestigationDocument(
            doc_id="holdout_doc_15",
            title="SolarGrid Networks Operational Infrastructure Guide",
            url="https://solargrid-net.de/infra/telemetry",
            text_content=(
                "SolarGrid Networks, an operating subsidiary of Helios Energy AG, centralizes all substation telemetry. "
                "The designated primary SCADA telemetry gateway is scada-gw01.solargrid-net.de, protected by mutual TLS "
                "and routing data from over 850 distributed inverter stations."
            ),
            source_type="infrastructure_documentation",
        ),

        # Task 9: Acrobotix Department of Teleportation (Negative Task)
        "holdout_doc_16": InvestigationDocument(
            doc_id="holdout_doc_16",
            title="Acrobotix Dynamic Systems Organizational Chart 2026",
            url="https://acrobotix.tech/governance/org-chart",
            text_content=(
                "Acrobotix Dynamic Systems maintains four operational divisions: Mechanical Engineering, Embedded Firmware, "
                "Perception Systems, and Field Deployment Operations. There is zero affiliation, no record, and no division "
                "concerning teleportation, quantum teleportation, or related speculative physics."
            ),
            source_type="organizational_filing",
        ),

        # Task 10: Synthetix Bio Labs Q3 2025 Executive Succession
        "holdout_doc_17": InvestigationDocument(
            doc_id="holdout_doc_17",
            title="Synthetix Bio Labs Press Release July 2025: CEO Stepping Down",
            url="https://synthetix-bio.com/news/2025-07-ceo-resignation",
            text_content=(
                "Synthetix Bio Labs announced that founder and Chief Executive Officer Dr. Arthur Bell has stepped down "
                "from executive duties effective July 15, 2025. Chief Scientific Officer Dr. Clara Oswald was appointed interim CEO "
                "while an executive search was conducted."
            ),
            source_type="press_release_archive",
        ),
        "holdout_doc_18": InvestigationDocument(
            doc_id="holdout_doc_18",
            title="Synthetix Bio Labs Regulatory Filing September 2025: Permanent CEO Appointed",
            url="https://synthetix-bio.com/investors/sec-filing-sep2025",
            text_content=(
                "Form 8-K Regulatory Filing for Synthetix Bio Labs: On September 1, 2025, the Board of Directors concluded the "
                "executive search and appointed Marcus Thorne as permanent Chief Executive Officer, succeeding interim CEO Dr. Clara Oswald. "
                "Earlier reports indicating Dr. Clara Oswald or Dr. Arthur Bell as current CEO are outdated and contradicted by this filing."
            ),
            source_type="regulatory_filing",
        ),
    }

    corpus.documents = docs
    for doc in docs.values():
        corpus._discoverable_entities.update([
            "Acrobotix Dynamic Systems",
            "Dr. Elena Voronova",
            "Centaur-4 Quadruped",
            "Calypso Consensus Protocol",
            "Dr. Tariq Vance",
            "Marcus Sterling",
            "First Solvay Conference",
            "Hendrik Lorentz",
            "Ernest Solvay",
            "Marie Curie",
            "Albert Einstein",
            "Henri Poincaré",
            "Muon g-2 Experiment",
            "Fermilab",
            "Tunguska Event",
            "Martin Fleischmann",
            "Stanley Pons",
            "Cold Fusion",
            "reqeusts-py",
            "Helios Energy AG",
            "SolarGrid Networks",
            "scada-gw01.solargrid-net.de",
            "Synthetix Bio Labs",
            "Dr. Arthur Bell",
            "Dr. Clara Oswald",
            "Marcus Thorne",
        ])

    return corpus
