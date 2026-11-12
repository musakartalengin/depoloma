"""Entry point for a packaged build (PyInstaller) — same as `python -m depoloma`."""
import sys

from depoloma.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
