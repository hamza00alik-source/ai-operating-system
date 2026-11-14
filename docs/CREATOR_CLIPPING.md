# Creator clipping engine (local MVP)

OpenCompany has a local, permission-first clipping engine separate from LongCat text-to-video generation.

## What it does

- Accepts a local source video that the operator owns or is licensed to edit.
- Can transcribe locally with optional faster-whisper (CPU/int8).
- Ranks candidate moments using a transparent transcript heuristic.
- Exports vertical 1080x1920 MP4 clips with H.264/AAC.
- Writes SRT subtitle sidecars and a JSON manifest.
- Requires human review before any upload or publication.

The ranking heuristic is a starting point, not a claim that a clip will go viral. It uses transcript length/density, questions, punctuation, numbers and selected hook words. Human review remains necessary for context, factual accuracy, rights and campaign compliance.

## Requirements

- Python 3.11+
- FFmpeg and ffprobe installed and available on PATH.
- For automatic transcription: install the optional worker requirements. The first faster-whisper run downloads the selected model; CPU processing can be slow and model storage consumes disk space.
- Without faster-whisper, provide transcript segments in JSON.

## Run

    python -m ai_os.clipping --input /path/to/authorized-source.mp4 --output-dir ./clipping-output --clip-seconds 35 --max-clips 5

For manual or externally prepared transcript timestamps:

    python -m ai_os.clipping --input /path/to/authorized-source.mp4 --segments-json ./segments.json

Example segments.json:

    [
      {"start": 2.1, "end": 7.8, "text": "Why does this happen?"},
      {"start": 7.8, "end": 15.2, "text": "The surprising answer is ..."}
    ]

Outputs include vertical MP4s, SRT subtitle sidecars and manifest.json.

## Current limitations

- Center crop only; no face/speaker tracking or dynamic reframing.
- Subtitle files are generated as SRT sidecars; burn-in styling is not included.
- Candidate ranking is heuristic; no semantic LLM judge is connected.
- This MVP is a local CLI, not yet a cloud worker connected to the durable video-jobs queue or owner dashboard.
- It does not download URLs, bypass access controls, publish or submit campaigns.
- It has not yet been tested against the deployment environment or real campaign source footage.

## Safety

Only process footage you own or have explicit permission to edit and distribute. Campaign-specific rules override this general workflow. Do not publish automatically.
