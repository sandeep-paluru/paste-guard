"""Runs the extension's content script tests (tests/js, jsdom + node:test) as part of plain `pytest`."""
import shutil
import subprocess
from pathlib import Path

import pytest

JS = Path(__file__).resolve().parent / "js"


def test_content_script_js():
    if not shutil.which("node"):
        pytest.skip("node is not installed")
    if not (JS / "node_modules" / "jsdom").exists():
        if not shutil.which("npm"):
            pytest.skip("npm is not installed")
        subprocess.run(["npm", "install", "--no-audit", "--no-fund"], cwd=JS, check=True, capture_output=True)
    r = subprocess.run(["node", "--test"], cwd=JS, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-2000:]
