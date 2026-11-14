import shutil
import subprocess
from pathlib import Path

import pytest

from ai_os.clipping import (
    ClipCandidate,
    TranscriptSegment,
    rank_clip_candidates,
    render_clip,
    score_text,
    validate_segments,
)

def test_validate_segments_discards_invalid_and_sorts():
    items = [
        {"start": 4, "end": 7, "text": "second"},
        {"start": -1, "end": 2, "text": "invalid"},
        {"start": 1, "end": 3, "text": "first"},
        {"start": 8, "end": 8, "text": "zero"},
    ]
    result = validate_segments(items)
    assert [item.text for item in result] == ["first", "second"]

def test_score_text_rewards_hook_signals():
    assert score_text("Why is this the biggest mistake?") > score_text("This is a regular sentence")

def test_rank_candidates_returns_non_overlapping_clips():
    segments = [
        TranscriptSegment(0, 8, "Why is this important?"),
        TranscriptSegment(8, 18, "The surprising truth is that it works."),
        TranscriptSegment(40, 50, "This is another interesting moment!"),
        TranscriptSegment(50, 60, "Because the result changes everything."),
    ]
    result = rank_clip_candidates(segments, clip_seconds=25, max_clips=3, min_seconds=12)
    assert len(result) >= 1
    for left, right in zip(result, result[1:]):
        assert left.end <= right.start or left.start >= right.end


def test_ffmpeg_renders_vertical_mp4_when_available(tmp_path):
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        pytest.skip("FFmpeg and ffprobe are not installed")
    source = tmp_path / "source.mp4"
    output = tmp_path / "vertical.mp4"
    subprocess.run([
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "color=c=black:s=320x240:d=1",
        "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(source),
    ], check=True, capture_output=True)
    subtitles = tmp_path / "captions.srt"
    subtitles.write_text("1\\n00:00:00,000 --> 00:00:00,900\\nA test caption\\n", encoding="utf-8")
    render_clip(source, ClipCandidate(0, 1, 1.0, "test clip"), output, subtitles_path=subtitles)
    probe = subprocess.run([
        ffprobe, "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height", "-of", "json", str(output),
    ], check=True, capture_output=True, text=True)
    import json
    stream = json.loads(probe.stdout)["streams"][0]
    assert (stream["width"], stream["height"]) == (1080, 1920)
    assert output.stat().st_size > 0
