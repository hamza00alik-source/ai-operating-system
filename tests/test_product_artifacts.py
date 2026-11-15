from pathlib import Path
from uuid import uuid4
import zipfile

from opencompany_core.product_artifacts import generate_outpost_pack, inspect_outpost_pack


def test_outpost_pack_generation_is_reproducible_and_passes_structural_qa(tmp_path):
    workflow_id = str(uuid4())
    first = generate_outpost_pack(workflow_id, tmp_path)
    assert len(first["artifacts"]) == 5
    assert first["qa"]["failed_checks"] == []
    assert len(first["qa"]["passed_checks"]) >= 4
    assert any("visual" in claim.lower() for claim in first["qa"]["untested_claims"])

    package = Path(first["root"]) / "package.zip"
    with zipfile.ZipFile(package) as archive:
        assert len([name for name in archive.namelist() if name.startswith("icons/")]) == 30
        assert archive.testzip() is None

    second = generate_outpost_pack(workflow_id, tmp_path)
    assert first["artifacts"] == second["artifacts"]
    assert inspect_outpost_pack(first["root"])["failed_checks"] == []


def test_outpost_pack_rejects_non_uuid_workflow_directory(tmp_path):
    try:
        generate_outpost_pack("../outside", tmp_path)
        assert False, "workflow path traversal must be rejected"
    except ValueError:
        pass
