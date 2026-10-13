"""Pack Heimdallr V3.2 specific deliverables into version-named flat zip archives.

Archives created:
1. v3_2_proofs.zip (and aliases: v3_2.zip, proofs_v3_2.zip)
   - Contains all V3.2 competition proofs, audits, benchmarks, ablation, trajectories,
     candidate profile, reproducibility metadata, and core reports.
   - Strictly flat (0 subdirectories).
2. v3_2_docs.zip (and alias: docs.zip)
   - Contains all V3.2 and repository documentation files flat.
3. proofs.zip and proof.zip (legacy backward-compatible aliases)
"""

from __future__ import annotations

import logging
from pathlib import Path
import shutil
import zipfile

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

WORKSPACE_ROOT = Path("/data/shared/project/PlayGround/Argus")
ARTIFACT_DIR = Path("/home/mihir/.gemini/antigravity-ide/brain/e083056e-870d-441d-9836-aa983eb6150d")
PROOFS_DIR = WORKSPACE_ROOT / "proofs"
DOCS_DIR = WORKSPACE_ROOT / "docs"

# V3.2 Core Deliverables
V3_2_PROOF_FILES = [
    # V3.2 Benchmark & Competition Deliverables
    PROOFS_DIR / "specialist_competition_results.json",
    PROOFS_DIR / "specialist_competition_benchmark.json",
    PROOFS_DIR / "specialist_competition_ablation.json",
    PROOFS_DIR / "specialist_competition_stability.json",
    PROOFS_DIR / "specialist_competition_trajectories.json",
    PROOFS_DIR / "specialist_competition_regressions.json",
    PROOFS_DIR / "specialist_competition_leakage_audit.json",
    PROOFS_DIR / "license_audit.json",
    PROOFS_DIR / "security_audit.json",
    PROOFS_DIR / "candidate_performance_profile.json",
    PROOFS_DIR / "reproducibility_metadata.json",
    # V3.2 Primary Reports
    DOCS_DIR / "V3_2_RECRUITMENT_REPORT.md",
    DOCS_DIR / "VERTICAL_4_SELECTION.md",
    DOCS_DIR / "V3_2_SYSTEM_VALIDATION_REPORT.md",
    DOCS_DIR / "V3_2_SYSTEM_LEAKAGE_AUDIT.md",
    # V3.2 System-Level Validation Deliverables
    PROOFS_DIR / "v3_2_system_scorecard.json",
    PROOFS_DIR / "v3_2_eval_v2_comparison.json",
    PROOFS_DIR / "v3_2_investigation_comparison.json",
    PROOFS_DIR / "v3_2_capability_match_comparison.json",
    PROOFS_DIR / "v3_2_candidate_attribution.json",
    PROOFS_DIR / "v3_2_ablation.json",
    PROOFS_DIR / "v3_2_routing_results.json",
    PROOFS_DIR / "v3_2_regressions.json",
    PROOFS_DIR / "v3_2_security_audit.json",
    PROOFS_DIR / "v3_2_leakage_audit.json",
    PROOFS_DIR / "v3_2_stability.json",
    PROOFS_DIR / "v3_2_trajectories.json",
]


def verify_strictly_flat(zip_path: Path) -> bool:
    """Verify that every entry in the archive has zero directories."""
    with zipfile.ZipFile(zip_path, "r") as zf:
        for name in zf.namelist():
            if "/" in name or "\\" in name:
                logger.error("Non-flat entry in %s: %s", zip_path.name, name)
                return False
    return True


def create_v3_2_archive(zip_dest: Path, include_all_proofs: bool = True) -> int:
    """Pack V3.2 deliverables into a strictly flat zip archive."""
    added = set()
    with zipfile.ZipFile(zip_dest, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        # 1. Add explicit V3.2 deliverables
        for f in V3_2_PROOF_FILES:
            if f.exists() and f.name not in added:
                zf.write(f, arcname=f.name)
                added.add(f.name)

        # 2. Add any remaining proofs in proofs/ directory
        if include_all_proofs and PROOFS_DIR.exists():
            for p in sorted(PROOFS_DIR.iterdir()):
                if p.is_file() and not p.name.startswith(".") and p.name not in added:
                    zf.write(p, arcname=p.name)
                    added.add(p.name)

    logger.info("Created %s with %d flat files", zip_dest.name, len(added))
    assert verify_strictly_flat(zip_dest), f"Archive {zip_dest} is not strictly flat!"
    return len(added)


def create_docs_archive(zip_dest: Path) -> int:
    """Pack docs directory into a strictly flat archive."""
    added = set()
    with zipfile.ZipFile(zip_dest, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(DOCS_DIR.iterdir()):
            if p.is_file() and not p.name.startswith(".") and p.name.endswith(".md"):
                zf.write(p, arcname=p.name)
                added.add(p.name)
    logger.info("Created %s with %d flat doc files", zip_dest.name, len(added))
    assert verify_strictly_flat(zip_dest), f"Archive {zip_dest} is not strictly flat!"
    return len(added)


def main() -> None:
    logger.info("Packing single versioned V3.2 archive...")
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    # Only ONE archive named after the version: v3_2.zip
    v3_2_zip_ws = WORKSPACE_ROOT / "v3_2.zip"
    count_v3_2 = create_v3_2_archive(v3_2_zip_ws, include_all_proofs=True)
    shutil.copy(v3_2_zip_ws, ARTIFACT_DIR / "v3_2.zip")

    logger.info("==================================================================")
    logger.info("SUCCESS: SINGLE V3.2 ARCHIVE CREATED")
    logger.info(" - %s (%d files, %d bytes)", v3_2_zip_ws, count_v3_2, v3_2_zip_ws.stat().st_size)
    logger.info(" - %s/v3_2.zip", ARTIFACT_DIR)
    logger.info("==================================================================")



if __name__ == "__main__":
    main()
