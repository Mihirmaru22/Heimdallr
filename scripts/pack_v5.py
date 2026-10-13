"""Package Heimdallr Vertical 5.1 deliverables into a single flat archive v5.zip."""

import os
from pathlib import Path
import shutil
import zipfile

WORKSPACE_ROOT = Path("/data/shared/project/PlayGround/Argus")
ARTIFACT_DIR = Path("/home/mihir/.gemini/antigravity-ide/brain/e083056e-870d-441d-9836-aa983eb6150d")

FILES_TO_PACK = [
    # 13 Documentation Deliverables
    WORKSPACE_ROOT / "docs/V5_VERTICAL_SELECTION.md",
    WORKSPACE_ROOT / "docs/V5_CAPABILITY_SPEC.md",
    WORKSPACE_ROOT / "docs/V5_CANDIDATE_AUDIT.md",
    WORKSPACE_ROOT / "docs/V5_BENCHMARK_REPORT.md",
    WORKSPACE_ROOT / "docs/V5_ROUTING_REPORT.md",
    WORKSPACE_ROOT / "docs/V5_SECURITY_REPORT.md",
    WORKSPACE_ROOT / "docs/V5_CROSS_SPECIALIST_REPORT.md",
    WORKSPACE_ROOT / "docs/V5_CANDIDATE_ATTRIBUTION.md",
    WORKSPACE_ROOT / "docs/V5_COMPETITION_REPORT.md",
    WORKSPACE_ROOT / "docs/V5_FINAL_DECISION.md",
    WORKSPACE_ROOT / "docs/V5_FINAL_VALIDATION_REPORT.md",
    WORKSPACE_ROOT / "docs/V5_EVIDENCE_INTEGRITY_REPORT.md",
    WORKSPACE_ROOT / "docs/V5_LEAKAGE_AUDIT.md",
    # 13 Proof Deliverables
    WORKSPACE_ROOT / "proofs/v5_capability_benchmark.json",
    WORKSPACE_ROOT / "proofs/v5_routing.json",
    WORKSPACE_ROOT / "proofs/v5_security.json",
    WORKSPACE_ROOT / "proofs/v5_cross_specialist.json",
    WORKSPACE_ROOT / "proofs/v5_candidate_attribution.json",
    WORKSPACE_ROOT / "proofs/v5_ablation.json",
    WORKSPACE_ROOT / "proofs/v5_competition.json",
    WORKSPACE_ROOT / "proofs/v5_regressions.json",
    WORKSPACE_ROOT / "proofs/v5_stability.json",
    WORKSPACE_ROOT / "proofs/v5_leakage_audit.json",
    WORKSPACE_ROOT / "proofs/v5_trajectories.json",
    WORKSPACE_ROOT / "proofs/v5_evidence_integrity.json",
    WORKSPACE_ROOT / "proofs/v5_final_scorecard.json",
]


def main():
    zip_path = WORKSPACE_ROOT / "v5.zip"
    if zip_path.exists():
        zip_path.unlink()

    print(f"Creating flat archive: {zip_path}")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in FILES_TO_PACK:
            if not file_path.exists():
                raise FileNotFoundError(f"Missing deliverable: {file_path}")
            zf.write(file_path, arcname=file_path.name)
            print(f"  Added: {file_path.name} ({file_path.stat().st_size} bytes)")

    # Copy to artifact directory
    artifact_zip = ARTIFACT_DIR / "v5.zip"
    shutil.copy2(zip_path, artifact_zip)
    print(f"Copied archive to artifact directory: {artifact_zip}")

    # Verify contents
    with zipfile.ZipFile(zip_path, "r") as zf:
        namelist = zf.namelist()
        print(f"Verification: {len(namelist)} files in archive. Subdirectories: {[n for n in namelist if '/' in n]}")
        assert len(namelist) == len(FILES_TO_PACK), f"Expected {len(FILES_TO_PACK)}, got {len(namelist)}"
        print("Archive successfully verified with all V5.1 release deliverables!")


if __name__ == "__main__":
    main()
