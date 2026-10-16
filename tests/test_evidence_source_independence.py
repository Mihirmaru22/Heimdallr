"""Tests for Evidence Source Independence in EvidenceRequirement.

Verifies:
1. Multiple records from the same source cannot count as independent corroboration.
2. Records from different sources correctly count as independent.
3. Non-independent evidence contributes to records but not independent source tally.
4. Duplicate evidence IDs are deduplicated.
5. Source key deduplication using source_id and source_type:evidence_id.
6. Documents limitations of the independence model.
"""

import pytest
from argus.investigation.evidence import EvidenceRequirement, EvidenceStatus


class TestSameSourceDeduplication:
    """Multiple records from the same source must NOT count as independent corroboration."""

    def test_same_source_id_counted_once(self):
        """Two evidence items from the same source_id must yield only 1 independent source."""
        req = EvidenceRequirement(
            description="Test requirement",
            min_independent_sources=2,
        )
        req.add_satisfying_evidence("ev_001", source_type="github", source_id="github-api-v3")
        req.add_satisfying_evidence("ev_002", source_type="github", source_id="github-api-v3")

        assert len(req.satisfied_by_evidence_ids) == 2  # Both evidence items registered
        assert len(req.independent_sources) == 1  # But only 1 independent source
        assert req.status == EvidenceStatus.PARTIALLY_SATISFIED  # Not fully satisfied

    def test_same_source_type_different_evidence_default_key(self):
        """Without explicit source_id, same source_type with different evidence_ids
        generates different default keys (source_type:evidence_id), so they count separately.
        
        LIMITATION: This is a known limitation — if two evidence items from the same
        API endpoint are submitted without a shared source_id, the default key derivation
        treats them as independent. Callers must provide consistent source_id values
        to enforce proper deduplication.
        """
        req = EvidenceRequirement(
            description="Test requirement",
            min_independent_sources=2,
        )
        req.add_satisfying_evidence("ev_001", source_type="github")
        req.add_satisfying_evidence("ev_002", source_type="github")

        # Default keys: "github:ev_001" and "github:ev_002" are different
        assert len(req.independent_sources) == 2
        # This documents the LIMITATION: without source_id, dedup fails

    def test_explicit_source_id_enforces_dedup(self):
        """Callers providing the same source_id get proper deduplication."""
        req = EvidenceRequirement(
            description="Test requirement",
            min_independent_sources=3,
        )
        # Three evidence items, all from the same source
        req.add_satisfying_evidence("ev_001", source_type="github", source_id="github-users-api")
        req.add_satisfying_evidence("ev_002", source_type="github", source_id="github-users-api")
        req.add_satisfying_evidence("ev_003", source_type="github", source_id="github-users-api")

        assert len(req.satisfied_by_evidence_ids) == 3
        assert len(req.independent_sources) == 1
        assert req.status == EvidenceStatus.PARTIALLY_SATISFIED


class TestDifferentSourceIndependence:
    """Records from genuinely different sources must count independently."""

    def test_two_different_sources_satisfy_requirement(self):
        req = EvidenceRequirement(
            description="Test requirement",
            min_independent_sources=2,
        )
        req.add_satisfying_evidence("ev_001", source_type="github", source_id="github-api")
        req.add_satisfying_evidence("ev_002", source_type="twitter", source_id="twitter-api")

        assert len(req.independent_sources) == 2
        assert req.status == EvidenceStatus.SATISFIED
        assert req.is_satisfied()

    def test_three_different_sources(self):
        req = EvidenceRequirement(
            description="High-confidence requirement",
            min_independent_sources=3,
        )
        req.add_satisfying_evidence("ev_001", source_type="github", source_id="github-api")
        req.add_satisfying_evidence("ev_002", source_type="sec_edgar", source_id="edgar-submissions")
        req.add_satisfying_evidence("ev_003", source_type="crtsh", source_id="ct-log-api")

        assert len(req.independent_sources) == 3
        assert req.is_satisfied()

    def test_mixed_sources_with_duplicates(self):
        """Two real sources + duplicate from first source = still only 2 independent."""
        req = EvidenceRequirement(
            description="Test requirement",
            min_independent_sources=3,
        )
        req.add_satisfying_evidence("ev_001", source_type="github", source_id="github-api")
        req.add_satisfying_evidence("ev_002", source_type="twitter", source_id="twitter-api")
        req.add_satisfying_evidence("ev_003", source_type="github", source_id="github-api")  # duplicate source

        assert len(req.satisfied_by_evidence_ids) == 3
        assert len(req.independent_sources) == 2  # Only 2 unique sources
        assert req.status == EvidenceStatus.PARTIALLY_SATISFIED


