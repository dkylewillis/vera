from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    workbench = Path(__file__).with_name("workbench.py")
    return subprocess.call([sys.executable, "-m", "streamlit", "run", str(workbench)])


__all__ = ["main"]
