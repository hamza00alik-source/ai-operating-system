import json
from pathlib import Path

from scripts.validate_agent_library import validate_library


def _make_library(root: Path) -> Path:
    library = root / "vendor" / "agency-agents"
    divisions = {f"division-{index:02d}": {} for index in range(18)}
    (library).mkdir(parents=True)
    (library / "divisions.json").write_text(
        json.dumps({"divisions": divisions}), encoding="utf-8"
    )
    ids = []
    for division_index, division in enumerate(divisions):
        directory = library / division
        directory.mkdir()
        count = 28 if division_index == 17 else 15
        for profile_index in range(count):
            agent_id = f"agent-{division_index:02d}-{profile_index:02d}"
            ids.append(agent_id)
            (directory / f"{agent_id}.md").write_text(
                f"---\nname: Agent {agent_id}\ndescription: Test specialist\n---\n\n# {agent_id}\n",
                encoding="utf-8",
            )
    docs = library / "strategy" / "runbooks"
    docs.mkdir(parents=True)
    (docs / "demo.md").write_text("# Demo runbook\n", encoding="utf-8")
    (library / "strategy" / "runbooks.json").write_text(
        json.dumps({"runbooks": [{
            "slug": "demo",
            "doc": "strategy/runbooks/demo.md",
            "roster": [{"agents": [ids[0]]}],
        }]}),
        encoding="utf-8",
    )
    return root


def test_agent_library_validator_accepts_complete_pinned_corpus(tmp_path):
    root = _make_library(tmp_path)
    assert validate_library(root) == []


def test_agent_library_validator_rejects_missing_frontmatter_and_unknown_runbook_agent(tmp_path):
    root = _make_library(tmp_path)
    library = root / "vendor" / "agency-agents"
    profile = next((library / "division-00").glob("*.md"))
    profile.write_text("# Missing metadata\n", encoding="utf-8")
    runbooks = library / "strategy" / "runbooks.json"
    payload = json.loads(runbooks.read_text(encoding="utf-8"))
    payload["runbooks"][0]["roster"][0]["agents"] = ["not-a-real-agent"]
    runbooks.write_text(json.dumps(payload), encoding="utf-8")

    errors = validate_library(root)
    assert any("missing required frontmatter" in error for error in errors)
    assert any("unknown agent ID" in error for error in errors)
