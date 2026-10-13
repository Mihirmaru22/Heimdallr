"""Package Heimdallr Vertical 5.1.1 deliverables into a single flat archive v5_1_1.zip."""

import os
from pathlib import Path
import shutil
import zipfile

WORKSPACE_ROOT = Path("/data/shared/project/PlayGround/Argus")
ARTIFACT_DIR = Path("/home/mihir/.gemini/antigravity-ide/brain/e083056e-870d-441d-9836-aa983eb6150d")

FILES_TO_PACK = [
    # 6 Documentation Deliverables
    WORKSPACE_ROOT / "docs/V5_1_1_SOURCE_AUDIT_REPORT.md",
    WORKSPACE_ROOT / "docs/V5_1_1_BENCHMARK_REPRODUCTION.md",
    WORKSPACE_ROOT / "docs/V5_1_1_CAPABILITY_GAP_REPORT.md",
    WORKSPACE_ROOT / "docs/V5_1_1_ROUTING_REPORT.md",
    WORKSPACE_ROOT / "docs/V5_1_1_SECURITY_REPORT.md",
    WORKSPACE_ROOT / "docs/V5_1_1_FINAL_DECISION.md",
    # 12 Proof Deliverables
    WORKSPACE_ROOT / "proofs/v5_1_1_source_manifest.json",
    WORKSPACE_ROOT / "proofs/v5_1_1_task_level_results.json",
    WORKSPACE_ROOT / "proofs/v5_1_1_four_way_comparison.json",
    WORKSPACE_ROOT / "proofs/v5_1_1_leakage_audit.json",
    WORKSPACE_ROOT / "proofs/v5_1_1_blindness_tests.json",
    WORKSPACE_ROOT / "proofs/v5_1_1_candidate_attribution.json",
    WORKSPACE_ROOT / "proofs/v5_1_1_capability_gap.json",
    WORKSPACE_ROOT / "proofs/v5_1_1_routing.json",
    WORKSPACE_ROOT / "proofs/v5_1_1_security.json",
    WORKSPACE_ROOT / "proofs/v5_1_1_regressions.json",
    WORKSPACE_ROOT / "proofs/v5_1_1_stability.json",
    WORKSPACE_ROOT / "proofs/v5_1_1_final_scorecard.json",
]


def main():
    zip_path = WORKSPACE_ROOT / "v5_1_1.zip"
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
    artifact_zip = ARTIFACT_DIR / "v5_1_1.zip"
    shutil.copy2(zip_path, artifact_zip)
    print(f"Copied archive to artifact directory: {artifact_zip}")

    # Verify contents
    with zipfile.ZipFile(zip_path, "r") as zf:
        namelist = zf.namelist()
        print(f"Verification: {len(namelist)} files in archive. Subdirectories: {[n for n in namelist if '/' in n]}")
        assert len(namelist) == len(FILES_TO_PACK), f"Expected {len(FILES_TO_PACK)}, got {len(namelist)}"
        print("Archive successfully verified with all V5.1.1 release deliverables!")


if __name__ == "__main__":
    main()
