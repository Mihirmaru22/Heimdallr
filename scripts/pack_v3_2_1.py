"""Package Heimdallr V3.2.1 deliverables into a single flat archive v3_2_1.zip."""

import os
from pathlib import Path
import shutil
import zipfile

WORKSPACE_ROOT = Path("/data/shared/project/PlayGround/Argus")
ARTIFACT_DIR = Path("/home/mihir/.gemini/antigravity-ide/brain/e083056e-870d-441d-9836-aa983eb6150d")

FILES_TO_PACK = [
    # Reports
    WORKSPACE_ROOT / "docs/V3_2_1_FINAL_VALIDATION_REPORT.md",
    WORKSPACE_ROOT / "docs/V3_2_1_VALIDATION_REPORT.md",
    WORKSPACE_ROOT / "docs/V3_2_1_REMEDIATION_REPORT.md",
    WORKSPACE_ROOT / "docs/V3_2_1_SECURITY_REPORT.md",
    WORKSPACE_ROOT / "docs/V3_2_1_ROUTING_REPORT.md",
    WORKSPACE_ROOT / "docs/V3_2_1_CANDIDATE_ATTRIBUTION.md",
    # Proofs
    WORKSPACE_ROOT / "proofs/v3_2_1_final_scorecard.json",
    WORKSPACE_ROOT / "proofs/v3_2_1_scorecard.json",
    WORKSPACE_ROOT / "proofs/v3_2_1_sanctions_benchmark.json",
    WORKSPACE_ROOT / "proofs/v3_2_1_routing.json",
    WORKSPACE_ROOT / "proofs/v3_2_1_security.json",
    WORKSPACE_ROOT / "proofs/v3_2_1_ablation.json",
    WORKSPACE_ROOT / "proofs/v3_2_1_attribution.json",
    WORKSPACE_ROOT / "proofs/v3_2_1_cross_specialist.json",
    WORKSPACE_ROOT / "proofs/v3_2_1_regressions.json",
    WORKSPACE_ROOT / "proofs/v3_2_1_stability.json",
    WORKSPACE_ROOT / "proofs/v3_2_1_leakage_audit.json",
    WORKSPACE_ROOT / "proofs/v3_2_1_trajectories.json",
]


def main():
    zip_path = WORKSPACE_ROOT / "v3_2_1.zip"
    if zip_path.exists():
        zip_path.unlink()

    print(f"Creating flat archive: {zip_path}")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in FILES_TO_PACK:
            if not file_path.exists():
                raise FileNotFoundError(f"Missing deliverable: {file_path}")
            # Add file flat (basename only, no directories)
            zf.write(file_path, arcname=file_path.name)
            print(f"  Added: {file_path.name} ({file_path.stat().st_size} bytes)")

    # Copy to artifact directory
    artifact_zip = ARTIFACT_DIR / "v3_2_1.zip"
    shutil.copy2(zip_path, artifact_zip)
    print(f"Copied archive to artifact directory: {artifact_zip}")

    # Verify contents
    with zipfile.ZipFile(zip_path, "r") as zf:
        namelist = zf.namelist()
        print(f"Verification: {len(namelist)} files in archive. Subdirectories: {[n for n in namelist if '/' in n]}")
        assert len(namelist) == len(FILES_TO_PACK)
        assert all("/" not in n for n in namelist)
    print("Archive verification passed successfully.")


if __name__ == "__main__":
    main()
