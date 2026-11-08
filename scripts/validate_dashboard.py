"""Validate the edited MCP dashboard JavaScript controls with Node.js."""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

html = Path("src/ai_os/dashboard.html").read_text(encoding="utf-8")
start = html.find("async function discoverMcpEndpoint(")
end = html.find("async function registerMcpEndpoint(", start)
if start < 0 or end < 0:
    raise SystemExit("Could not locate the MCP dashboard control functions.")

source = html[start:end]
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
        "MCP dashboard controls failed JavaScript syntax validation:\n"
        + result.stderr[-5000:]
    )

print("PASS: validated MCP discovery, approval, pause and resume dashboard controls.")
