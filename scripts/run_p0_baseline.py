"""CLI entrypoint to execute Heimdallr P0 Reproducible System Baseline.

Usage:
  uv run python scripts/run_p0_baseline.py [--skip-tests] [--run-id RUN_ID] [--output-dir DIR]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add src to python path
src_dir = Path(__file__).resolve().parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from argus.evals.baseline.runner import BaselineRunner


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="run_p0_baseline",
        description="Heimdallr P0: Reproducible System Baseline Runner",
    )
    parser.add_argument("--run-id", type=str, default=None, help="Custom run identifier")
    parser.add_argument("--output-dir", type=str, default=None, help="Output directory for artifacts")
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Skip running full pytest suite to speed up benchmark generation",
    )
    parser.add_argument(
        "--skip-repeat",
        action="store_true",
        help="Skip repeat pass for stability evaluation",
    )

    args = parser.parse_args()

    runner = BaselineRunner(run_id=args.run_id, output_dir=args.output_dir)
    out = runner.run(
        include_tests=not args.skip_tests,
        include_repeat=not args.skip_repeat,
    )

    print(f"\n=======================================================")
    print(f"P0 BASELINE COMPLETE")
    print(f"Run ID: {out.run_id}")
    print(f"Artifacts: {out.output_dir}")
    print(f"Summary: {out.summary_path}")
    print(f"=======================================================\n")

    return out.exit_code


if __name__ == "__main__":
    sys.exit(main())
