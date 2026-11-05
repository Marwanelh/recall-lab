"""Allow `python -m recall_lab` with no install step. See ADR-0006."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
