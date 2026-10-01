"""Pack the Aid into one self-contained HTML file.

``web/`` holds the UI source as plain files — a shell ``index.html`` that
references ``style.css``, the ``app/*.js`` modules and the data script by
relative path (so the dev loop is: run stage 2 once, then edit ``web/`` and
reload — script tags work over file://, fetch() does not). ``pack`` walks
those references in document order and inlines them, producing
``output/bakers_aid.html``: no build system, no server, byte-deterministic.
"""

from __future__ import annotations

import os
import re

WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "web")

_SCRIPT_RE = re.compile(r'<script src="([^"]+)"></script>')
_STYLE_RE = re.compile(r'<link rel="stylesheet" href="([^"]+)"\s*/?>')


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def pack(outdir: str) -> str:
    """Inline web/ + data.js into ``<outdir>/bakers_aid.html``; return its path."""
    html = _read(os.path.join(WEB_DIR, "index.html"))

    def inline_script(m: re.Match) -> str:
        src = m.group(1)
        if src.endswith("data.js"):
            # The data comes from THIS run's outdir (web/index.html references
            # the default location only for the dev loop).
            body = _read(os.path.join(outdir, "aid", "data.js"))
        else:
            body = _read(os.path.join(WEB_DIR, src))
        assert "</script" not in body.lower(), f"{src} contains </script>"
        return f"<script>\n{body}</script>"

    def inline_style(m: re.Match) -> str:
        return f"<style>\n{_read(os.path.join(WEB_DIR, m.group(1)))}</style>"

    html = _SCRIPT_RE.sub(inline_script, html)
    html = _STYLE_RE.sub(inline_style, html)

    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, "bakers_aid.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(html)
    return path