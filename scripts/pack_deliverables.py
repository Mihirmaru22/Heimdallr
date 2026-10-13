"""Pack deliverables into strictly flat zip archives (0 subdirectories).

Creates:
1. proofs.zip and proof.zip (containing all files from proofs/)
2. docs.zip (containing all markdown and doc files from docs/)
Saves them to workspace root and copies to artifact directory.
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


def pack_flat_zip(source_dir: Path, zip_dest: Path, filter_ext: tuple = ()) -> int:
    """Pack all files from source_dir into zip_dest strictly flat with 0 subdirectories."""
    count = 0
    with zipfile.ZipFile(zip_dest, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(source_dir.iterdir()):
            if p.is_file() and not p.name.startswith("."):
                if filter_ext and not p.name.endswith(filter_ext):
                    continue
                # arcname=p.name ensures 100% strictly flat structure
                zf.write(p, arcname=p.name)
                count += 1
    logger.info("Packed %d files into flat archive: %s", count, zip_dest)
    return count


def verify_strictly_flat(zip_path: Path) -> bool:
    """Verify that every entry in the zip file has 0 directories."""
    with zipfile.ZipFile(zip_path, "r") as zf:
        for name in zf.namelist():
            if "/" in name or "\\" in name:
                logger.error("Non-flat entry found in %s: %s", zip_path, name)
                return False
    logger.info("Verified strictly flat (0 subdirectories): %s", zip_path)
    return True


def main() -> None:
    # 1. Pack proofs.zip
    proofs_zip_ws = WORKSPACE_ROOT / "proofs.zip"
    count_proofs = pack_flat_zip(PROOFS_DIR, proofs_zip_ws)
    assert verify_strictly_flat(proofs_zip_ws)

    # 2. Duplicate to proof.zip
    proof_zip_ws = WORKSPACE_ROOT / "proof.zip"
    shutil.copy(proofs_zip_ws, proof_zip_ws)
    assert verify_strictly_flat(proof_zip_ws)

    # 3. Pack docs.zip
    docs_zip_ws = WORKSPACE_ROOT / "docs.zip"
    count_docs = pack_flat_zip(DOCS_DIR, docs_zip_ws)
    assert verify_strictly_flat(docs_zip_ws)

    # 4. Copy to Artifact directory
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy(proofs_zip_ws, ARTIFACT_DIR / "proofs.zip")
    shutil.copy(proof_zip_ws, ARTIFACT_DIR / "proof.zip")
    shutil.copy(docs_zip_ws, ARTIFACT_DIR / "docs.zip")

    logger.info("==================================================================")
    logger.info("SUCCESSFULLY PACKED DELIVERABLES:")
    logger.info(" - %s (%d files)", proofs_zip_ws, count_proofs)
    logger.info(" - %s (%d files)", proof_zip_ws, count_proofs)
    logger.info(" - %s (%d files)", docs_zip_ws, count_docs)
    logger.info("Copied to artifact directory: %s", ARTIFACT_DIR)
    logger.info("==================================================================")


if __name__ == "__main__":
    main()
