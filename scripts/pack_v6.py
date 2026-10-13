"""Package Heimdallr Vertical 6 deliverables into a single flat archive v6.zip."""

import os
from pathlib import Path
import shutil
import zipfile

WORKSPACE_ROOT = Path("/data/shared/project/PlayGround/Argus")
ARTIFACT_DIR = Path("/home/mihir/.gemini/antigravity-ide/brain/e083056e-870d-441d-9836-aa983eb6150d")

FILES_TO_PACK = [
    # 7 Documentation Deliverables
    WORKSPACE_ROOT / "docs/V6_CANDIDATE_LANDSCAPE.md",
    WORKSPACE_ROOT / "docs/V6_CAPABILITY_MATRIX.md",
    WORKSPACE_ROOT / "docs/V6_COMBINATION_EXPERIMENT.md",
    WORKSPACE_ROOT / "docs/V6_LICENSE_AND_SECURITY_AUDIT.md",
    WORKSPACE_ROOT / "docs/V6_BENCHMARK_REPORT.md",
    WORKSPACE_ROOT / "docs/V6_ARCHITECTURE_DECISION.md",
    WORKSPACE_ROOT / "docs/V6_FINAL_RECRUITMENT_REPORT.md",
    # 12 Proof Deliverables
    WORKSPACE_ROOT / "proofs/v6_candidate_inventory.json",
    WORKSPACE_ROOT / "proofs/v6_capability_mapping.json",
    WORKSPACE_ROOT / "proofs/v6_benchmark_results.json",
    WORKSPACE_ROOT / "proofs/v6_task_level_results.json",
    WORKSPACE_ROOT / "proofs/v6_candidate_attribution.json",
    WORKSPACE_ROOT / "proofs/v6_routing_results.json",
    WORKSPACE_ROOT / "proofs/v6_security_results.json",
    WORKSPACE_ROOT / "proofs/v6_regression_results.json",
    WORKSPACE_ROOT / "proofs/v6_final_scorecard.json",
    WORKSPACE_ROOT / "proofs/v6_scorecard.json",
    WORKSPACE_ROOT / "proofs/v6_requirements_coverage_matrix.json",
    WORKSPACE_ROOT / "proofs/v6_combination_benchmark.json",
]


def main():
    zip_path = WORKSPACE_ROOT / "v6.zip"
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
    artifact_zip = ARTIFACT_DIR / "v6.zip"
    shutil.copy2(zip_path, artifact_zip)
    print(f"Copied archive to artifact directory: {artifact_zip}")

    # Verify contents
    with zipfile.ZipFile(zip_path, "r") as zf:
        namelist = zf.namelist()
        print(f"Verification: {len(namelist)} files in archive. Subdirectories: {[n for n in namelist if '/' in n]}")
        assert len(namelist) == len(FILES_TO_PACK), f"Expected {len(FILES_TO_PACK)}, got {len(namelist)}"
        print(f"Archive successfully verified with all {len(FILES_TO_PACK)} V6 deliverables!")


if __name__ == "__main__":
    main()
