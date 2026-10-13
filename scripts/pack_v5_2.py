"""Package Heimdallr Vertical 5.2 deliverables into a single flat archive v5_2.zip."""

import os
from pathlib import Path
import shutil
import zipfile

WORKSPACE_ROOT = Path("/data/shared/project/PlayGround/Argus")
ARTIFACT_DIR = Path("/home/mihir/.gemini/antigravity-ide/brain/e083056e-870d-441d-9836-aa983eb6150d")

FILES_TO_PACK = [
    # 7 Documentation Deliverables
    WORKSPACE_ROOT / "docs/V5_2_CAPABILITY_BOUNDARY.md",
    WORKSPACE_ROOT / "docs/V5_2_BENCHMARK_DESIGN.md",
    WORKSPACE_ROOT / "docs/V5_2_BENCHMARK_REPRODUCTION.md",
    WORKSPACE_ROOT / "docs/V5_2_SOURCE_AND_LEAKAGE_AUDIT.md",
    WORKSPACE_ROOT / "docs/V5_2_CAPABILITY_GAP_REPORT.md",
    WORKSPACE_ROOT / "docs/V5_2_SECURITY_AND_LICENSE_AUDIT.md",
    WORKSPACE_ROOT / "docs/V5_2_FINAL_DECISION.md",
    # 14 Proof Deliverables
    WORKSPACE_ROOT / "proofs/v5_2_source_manifest.json",
    WORKSPACE_ROOT / "proofs/v5_2_leakage_audit.json",
    WORKSPACE_ROOT / "proofs/v5_2_task_definitions.json",
    WORKSPACE_ROOT / "proofs/v5_2_corpus_manifest.json",
    WORKSPACE_ROOT / "proofs/v5_2_raw_task_results.json",
    WORKSPACE_ROOT / "proofs/v5_2_four_way_comparison.json",
    WORKSPACE_ROOT / "proofs/v5_2_capability_gap_metrics.json",
    WORKSPACE_ROOT / "proofs/v5_2_causal_attribution.json",
    WORKSPACE_ROOT / "proofs/v5_2_routing_metrics.json",
    WORKSPACE_ROOT / "proofs/v5_2_security_results.json",
    WORKSPACE_ROOT / "proofs/v5_2_license_results.json",
    WORKSPACE_ROOT / "proofs/v5_2_regression_results.json",
    WORKSPACE_ROOT / "proofs/v5_2_stability_results.json",
    WORKSPACE_ROOT / "proofs/v5_2_final_scorecard.json",
]


def main():
    zip_path = WORKSPACE_ROOT / "v5_2.zip"
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
    artifact_zip = ARTIFACT_DIR / "v5_2.zip"
    shutil.copy2(zip_path, artifact_zip)
    print(f"Copied archive to artifact directory: {artifact_zip}")

    # Verify contents
    with zipfile.ZipFile(zip_path, "r") as zf:
        namelist = zf.namelist()
        print(f"Verification: {len(namelist)} files in archive. Subdirectories: {[n for n in namelist if '/' in n]}")
        assert len(namelist) == len(FILES_TO_PACK), f"Expected {len(FILES_TO_PACK)}, got {len(namelist)}"
        print("Archive successfully verified with all 21 V5.2 release deliverables!")


if __name__ == "__main__":
    main()
