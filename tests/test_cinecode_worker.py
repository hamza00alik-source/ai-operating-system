import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from workers import cinecode_worker as worker


def test_workspace_rejects_non_uuid_job_ids(tmp_path):
    with pytest.raises(worker.WorkerError, match="invalid job identifier"):
        worker._safe_workspace(tmp_path, "../../outside")


def test_workspace_is_created_under_configured_root(tmp_path):
    workspace = worker._safe_workspace(tmp_path, "2e8c0e1a-5d35-4a3c-9e5a-5c6e8f35b001")
    assert workspace.parent == tmp_path.resolve()
    assert workspace.is_dir()


def test_agent_environment_does_not_receive_worker_or_owner_secrets(monkeypatch):
    monkeypatch.setenv("VIDEO_CINECODE_WORKER_TOKEN", "must-not-leak")
    monkeypatch.setenv("AI_OS_API_KEY", "must-not-leak-either")
    monkeypatch.setenv("CODEX_HOME", "/tmp/codex-home")
    env = worker._agent_env()
    assert "VIDEO_CINECODE_WORKER_TOKEN" not in env
    assert "AI_OS_API_KEY" not in env
    assert env["CODEX_HOME"] == "/tmp/codex-home"


def test_prompt_treats_job_brief_as_untrusted_and_requires_fixed_output():
    prompt = worker._prompt({
        "prompt": "A cinematic mountain film",
        "parameters": {"aspect_ratio": "16:9"},
        "cost_basis": "pre-approved local compute",
    })
    assert "untrusted creative input" in prompt
    assert "output/final.mp4" in prompt
    assert "A cinematic mountain film" in prompt
    assert "non-interactive" in prompt
    assert '"mode": "quick"' in prompt
    assert "AskUserQuestion" in prompt
    assert "output/report.md" in prompt


def test_copy_cinecode_skips_git_and_symlinks(tmp_path):
    source = tmp_path / "source"
    workspace = tmp_path / "workspace"
    source.mkdir()
    workspace.mkdir()
    (source / ".git").mkdir()
    (source / "project.md").write_text("Cinecode instructions", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("private", encoding="utf-8")
    try:
        (source / "private-link").symlink_to(outside)
    except OSError:
        pytest.skip("symlinks are unavailable on this platform")
    worker._copy_cinecode(source, workspace)
    assert (workspace / "cinecode-kit" / "project.md").read_text(encoding="utf-8") == "Cinecode instructions"
    assert (workspace / "AGENTS.md").is_file()
    assert "non-interactive" in (workspace / "AGENTS.md").read_text(encoding="utf-8")
    assert not (workspace / "cinecode-kit" / ".git").exists()
    assert not (workspace / "cinecode-kit" / "private-link").exists()


def test_validate_mp4_requires_video_stream_and_enforces_duration(tmp_path, monkeypatch):
    workspace = tmp_path / "job"
    output = workspace / "output"
    output.mkdir(parents=True)
    artifact = output / "final.mp4"
    artifact.write_bytes(b"test-mp4")
    fake = SimpleNamespace(
        returncode=0,
        stdout=json.dumps({
            "format": {"duration": "12.5", "format_name": "mov,mp4"},
            "streams": [{"codec_type": "video", "width": 1920, "height": 1080}],
        }),
    )
    monkeypatch.setattr(worker.subprocess, "run", lambda *args, **kwargs: fake)
    metadata = worker._validate_mp4(artifact, workspace, "ffprobe", 60, 1024)
    assert metadata["duration_seconds"] == 12.5
    assert metadata["width"] == 1920
    assert metadata["engine"] == "cinecode"


def test_validate_mp4_rejects_overlong_video(tmp_path, monkeypatch):
    workspace = tmp_path / "job"
    output = workspace / "output"
    output.mkdir(parents=True)
    artifact = output / "final.mp4"
    artifact.write_bytes(b"test-mp4")
    fake = SimpleNamespace(
        returncode=0,
        stdout=json.dumps({
            "format": {"duration": "61", "format_name": "mov,mp4"},
            "streams": [{"codec_type": "video", "width": 1920, "height": 1080}],
        }),
    )
    monkeypatch.setattr(worker.subprocess, "run", lambda *args, **kwargs: fake)
    with pytest.raises(worker.WorkerError, match="fit the duration limit"):
        worker._validate_mp4(artifact, workspace, "ffprobe", 60, 1024)



def test_validate_mp4_rejects_non_mp4_container_even_with_video_stream(tmp_path, monkeypatch):
    workspace = tmp_path / "job"
    output = workspace / "output"
    output.mkdir(parents=True)
    artifact = output / "final.mp4"
    artifact.write_bytes(b"test-media")
    fake = SimpleNamespace(
        returncode=0,
        stdout=json.dumps({
            "format": {"duration": "12.5", "format_name": "matroska,webm"},
            "streams": [{"codec_type": "video", "width": 1280, "height": 720}],
        }),
    )
    monkeypatch.setattr(worker.subprocess, "run", lambda *args, **kwargs: fake)
    with pytest.raises(worker.WorkerError, match="video stream and fit the duration limit"):
        worker._validate_mp4(artifact, workspace, "ffprobe", 60, 1024)
