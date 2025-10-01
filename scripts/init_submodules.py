#!/usr/bin/env python3
"""Utility script to initialize all git submodules for this repository."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def run() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    try:
        subprocess.run(
            ["git", "submodule", "update", "--init", "--recursive"],
            cwd=repo_root,
            check=True,
        )
    except FileNotFoundError:
        print("Error: git executable not found. Please install Git and try again.", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as exc:
        print("Error initializing submodules. Please check the output above for details.", file=sys.stderr)
        return exc.returncode

    print("All submodules initialized successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
