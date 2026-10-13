"""Package Heimdallr Vertical 5.2 final reports into a single flat archive v5.2_last.zip."""

import os
from pathlib import Path
import shutil
import zipfile

WORKSPACE_ROOT = Path("/data/shared/project/PlayGround/Argus")
ARTIFACT_DIR = Path("/home/mihir/.gemini/antigravity-ide/brain/e083056e-870d-441d-9836-aa983eb6150d")

FILES_TO_PACK = [
    # 7 Documentation Deliverables (Reports from this run)
    WORKSPACE_ROOT / "docs/V5_2_CAPABILITY_BOUNDARY.md",
    WORKSPACE_ROOT / "docs/V5_2_BENCHMARK_DESIGN.md",
    WORKSPACE_ROOT / "docs/V5_2_BENCHMARK_REPRODUCTION.md",
    WORKSPACE_ROOT / "docs/V5_2_SOURCE_AND_LEAKAGE_AUDIT.md",
    WORKSPACE_ROOT / "docs/V5_2_CAPABILITY_GAP_REPORT.md",
    WORKSPACE_ROOT / "docs/V5_2_SECURITY_AND_LICENSE_AUDIT.md",
    WORKSPACE_ROOT / "docs/V5_2_FINAL_DECISION.md",
]


def main():
    zip_path = WORKSPACE_ROOT / "v5.2_last.zip"
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
    artifact_zip = ARTIFACT_DIR / "v5.2_last.zip"
    shutil.copy2(zip_path, artifact_zip)
    print(f"Copied archive to artifact directory: {artifact_zip}")

    # Verify contents
    with zipfile.ZipFile(zip_path, "r") as zf:
        namelist = zf.namelist()
        print(f"Verification: {len(namelist)} files in archive. Subdirectories: {[n for n in namelist if '/' in n]}")
        assert len(namelist) == len(FILES_TO_PACK), f"Expected {len(FILES_TO_PACK)}, got {len(namelist)}"
        print("Archive successfully verified with 7 final V5.2 reports!")


if __name__ == "__main__":
    main()
