"""CPU-friendly creator clipping worker for the durable OpenCompany video queue.

The worker processes only owner-approved creator-clipping jobs. Source footage
must already exist in CLIPPING_INPUT_DIR and be owned/licensed for editing.
"""
import http.client
import json
import os
import time
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from ai_os.clipping import process_video

API = os.environ["OPENCOMPANY_API_URL"].rstrip("/")
WORKER_TOKEN = os.environ["VIDEO_WORKER_TOKEN"]
WORKER_ID = os.getenv("VIDEO_WORKER_ID", f"clipper-{os.uname().nodename}")
INPUT_DIR = Path(os.environ["CLIPPING_INPUT_DIR"]).resolve()
OUTPUT_DIR = Path(os.getenv("CLIPPING_OUTPUT_DIR", "./clipping-output")).resolve()
POLL_SECONDS = int(os.getenv("VIDEO_WORKER_POLL_SECONDS", "5"))
LEASE_SECONDS = int(os.getenv("VIDEO_JOB_LEASE_SECONDS", "180"))
MAX_UPLOAD_BYTES = 300 * 1024 * 1024


def request_json(path, payload=None, lease=None):
    data = None if payload is None else json.dumps(payload).encode()
    headers = {"X-Video-Worker-Token": WORKER_TOKEN, "Content-Type": "application/json"}
    if lease:
        headers["X-Job-Lease"] = lease
    req = urllib.request.Request(API + path, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=60) as response:
        raw = response.read()
        return json.loads(raw) if raw else {}


def safe_source_path(value):
    if not value:
        raise ValueError("Approved job parameters must include source_path.")
    candidate = (INPUT_DIR / str(value)).resolve()
    if candidate != INPUT_DIR and INPUT_DIR not in candidate.parents:
        raise ValueError("source_path must stay inside CLIPPING_INPUT_DIR.")
    if not candidate.is_file():
        raise FileNotFoundError(f"Authorized source file not found: {candidate}")
    return candidate


def upload_artifact(job_id, lease, path):
    size = path.stat().st_size
    if size <= 0 or size > MAX_UPLOAD_BYTES:
        raise ValueError(f"Generated MP4 size is invalid: {size} bytes")
    with path.open("rb") as stream:
        head = stream.read(12)
        if len(head) < 12 or head[4:8] != b"ftyp":
            raise ValueError("Generated output is not a valid MP4 container")
    target = urllib.parse.urlsplit(API)
    if target.scheme not in ("https", "http") or not target.hostname:
        raise ValueError("OPENCOMPANY_API_URL must be an absolute HTTP(S) URL")
    connection_type = http.client.HTTPSConnection if target.scheme == "https" else http.client.HTTPConnection
    connection = connection_type(target.hostname, target.port, timeout=180)
    endpoint = target.path.rstrip("/") + f"/video/worker/jobs/{job_id}/artifact"
    if target.query:
        endpoint += "?" + target.query
    headers = {"X-Video-Worker-Token": WORKER_TOKEN, "X-Job-Lease": lease,
               "Content-Type": "video/mp4", "Content-Length": str(size), "Connection": "close"}
    try:
        connection.putrequest("PUT", endpoint)
        for name, value in headers.items():
            connection.putheader(name, value)
        connection.endheaders()
        with path.open("rb") as stream:
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                connection.send(chunk)
        response = connection.getresponse()
        raw = response.read()
        if response.status < 200 or response.status >= 300:
            raise RuntimeError(f"Artifact upload failed: HTTP {response.status}: {raw.decode('utf-8', errors='replace')[:1000]}")
        return json.loads(raw) if raw else {}
    finally:
        connection.close()


def heartbeat_loop(job_id, lease, stop, cancellation):
    while not stop.wait(25):
        try:
            result = request_json(f"/video/worker/jobs/{job_id}/heartbeat",
                                  {"progress": 15, "message": "Creator clipping in progress"}, lease)
            if result.get("cancel_requested"):
                cancellation.set()
                return
        except Exception:
            cancellation.set()
            return


def main():
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Creator clipping worker {WORKER_ID} ready; input={INPUT_DIR}; API={API}", flush=True)
    while True:
        try:
            job = request_json("/video/worker/claim",
                               {"worker_id": WORKER_ID, "lease_seconds": LEASE_SECONDS,
                                "provider": "creator-clipping"})
        except urllib.error.HTTPError as exc:
            print(f"claim failed: HTTP {exc.code}", flush=True)
            time.sleep(POLL_SECONDS)
            continue
        if not job or not job.get("id"):
            time.sleep(POLL_SECONDS)
            continue
        job_id, lease = job["id"], job["lease_token"]
        stop, cancellation = threading.Event(), threading.Event()
        hb = threading.Thread(target=heartbeat_loop, args=(job_id, lease, stop, cancellation), daemon=True)
        hb.start()
        try:
            params = job.get("parameters") or {}
            source = safe_source_path(params.get("source_path"))
            output_dir = OUTPUT_DIR / job_id
            manifest = process_video(
                source=source,
                output_dir=output_dir,
                clip_seconds=float(params.get("clip_seconds", 35)),
                max_clips=1,
                model_name=str(params.get("whisper_model", "small")),
            )
            if cancellation.is_set():
                request_json(f"/video/worker/jobs/{job_id}/fail",
                             {"error": "Cancellation requested or worker heartbeat lost", "retryable": False}, lease)
                continue
            if not manifest:
                raise RuntimeError("No eligible clip candidates were produced.")
            video_path = output_dir / manifest[0]["video"]
            # Keep sidecar and manifest on the worker volume; return their metadata
            # with the MP4 result record for the owner review screen.
            result = upload_artifact(job_id, lease, video_path)
            print(f"Completed {job_id}: {result.get('result_uri')}", flush=True)
        except Exception as exc:
            try:
                request_json(f"/video/worker/jobs/{job_id}/fail",
                             {"error": f"{type(exc).__name__}: {exc}", "retryable": True}, lease)
            except Exception as report_exc:
                print(f"Could not report worker failure: {report_exc}", flush=True)
            print(f"Job {job_id} failed: {exc}", flush=True)
        finally:
            stop.set()
            hb.join(timeout=2)


if __name__ == "__main__":
    main()
