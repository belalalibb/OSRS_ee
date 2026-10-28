"""``python -m osrs_ee <subcommand>`` — same entry point as the ``osrs-ee`` console script.

Useful when the script shim is not on PATH (fresh venv on Windows/PowerShell,
``pip install --user``). Behaviour and exit codes are identical to ``osrs-ee``.
"""
from __future__ import annotations

import sys

from osrs_ee.cli import main

if __name__ == "__main__":
    sys.exit(main())
