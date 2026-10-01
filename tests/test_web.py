"""The Aid's JS smoke tests, executed by qjs (QuickJS, staged by flake.nix).

tests/test_web.js loads the DOM-free modules (palette, state, geo) for real
and syntax-parses the rest; this wrapper just enforces its exit code so the
pytest suite covers the UI source too.
"""

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.skipif(
    subprocess.run(["which", "qjs"], capture_output=True).returncode != 0,
    reason="qjs not available",
)
def test_web_modules():
    r = subprocess.run(
        ["qjs", str(ROOT / "tests" / "test_web.js")],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "web tests: all green" in r.stdout