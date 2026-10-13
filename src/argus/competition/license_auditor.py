"""Heimdallr V3.2: License Auditor & Pre-Integration Gate.

Enforces strict legal licensing verification before any open-source candidate
is integrated or benchmarked. Produces machine-readable license_audit.json.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from argus.competition.models import CandidateImplementation, LicenseStatus

logger = logging.getLogger(__name__)

# License Classification Mapping
APPROVED_LICENSES = {
    "mit", "apache-2.0", "apache 2.0", "bsd-2-clause", "bsd-3-clause", "cc0", "isc", "unlicense"
}
ATTRIBUTION_LICENSES = {
    "cc-by-4.0", "cc-by-sa-4.0", "odbl-1.0", "odbl", "open-government-licence"
}
RESTRICTED_LICENSES = {
    "cc-by-nc-4.0", "lgpl-2.1", "lgpl-3.0", "mpl-2.0", "epl-2.0"
}
INCOMPATIBLE_LICENSES = {
    "agpl-3.0", "agpl", "gpl-3.0", "gpl-2.0", "commercial", "proprietary", "sspl"
}


class LicenseAuditor:
    """Evaluates candidate license strings against Heimdallr legal policies."""

    @staticmethod
    def audit_license(license_str: str) -> LicenseStatus:
        """Classify a license string into a formal LicenseStatus."""
        if not license_str or license_str.strip().lower() in ("none", "", "undeclared"):
            return LicenseStatus.UNKNOWN

        clean = license_str.strip().lower()

        if any(lic in clean for lic in APPROVED_LICENSES):
            return LicenseStatus.APPROVED
        if any(lic in clean for lic in ATTRIBUTION_LICENSES):
            return LicenseStatus.APPROVED_WITH_ATTRIBUTION
        if any(lic in clean for lic in RESTRICTED_LICENSES):
            return LicenseStatus.RESTRICTED
        if any(lic in clean for lic in INCOMPATIBLE_LICENSES):
            return LicenseStatus.INCOMPATIBLE

        return LicenseStatus.UNKNOWN

    @staticmethod
    def is_commercially_compatible(status: LicenseStatus) -> bool:
        """Check if license status permits commercial deployment and bundling."""
        return status in (LicenseStatus.APPROVED, LicenseStatus.APPROVED_WITH_ATTRIBUTION)


    def audit_candidates(
        self,
        candidates: List[CandidateImplementation],
        output_path: Optional[Path | str] = None,
    ) -> Dict[str, Any]:
        """Audit a list of candidates and generate machine-readable license audit report."""
        audit_records: List[Dict[str, Any]] = []
        incompatible_count = 0

        for cand in candidates:
            status = self.audit_license(cand.license)
            cand.license_status = status
            is_acceptable = status in (LicenseStatus.APPROVED, LicenseStatus.APPROVED_WITH_ATTRIBUTION)

            record = {
                "candidate_id": cand.candidate_id,
                "name": cand.name,
                "version": cand.version,
                "declared_license": cand.license,
                "license_status": status.value,
                "acceptable_for_recruitment": is_acceptable,
                "requires_attribution": status == LicenseStatus.APPROVED_WITH_ATTRIBUTION,
                "repository": cand.repository,
            }
            audit_records.append(record)
            if not is_acceptable:
                incompatible_count += 1

        summary = {
            "audit_standard": "Heimdallr V3.2 Pre-Integration Legal Gate",
            "total_candidates_audited": len(candidates),
            "approved_candidates": len([r for r in audit_records if r["acceptable_for_recruitment"]]),
            "rejected_or_restricted_candidates": incompatible_count,
            "overall_status": "PASS" if incompatible_count == 0 else "WARNING_RESTRICTIONS_FOUND",
            "records": audit_records,
        }

        if output_path:
            p = Path(output_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                json.dump(summary, f, indent=2)
            logger.info("Saved license audit to %s", p)

        return summary
