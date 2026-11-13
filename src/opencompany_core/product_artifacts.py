"""Deterministic, zero-provider-cost Product & R&D starter-bundle generator.

The generated ZIP is a structured production blueprint, not a claim that a
finished commercial product or its visual/functional QA has been completed.
"""
from __future__ import annotations

import hashlib
import json
import os
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4


MAX_BRIEF_CHARS = 12000
MAX_ARCHIVE_BYTES = 2_000_000


def generate_product_blueprint(
    *, workflow_id: UUID | str, title: str, brief: str, artifact_root: Path,
) -> dict:
    title = title.strip()
    brief = brief.strip()
    if not title or len(title) > 240 or not brief or len(brief) > MAX_BRIEF_CHARS:
        raise ValueError("A valid product title and brief are required.")
    identifier = str(UUID(str(workflow_id)))
    artifact_root.mkdir(parents=True, exist_ok=True)
    target = artifact_root / f"{identifier}.zip"
    created_at = datetime.now(timezone.utc).isoformat()

    readme = f"""# {title}

## Bundle status

This is an automatically generated **production blueprint starter pack**.
It is not a finished commercial product. Complete the production tasks and
run the checks in QA_CHECKLIST.md before making any quality or compatibility
claims.

## Included files

- PRODUCT_SPEC.md — initial scope and acceptance criteria
- PRODUCTION_PLAN.md — staged production checklist
- QA_CHECKLIST.md — checks that still require execution
- LISTING_DRAFT.md — editable, unpublished listing copy
- SOURCE_BRIEF.md — the owner's original product brief
- manifest.json — bundle file list and generation metadata

No paid provider, external service, customer contact, publication, or purchase
was used to create this bundle.
"""
    specification = f"""# Product specification: {title}

## Owner-provided brief

{brief}

## Initial scope

This specification preserves the supplied brief as the source of truth. It
does not invent product features that were not specified. The production team
must resolve ambiguities before implementation.

## Acceptance criteria

- [ ] Every deliverable is traceable to a requirement in the source brief.
- [ ] All included files open and are readable.
- [ ] Product contents are original and do not include unlicensed third-party assets.
- [ ] Required target-platform compatibility is explicitly tested and recorded.
- [ ] Known limitations and untested claims are disclosed.
- [ ] The final package has a reproducible manifest and checksum.
"""
    plan = f"""# Production plan: {title}

1. **Clarify scope** — convert the source brief into measurable requirements.
2. **Create source assets** — produce only original assets required by the approved specification.
3. **Assemble the product** — use reproducible filenames and a clear folder structure.
4. **Run technical checks** — validate formats, references, archive integrity, and target-platform compatibility.
5. **Review quality** — inspect visual and functional quality; record checks separately from assumptions.
6. **Package** — include usage instructions, license/rights notes, version, and a manifest.
7. **Prepare listing draft** — describe only verified product features and limitations.
8. **Owner review** — obtain explicit approval before any listing or publication.

## Current status

Only this planning bundle has been generated. No product-specific source assets,
visual inspection, engine test, market validation, or legal review has been run.
"""
    qa = f"""# QA checklist: {title}

The following checks are **not executed** by generating this blueprint.

## Automated checks to implement/run

- [ ] ZIP integrity test
- [ ] Manifest completeness and checksum verification
- [ ] File extension and size validation
- [ ] Broken internal reference scan
- [ ] Duplicate filename scan

## Human or target-environment checks

- [ ] Visual quality and consistency
- [ ] Functional correctness in the target application/engine
- [ ] Accessibility and usability review
- [ ] Intellectual-property and license review
- [ ] Buyer-facing instructions and limitations review

Record every check as passed, failed, or untested. Never infer a pass from an
empty result or from the fact that the ZIP can be opened.
"""
    listing = f"""# Unpublished listing draft: {title}

**Status:** Draft only — not published or submitted.

## Product name

{title}

## Description

[Replace this section with a factual description after the actual product is
built and reviewed. Do not describe planned features as existing features.]

## Included files

[Insert the verified final deliverables and formats.]

## Compatibility

[State only platforms and versions that have been tested.]

## Limitations

[Disclose known limitations and any checks that remain untested.]

## Rights and licensing

[Confirm that all included material is original or properly licensed before
publication.]
"""
    source = f"""# Owner-provided source brief

## Product title

{title}

## Brief

{brief}
"""
    files = {
        "README.md": readme,
        "PRODUCT_SPEC.md": specification,
        "PRODUCTION_PLAN.md": plan,
        "QA_CHECKLIST.md": qa,
        "LISTING_DRAFT.md": listing,
        "SOURCE_BRIEF.md": source,
    }
    manifest = {
        "workflow_id": identifier,
        "title": title,
        "created_at": created_at,
        "bundle_type": "product_blueprint_starter_pack",
        "status": "blueprint_only_not_a_finished_product",
        "provider_cost_usd": 0,
        "external_actions_performed": False,
        "files": [
            {"path": name, "sha256": hashlib.sha256(value.encode("utf-8")).hexdigest(),
             "size_bytes": len(value.encode("utf-8"))}
            for name, value in files.items()
        ],
    }
    files["manifest.json"] = json.dumps(manifest, indent=2, sort_keys=True) + "\n"

    if target.exists():
        with zipfile.ZipFile(target, "r") as archive:
            if archive.testzip() is not None:
                raise ValueError("An existing generated blueprint ZIP failed integrity check.")
            file_count = len(archive.namelist())
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        return {
            "artifact_id": identifier, "file_name": f"{identifier}.zip",
            "path": str(target), "sha256": digest, "size_bytes": target.stat().st_size,
            "file_count": file_count, "bundle_type": "product_blueprint_starter_pack",
            "status": "blueprint_only_not_a_finished_product",
        }

    temporary = artifact_root / f".{identifier}.{uuid4().hex}.zip.tmp"
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, value in files.items():
                info = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, value.encode("utf-8"))
        if temporary.stat().st_size > MAX_ARCHIVE_BYTES:
            raise ValueError("Generated blueprint exceeds the archive size limit.")
        with zipfile.ZipFile(temporary, "r") as archive:
            bad_file = archive.testzip()
            if bad_file:
                raise ValueError(f"Generated ZIP failed integrity check: {bad_file}")
        try:
            # Hard-link creation is atomic and never overwrites a concurrent
            # winner for this workflow's immutable artifact identifier.
            os.link(temporary, target)
        except FileExistsError:
            pass
    finally:
        if temporary.exists():
            temporary.unlink()

    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    return {
        "artifact_id": identifier,
        "file_name": f"{identifier}.zip",
        "path": str(target),
        "sha256": digest,
        "size_bytes": target.stat().st_size,
        "file_count": len(files),
        "bundle_type": manifest["bundle_type"],
        "status": manifest["status"],
    }


