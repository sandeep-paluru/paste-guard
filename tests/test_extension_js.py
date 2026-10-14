"""Runs the extension's content script tests (tests/js, jsdom + node:test) as part of plain `pytest`."""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

JS = Path(__file__).resolve().parent / "js"


def test_content_script_js():
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    if not (JS / "node_modules" / "jsdom").exists():
        npm = shutil.which("npm")
        if not npm:
            pytest.skip("npm is not installed")
        # npm is npm.cmd on Windows; CreateProcess needs shell=True for .cmd
        subprocess.run([npm, "install", "--no-audit", "--no-fund"], cwd=JS, check=True, capture_output=True, shell=(os.name == "nt"))
    r = subprocess.run([node, "--test"], cwd=JS, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-2000:]
