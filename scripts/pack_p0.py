"""Package Heimdallr P0 baseline deliverables into p0_baseline.zip."""

import os
from pathlib import Path
import shutil
import zipfile

WORKSPACE_ROOT = Path("/data/shared/project/PlayGround/Argus")
ARTIFACT_DIR = Path("/home/mihir/.gemini/antigravity-ide/brain/0d40961f-1ee0-42d3-8234-eed00d98d17f")

# Find latest complete baseline run dir containing manifest.json
candidate_runs = sorted([
    d for d in (WORKSPACE_ROOT / "artifacts/baselines").glob("p0_baseline_*")
    if (d / "manifest.json").exists()
])
BASELINE_RUN_DIR = candidate_runs[-1] if candidate_runs else WORKSPACE_ROOT / "artifacts"

FILES_TO_PACK = [
    BASELINE_RUN_DIR / "manifest.json",
    BASELINE_RUN_DIR / "environment.json",
    BASELINE_RUN_DIR / "test_results.json",
    BASELINE_RUN_DIR / "benchmark_results.json",
    BASELINE_RUN_DIR / "task_results.json",
    BASELINE_RUN_DIR / "performance.json",
    BASELINE_RUN_DIR / "limitations.json",
    BASELINE_RUN_DIR / "summary.md",
    WORKSPACE_ROOT / "src/argus/evals/baseline/manifest.py",
    WORKSPACE_ROOT / "src/argus/evals/baseline/runner.py",
    WORKSPACE_ROOT / "src/argus/evals/baseline/validation.py",
    WORKSPACE_ROOT / "src/argus/evals/baseline/__init__.py",
    WORKSPACE_ROOT / "src/argus/evals/v2/models.py",
    WORKSPACE_ROOT / "src/argus/evals/v2/graders.py",
    WORKSPACE_ROOT / "src/argus/evals/v2/runner.py",
    WORKSPACE_ROOT / "scripts/run_p0_baseline.py",
    WORKSPACE_ROOT / "tests/test_baseline_infrastructure.py",
    WORKSPACE_ROOT / "tests/test_eval_v2_evaluator_guard.py",
]


def main():
    zip_path = WORKSPACE_ROOT / "p0_baseline.zip"
    if zip_path.exists():
        zip_path.unlink()

    print(f"Creating P0 baseline archive: {zip_path}")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in FILES_TO_PACK:
            if not file_path.exists():
                raise FileNotFoundError(f"Missing deliverable: {file_path}")
            # Use relative path from workspace or baseline dir for clean archive structure
            if BASELINE_RUN_DIR in file_path.parents or file_path.parent == BASELINE_RUN_DIR:
                arcname = f"artifacts/{file_path.name}"
            else:
                arcname = str(file_path.relative_to(WORKSPACE_ROOT))
            zf.write(file_path, arcname=arcname)
            print(f"  Added: {arcname} ({file_path.stat().st_size:,} bytes)")

    # Copy to artifact directory
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    artifact_zip = ARTIFACT_DIR / "p0_baseline.zip"
    shutil.copy2(zip_path, artifact_zip)
    print(f"Copied archive to IDE artifact directory: {artifact_zip}")

    # Verify contents
    with zipfile.ZipFile(zip_path, "r") as zf:
        namelist = zf.namelist()
        print(f"Verification: {len(namelist)} files in archive.")
        for name in namelist:
            info = zf.getinfo(name)
            print(f"  - {name} ({info.file_size:,} bytes)")
        assert len(namelist) == len(FILES_TO_PACK), f"Expected {len(FILES_TO_PACK)}, got {len(namelist)}"
        print(f"\nArchive successfully verified with all {len(FILES_TO_PACK)} P0 deliverables!")


if __name__ == "__main__":
    main()
