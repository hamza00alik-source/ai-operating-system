"""Validate inline dashboard JavaScript syntax with Node.js."""
from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

html = Path("src/ai_os/dashboard.html").read_text(encoding="utf-8")
scripts = re.findall(r"<script\b[^>]*>(.*?)</script\s*>", html, flags=re.IGNORECASE | re.DOTALL)
if not scripts:
    raise SystemExit("Dashboard contains no inline script blocks.")

for index, source in enumerate(scripts, start=1):
    with tempfile.NamedTemporaryFile("w", suffix=".js", encoding="utf-8") as handle:
        handle.write(source)
        handle.flush()
        result = subprocess.run(
            ["node", "--check", handle.name],
            capture_output=True,
            text=True,
            check=False,
        )
    if result.returncode:
        raise SystemExit(
            f"Dashboard script block {index} failed JavaScript syntax validation:\n"
            + result.stderr[-5000:]
        )

print(f"PASS: validated {len(scripts)} inline dashboard JavaScript block(s).")