class TestNonIndependentEvidence:
    """Non-independent items contribute to evidence records but not source tally."""

    def test_non_independent_does_not_count(self):
        req = EvidenceRequirement(
            description="Test requirement",
            min_independent_sources=2,
        )
        req.add_satisfying_evidence("ev_001", source_type="github", source_id="github-api", is_independent=True)
        req.add_satisfying_evidence("ev_002", source_type="derived", source_id="local-cache", is_independent=False)

        assert len(req.satisfied_by_evidence_ids) == 2
        assert len(req.independent_sources) == 1  # Only the independent one
        assert "derived" in req.discovered_source_types  # Source type still registered
        assert req.status == EvidenceStatus.PARTIALLY_SATISFIED

    def test_only_non_independent_evidence(self):
        """Non-independent evidence alone cannot satisfy or partially-satisfy
        an independent-source requirement. Status must remain UNSATISFIED
        because 0 independent sources exist against a threshold of 1."""
        req = EvidenceRequirement(
            description="Test requirement",
            min_independent_sources=1,
        )
        req.add_satisfying_evidence("ev_001", source_type="cache", is_independent=False)

        assert len(req.satisfied_by_evidence_ids) == 1
        assert len(req.independent_sources) == 0
        # 0 independent sources < 1 required: must stay UNSATISFIED
        assert req.status == EvidenceStatus.UNSATISFIED


class TestEvidenceIdDeduplication:
    """Duplicate evidence IDs are deduplicated in satisfied_by_evidence_ids."""

    def test_same_evidence_id_registered_once(self):
        req = EvidenceRequirement(
            description="Test requirement",
            min_independent_sources=1,
        )
        req.add_satisfying_evidence("ev_001", source_type="github", source_id="github-api")
        req.add_satisfying_evidence("ev_001", source_type="github", source_id="github-api")  # exact duplicate

        assert len(req.satisfied_by_evidence_ids) == 1
        assert len(req.independent_sources) == 1


class TestRequiredSourceTypes:
    """Source type filtering for specialized evidence requirements."""

    def test_required_source_type_must_match(self):
        req = EvidenceRequirement(
            description="Must come from SEC EDGAR",
            min_independent_sources=1,
            required_source_types=["sec_edgar"],
        )
        # Provide evidence from wrong source type
        req.add_satisfying_evidence("ev_001", source_type="github", source_id="github-api")

        assert len(req.independent_sources) == 1
        assert req.status == EvidenceStatus.PARTIALLY_SATISFIED  # Source count met but type not

    def test_required_source_type_satisfied(self):
        req = EvidenceRequirement(
            description="Must come from SEC EDGAR",
            min_independent_sources=1,
            required_source_types=["sec_edgar"],
        )
        req.add_satisfying_evidence("ev_001", source_type="sec_edgar", source_id="edgar-api")

        assert req.is_satisfied()
        assert req.satisfied_at is not None


class TestIndependenceModelLimitations:
    """Document known limitations of the source independence model.
    
    These tests serve as documentation of the current design boundaries,
    not as bugs to be fixed in this pass.
    """

    def test_limitation_default_key_allows_same_source_different_evidence(self):
        """DOCUMENTED LIMITATION: Without explicit source_id, the default key
        'source_type:evidence_id' allows multiple items from the same actual source
        to be counted as independent if they have different evidence_ids.
        
        Mitigation: Callers must provide consistent source_id values when submitting
        evidence from the same API endpoint or data source.
        """
        req = EvidenceRequirement(
            description="Limitation test",
            min_independent_sources=2,
        )
        # Same API, no source_id: default keys differ
        req.add_satisfying_evidence("ev_001", source_type="github")
        req.add_satisfying_evidence("ev_002", source_type="github")

        # This succeeds (2 independent), but both came from the same source
        # This is a KNOWN LIMITATION
        assert len(req.independent_sources) == 2
        # Documented: caller must set source_id="github-api" for proper dedup

    def test_limitation_no_cross_requirement_dedup(self):
        """DOCUMENTED LIMITATION: Independence is tracked per-requirement,
        not globally across all requirements in an investigation.
        
        Two different requirements can independently count the same source
        as satisfying their respective independence thresholds.
        """
        req1 = EvidenceRequirement(description="Req 1", min_independent_sources=1)
        req2 = EvidenceRequirement(description="Req 2", min_independent_sources=1)

        req1.add_satisfying_evidence("ev_001", source_type="github", source_id="github-api")
        req2.add_satisfying_evidence("ev_001", source_type="github", source_id="github-api")

        # Both satisfied by the same single source
        assert req1.is_satisfied()
        assert req2.is_satisfied()
        # Documented: no global source budget across requirements
