"""Load the bundled, non-executable MCP provider catalogue."""
from __future__ import annotations

import json
from pathlib import Path


def load_mcp_provider_catalog() -> dict:
    path = Path(__file__).with_name("mcp_provider_catalog.json")
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)
