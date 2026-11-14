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


## Durable queue worker integration

The API supports a separate `creator-clipping` provider on the existing
owner-approved video job queue. This worker claims only that provider; it does
not consume LongCat generation jobs.

Configure the worker host:

- `OPENCOMPANY_API_URL`: deployed OpenCompany API base URL.
- `VIDEO_WORKER_TOKEN`: same worker secret configured on the API.
- `CLIPPING_INPUT_DIR`: directory containing owner-uploaded/licensed source
  files, mounted on the worker host.
- `CLIPPING_OUTPUT_DIR`: persistent output directory (optional).
- `VIDEO_WORKER_ID`: unique worker identifier (optional).

Install the project and optional transcription dependency, and install FFmpeg
and ffprobe on the worker host. Run:

    python workers/creator_clipping_worker.py

Create a video job with provider `creator-clipping`, a prompt describing the
task, explicit cost estimate/budget/cost basis, and parameters such as:

    {
      "source_path": "campaign-source.mp4",
      "clip_seconds": 35,
      "whisper_model": "small"
    }

The source_path is resolved under CLIPPING_INPUT_DIR; path traversal outside
that directory is rejected. The worker produces and uploads one highest-ranked
candidate MP4 per approved job. SRT and manifest sidecars remain on the worker
output volume for now. The API stores the uploaded MP4 as the job artifact.

This is a CPU-capable worker, but Whisper model inference and FFmpeg rendering
can be slow. The first Whisper run downloads a model. Do not treat a free-tier
cloud host as guaranteed to provide enough RAM, disk, CPU time or persistent
storage. No cloud worker has been deployed or connected automatically.
