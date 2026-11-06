"""Validate the pinned Agency Agents corpus before tests and deployment.

This deliberately uses only the Python standard library so CI does not need a
YAML parser or network access. The parser validates the top-level scalar fields
consumed by ai_os.registry; it is not a general YAML implementation.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path


def _frontmatter(markdown: str) -> dict[str, str]:
    match = re.match(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", markdown, re.DOTALL)
    if not match:
        return {}
    values: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if not line or line[:1].isspace() or ":" not in line:
            continue
        key, value = line.split(":", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key.strip()] = value
    return values


def validate_library(root: Path, *, check_git_pin: bool = False) -> list[str]:
    errors: list[str] = []
    library = root / "vendor" / "agency-agents"
    divisions_file = library / "divisions.json"
    runbooks_file = library / "strategy" / "runbooks.json"

    if not divisions_file.is_file():
        return ["Agency Agents submodule is missing or not initialized: vendor/agency-agents"]
    try:
        divisions_payload = json.loads(divisions_file.read_text(encoding="utf-8"))
        divisions = divisions_payload["divisions"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        return [f"Invalid divisions.json: {exc}"]
    if not isinstance(divisions, dict) or not divisions:
        return ["divisions.json must contain a non-empty divisions object"]

    actual_divisions = {
        path.name for path in library.iterdir()
        if path.is_dir() and any(path.rglob("*.md"))
    }
    expected_divisions = set(divisions)
    if actual_divisions != expected_divisions:
        errors.append(
            "Division directory mismatch: "
            f"missing={sorted(expected_divisions - actual_divisions)}, "
            f"unexpected={sorted(actual_divisions - expected_divisions)}"
        )

    seen_ids: dict[str, str] = {}
    profile_count = 0
    for division in sorted(expected_divisions):
        directory = library / division
        if not directory.is_dir():
            continue
        profiles = sorted(directory.rglob("*.md"))
        if not profiles:
            errors.append(f"Division has no Markdown profiles: {division}")
        for profile in profiles:
            relative = profile.relative_to(library).as_posix()
            profile_count += 1
            metadata = _frontmatter(profile.read_text(encoding="utf-8"))
            for required in ("name", "description"):
                if not metadata.get(required, "").strip():
                    errors.append(f"{relative}: missing required frontmatter field '{required}'")
            agent_id = profile.stem
            if agent_id in seen_ids:
                errors.append(
                    f"Duplicate agent ID '{agent_id}': {seen_ids[agent_id]} and {relative}"
                )
            else:
                seen_ids[agent_id] = relative

    if len(expected_divisions) != 18:
        errors.append(f"Expected 18 divisions, found {len(expected_divisions)}")
    if profile_count != 283:
        errors.append(f"Expected 283 specialist profiles, found {profile_count}")

    if not runbooks_file.is_file():
        errors.append("Missing strategy/runbooks.json")
    else:
        try:
            runbooks_payload = json.loads(runbooks_file.read_text(encoding="utf-8"))
            runbooks = runbooks_payload["runbooks"]
            if not isinstance(runbooks, list) or not runbooks:
                raise ValueError("runbooks must be a non-empty list")
            seen_slugs: set[str] = set()
            for runbook in runbooks:
                slug = runbook.get("slug")
                if not isinstance(slug, str) or not slug or slug in seen_slugs:
                    errors.append(f"Invalid or duplicate runbook slug: {slug!r}")
                    continue
                seen_slugs.add(slug)
                doc = runbook.get("doc")
                if not isinstance(doc, str) or not (library / doc).is_file():
                    errors.append(f"Runbook '{slug}' references missing document: {doc!r}")
                for group in runbook.get("roster", []):
                    for agent_id in group.get("agents", []):
                        if agent_id not in seen_ids:
                            errors.append(
                                f"Runbook '{slug}' references unknown agent ID '{agent_id}'"
                            )
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            errors.append(f"Invalid strategy/runbooks.json: {exc}")

    if check_git_pin:
        try:
            expected = subprocess.run(
                ["git", "ls-tree", "HEAD", "vendor/agency-agents"],
                cwd=root, check=True, capture_output=True, text=True,
            ).stdout.strip().split()
            actual = subprocess.run(
                ["git", "-C", str(library), "rev-parse", "HEAD"],
                cwd=root, check=True, capture_output=True, text=True,
            ).stdout.strip()
            if len(expected) < 3 or expected[0] != "160000" or expected[1] != "commit":
                errors.append("vendor/agency-agents is not recorded as a Git submodule commit")
            elif expected[2] != actual:
                errors.append(
                    f"Submodule checkout {actual} does not match repository pin {expected[2]}"
                )
        except (OSError, subprocess.CalledProcessError) as exc:
            errors.append(f"Could not verify Agency Agents Git pin: {exc}")

    return errors


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    errors = validate_library(root, check_git_pin=True)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("Agency Agents validation passed: 18 divisions, 283 profiles, runbooks, and Git pin.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
