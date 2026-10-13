#!/usr/bin/env python3
"""Heimdallr OSINT Terminal Script Executable.

Usage:
    uv run python scripts/osint_terminal.py
    uv run python scripts/osint_terminal.py --target "Apex Technologies Group Inc" --no-interactive
"""

import sys
from pathlib import Path

# Ensure src is on python path
src_dir = Path(__file__).resolve().parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from argus.terminal import main

if __name__ == "__main__":
    main()