def verify_product_blueprint(path: Path) -> dict:
    """Run deterministic archive, path, manifest and content-integrity checks."""
    passed: list[str] = []
    failed: list[str] = []
    untested = [
        "visual quality of any future product assets",
        "functional behavior in the target application or game engine",
        "intellectual-property and licensing review",
        "market demand and buyer willingness to pay",
    ]
    required = {
        "README.md", "PRODUCT_SPEC.md", "PRODUCTION_PLAN.md",
        "QA_CHECKLIST.md", "LISTING_DRAFT.md", "SOURCE_BRIEF.md", "manifest.json",
    }
    if not path.is_file():
        return {
            "passed_checks": passed,
            "failed_checks": ["artifact file is missing"],
            "untested_claims": untested,
        }
    if path.stat().st_size > MAX_ARCHIVE_BYTES:
        failed.append("archive exceeds the 2 MB size limit")
        return {"passed_checks": passed, "failed_checks": failed, "untested_claims": untested}
    try:
        with zipfile.ZipFile(path, "r") as archive:
            bad_member = archive.testzip()
            names = archive.namelist()
            if bad_member:
                failed.append(f"ZIP CRC check failed for {bad_member}")
            else:
                passed.append("ZIP CRC integrity")
            if len(names) != len(set(names)):
                failed.append("archive contains duplicate filenames")
            else:
                passed.append("unique archive filenames")
            if any(name.startswith("/") or chr(92) in name or ".." in Path(name).parts for name in names):
                failed.append("archive contains an unsafe path")
            else:
                passed.append("safe relative archive paths")
            if set(names) != required:
                failed.append("archive file set does not match the required blueprint structure")
            else:
                passed.append("required blueprint files present")
            total_size = sum(item.file_size for item in archive.infolist())
            if total_size > 5_000_000:
                failed.append("uncompressed archive size exceeds 5 MB")
            else:
                passed.append("uncompressed archive size within limit")
            if not failed:
                manifest = json.loads(archive.read("manifest.json"))
                declared = {item["path"]: item for item in manifest["files"]}
                for name in required - {"manifest.json"}:
                    if name not in declared:
                        failed.append(f"manifest entry missing for {name}")
                        continue
                    data = archive.read(name)
                    if hashlib.sha256(data).hexdigest() != declared[name]["sha256"]:
                        failed.append(f"manifest checksum mismatch for {name}")
                    elif len(data) != declared[name]["size_bytes"]:
                        failed.append(f"manifest size mismatch for {name}")
                if not failed:
                    passed.append("manifest SHA-256 and size checks")
            if not failed:
                readme = archive.read("README.md").decode("utf-8")
                qa = archive.read("QA_CHECKLIST.md").decode("utf-8")
                if "not a finished commercial product" in readme and "not executed" in qa:
                    passed.append("scope and untested-claim disclosures present")
                else:
                    failed.append("required scope/QA disclosures missing")
    except (OSError, zipfile.BadZipFile, KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
        failed.append(f"archive verification error: {type(exc).__name__}")
    return {
        "passed_checks": passed,
        "failed_checks": failed,
        "untested_claims": untested,
    }
