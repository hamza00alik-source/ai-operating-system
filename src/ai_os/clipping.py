"""Local, permission-first short-form video clipping engine."""
from __future__ import annotations
import argparse, json, re, shutil, subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

@dataclass(frozen=True)
class TranscriptSegment:
    start: float
    end: float
    text: str

@dataclass(frozen=True)
class ClipCandidate:
    start: float
    end: float
    score: float
    text: str

def require_binary(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise RuntimeError(f"{name} is required but was not found on PATH.")
    return path

def validate_segments(items: Iterable[dict]) -> list[TranscriptSegment]:
    result = []
    for item in items:
        start, end = float(item["start"]), float(item["end"])
        text = str(item.get("text", "")).strip()
        if start < 0 or end <= start or not text:
            continue
        result.append(TranscriptSegment(start, end, text))
    return sorted(result, key=lambda x: x.start)

def score_text(text: str) -> float:
    """Transparent heuristic, not a claim of semantic/viral prediction."""
    clean = text.strip()
    words = re.findall(r"[\w']+", clean.lower())
    if not words:
        return 0.0
    score = min(len(words) / 18.0, 2.0)
    score += 1.2 if "?" in clean else 0.0
    score += 0.5 if any(ch.isdigit() for ch in clean) else 0.0
    hooks = {"why", "secret", "mistake", "never", "best", "worst", "because",
             "surprising", "important", "impossible", "actually", "truth"}
    score += min(sum(1 for word in words if word in hooks) * 0.35, 1.4)
    score += 0.3 if clean.endswith(("!", "?")) else 0.0
    return round(score, 3)

def rank_clip_candidates(segments: list[TranscriptSegment], clip_seconds: float = 35.0,
                         max_clips: int = 5, min_seconds: float = 12.0) -> list[ClipCandidate]:
    if not 10 <= clip_seconds <= 90:
        raise ValueError("clip_seconds must be between 10 and 90.")
    if not 1 <= max_clips <= 30:
        raise ValueError("max_clips must be between 1 and 30.")
    candidates = []
    for index, first in enumerate(segments):
        start = first.start
        chosen = [s for s in segments[index:] if s.start < start + clip_seconds]
        if not chosen:
            continue
        end = min(start + clip_seconds, max(s.end for s in chosen))
        if end - start < min_seconds:
            continue
        text = " ".join(s.text for s in chosen)
        density = sum(min(len(s.text.split()), 30) for s in chosen) / max(end - start, 1)
        score = score_text(text) + min(density / 5.0, 1.0)
        candidates.append(ClipCandidate(start, end, score, text))
    candidates.sort(key=lambda item: item.score, reverse=True)
    selected = []
    for candidate in candidates:
        if all(candidate.end <= old.start or candidate.start >= old.end for old in selected):
            selected.append(candidate)
        if len(selected) >= max_clips:
            break
    return sorted(selected, key=lambda item: item.start)

def transcribe_local(source: Path, model_name: str = "small") -> list[TranscriptSegment]:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError("Automatic transcription needs faster-whisper. Install workers/requirements-clipping.txt or supply --segments-json.") from exc
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    segments, _ = model.transcribe(str(source), vad_filter=True)
    return [TranscriptSegment(float(s.start), float(s.end), str(s.text).strip())
            for s in segments if str(s.text).strip()]

def write_srt(segments: list[TranscriptSegment], start: float, end: float, path: Path) -> None:
    def stamp(seconds: float) -> str:
        millis = int(round(max(0, seconds) * 1000))
        hours, millis = divmod(millis, 3600000)
        minutes, millis = divmod(millis, 60000)
        secs, millis = divmod(millis, 1000)
        return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"
    rows, index = [], 1
    for segment in segments:
        left, right = max(segment.start, start), min(segment.end, end)
        if right <= left:
            continue
        rows.extend([str(index), f"{stamp(left-start)} --> {stamp(right-start)}", segment.text, ""])
        index += 1
    path.write_text("\n".join(rows), encoding="utf-8")

def render_clip(
    source: Path, candidate: ClipCandidate, output: Path, fps: int = 30,
    subtitles_path: Path | None = None,
) -> None:
    ffmpeg = require_binary("ffmpeg")
    output.parent.mkdir(parents=True, exist_ok=True)
    duration = candidate.end - candidate.start
    filters = ["scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"]
    if subtitles_path is not None:
        if not subtitles_path.is_file():
            raise FileNotFoundError(f"Subtitle file not found: {subtitles_path}")
        subtitle_file = str(subtitles_path.resolve()).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
        filters.append(f"subtitles='{subtitle_file}'")
    command = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{candidate.start:.3f}", "-i", str(source),
        "-t", f"{duration:.3f}", "-vf", ",".join(filters), "-r", str(fps),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(output),
    ]
    subprocess.run(command, check=True, capture_output=True, text=True)

def process_video(source: Path, output_dir: Path, segments: list[TranscriptSegment] | None = None,
                  clip_seconds: float = 35.0, max_clips: int = 5, model_name: str = "small") -> list[dict]:
    require_binary("ffmpeg")
    require_binary("ffprobe")
    if not source.is_file():
        raise FileNotFoundError(f"Source video not found: {source}")
    if segments is None:
        segments = transcribe_local(source, model_name=model_name)
    if not segments:
        raise RuntimeError("No speech segments found; provide timestamps or another source.")
    candidates = rank_clip_candidates(segments, clip_seconds, max_clips)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = []
    for index, candidate in enumerate(candidates, 1):
        stem = f"clip_{index:02}"
        video_path, srt_path = output_dir / f"{stem}.mp4", output_dir / f"{stem}.srt"
        write_srt(segments, candidate.start, candidate.end, srt_path)
        render_clip(source, candidate, video_path, subtitles_path=srt_path)
        manifest.append({"video": video_path.name, "subtitles": srt_path.name,
            "start": round(candidate.start, 3), "end": round(candidate.end, 3),
            "score": candidate.score, "selection_method": "transparent_transcript_heuristic",
            "review_required": True})
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest

def main() -> None:
    parser = argparse.ArgumentParser(description="Create vertical short clips from an authorized local video.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("clipping-output"))
    parser.add_argument("--segments-json", type=Path)
    parser.add_argument("--clip-seconds", type=float, default=35)
    parser.add_argument("--max-clips", type=int, default=5)
    parser.add_argument("--whisper-model", default="small")
    args = parser.parse_args()
    segments = None
    if args.segments_json:
        segments = validate_segments(json.loads(args.segments_json.read_text(encoding="utf-8")))
    manifest = process_video(args.input, args.output_dir, segments, args.clip_seconds, args.max_clips, args.whisper_model)
    print(json.dumps(manifest, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
