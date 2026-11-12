"""Optional single-node LongCat-Video GPU worker.

Run inside the LongCat-Video Python/CUDA environment, not inside the API image.
The official demo script hardcodes its sample prompt, so this worker calls the
same public pipeline classes directly and passes the approved job prompt.
"""
import json
import os
import sys
import time
import uuid
import threading
import urllib.error
import urllib.request
from pathlib import Path

API = os.environ["OPENCOMPANY_API_URL"].rstrip("/")
WORKER_TOKEN = os.environ["VIDEO_WORKER_TOKEN"]
WORKER_ID = os.getenv("VIDEO_WORKER_ID", f"longcat-{os.uname().nodename}")
LONGCAT_REPO = Path(os.environ["LONGCAT_REPO_DIR"]).resolve()
sys.path.insert(0, str(LONGCAT_REPO))
CHECKPOINT = Path(os.environ["LONGCAT_CHECKPOINT_DIR"]).resolve()
OUTPUT_DIR = Path(os.getenv("LONGCAT_OUTPUT_DIR", "./outputs"))
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


def upload_artifact(job_id, lease, path):
    size = path.stat().st_size
    if size <= 0 or size > MAX_UPLOAD_BYTES:
        raise ValueError(f"Generated MP4 size is invalid: {size} bytes")
    with path.open("rb") as stream:
        head = stream.read(12)
        if len(head) < 12 or head[4:8] != b"ftyp":
            raise ValueError("Generated output is not a valid MP4 container")
        stream.seek(0)
        body = stream.read()
    headers = {
        "X-Video-Worker-Token": WORKER_TOKEN,
        "X-Job-Lease": lease,
        "Content-Type": "video/mp4",
    }
    req = urllib.request.Request(
        API + f"/video/worker/jobs/{job_id}/artifact",
        data=body, headers=headers, method="PUT",
    )
    with urllib.request.urlopen(req, timeout=180) as response:
        return json.loads(response.read())


def load_pipeline():
    import torch
    from transformers import AutoTokenizer, UMT5EncoderModel
    from longcat_video.pipeline_longcat_video import LongCatVideoPipeline
    from longcat_video.modules.scheduling_flow_match_euler_discrete import FlowMatchEulerDiscreteScheduler
    from longcat_video.modules.autoencoder_kl_wan import AutoencoderKLWan
    from longcat_video.modules.longcat_video_dit import LongCatVideoTransformer3DModel
    from longcat_video.context_parallel import context_parallel_util
    from longcat_video.context_parallel.context_parallel_util import init_context_parallel

    if not torch.cuda.is_available():
        raise RuntimeError("LongCat worker requires a CUDA GPU; no CPU fallback is attempted.")
    if not CHECKPOINT.is_dir():
        raise RuntimeError(f"LongCat checkpoint directory not found: {CHECKPOINT}")
    torch.cuda.set_device(int(os.getenv("LOCAL_RANK", "0")))
    import torch.distributed as dist
    if not dist.is_initialized():
        dist.init_process_group(backend="nccl")
    rank = dist.get_rank()
    world = dist.get_world_size()
    if world != 1:
        raise RuntimeError("This worker release supports one GPU process per worker. Multi-GPU distributed execution is not enabled.")
    init_context_parallel(context_parallel_size=1, global_rank=rank, world_size=1)
    split = context_parallel_util.get_optimal_split(context_parallel_util.get_cp_size())
    dtype = torch.bfloat16
    tokenizer = AutoTokenizer.from_pretrained(str(CHECKPOINT), subfolder="tokenizer", torch_dtype=dtype)
    text_encoder = UMT5EncoderModel.from_pretrained(str(CHECKPOINT), subfolder="text_encoder", torch_dtype=dtype)
    vae = AutoencoderKLWan.from_pretrained(str(CHECKPOINT), subfolder="vae", torch_dtype=dtype)
    scheduler = FlowMatchEulerDiscreteScheduler.from_pretrained(str(CHECKPOINT), subfolder="scheduler", torch_dtype=dtype)
    dit = LongCatVideoTransformer3DModel.from_pretrained(str(CHECKPOINT), subfolder="dit", cp_split_hw=split, torch_dtype=dtype)
    if os.getenv("LONGCAT_ENABLE_COMPILE", "false").lower() == "true":
        dit = torch.compile(dit)
    pipe = LongCatVideoPipeline(tokenizer=tokenizer,text_encoder=text_encoder,vae=vae,scheduler=scheduler,dit=dit)
    pipe.to(torch.cuda.current_device())
    return pipe, torch, rank


def heartbeat_loop(job_id, lease, stop, cancellation):
    first_heartbeat = True
    while not stop.wait(30):
        try:
            result = request_json(
                f"/video/worker/jobs/{job_id}/heartbeat",
                {"progress": 10, "message": "LongCat inference running"}
                if first_heartbeat else {"progress": None, "message": ""},
                lease,
            )
            first_heartbeat = False
            if result.get("cancel_requested"):
                # Keep renewing the lease until the current inference call returns;
                # otherwise another worker could duplicate a still-running GPU job.
                cancellation.set()
        except Exception:
            # Lease expiry is safer than continuing to report success after a lost API.
            cancellation.set()
            return


def generate_one(pipe, torch, job):
    from torchvision.io import write_video
    import numpy as np
    params = job.get("parameters") or {}
    width = int(params.get("width", 832))
    height = int(params.get("height", 480))
    frames = int(params.get("num_frames", 49))
    steps = int(params.get("num_inference_steps", 50))
    fps = int(params.get("fps", 15))
    guidance = float(params.get("guidance_scale", 4.0))
    if width not in (640, 832) or height not in (384, 480):
        raise ValueError("This worker supports only approved 640/832 by 384/480 output sizes.")
    if not 17 <= frames <= 129 or frames % 4 != 1:
        raise ValueError("num_frames must be 17–129 and congruent to 1 modulo 4.")
    if not 20 <= steps <= 60 or not 8 <= fps <= 30 or not 1 <= guidance <= 8:
        raise ValueError("Inference steps, FPS, or guidance scale is outside the safe range.")
    generator = torch.Generator(device="cuda").manual_seed(int(params.get("seed", 42)))
    output = pipe.generate_t2v(
        prompt=job["prompt"],
        negative_prompt=str(params.get("negative_prompt", "")),
        height=height,width=width,num_frames=frames,
        num_inference_steps=steps,guidance_scale=guidance,generator=generator,
    )[0]
    array = (np.asarray(output) * 255).clip(0,255).astype(np.uint8)
    out = OUTPUT_DIR / f"{job['id']}.mp4"
    write_video(str(out), torch.from_numpy(array), fps=fps, video_codec="libx264", options={"crf":"18"})
    del output, array
    torch.cuda.empty_cache()
    return out, {"width":width,"height":height,"frames":frames,"fps":fps,"format":"mp4","engine":"LongCat-Video"}


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    pipe, torch, rank = load_pipeline()
    print(f"LongCat worker {WORKER_ID} ready; API={API}", flush=True)
    while True:
        try:
            job = request_json("/video/worker/claim", {"worker_id":WORKER_ID,"lease_seconds":LEASE_SECONDS})
        except urllib.error.HTTPError as exc:
            print(f"claim failed: HTTP {exc.code}", flush=True)
            time.sleep(POLL_SECONDS)
            continue
        if not job or not job.get("id"):
            time.sleep(POLL_SECONDS)
            continue
        job_id, lease = job["id"], job["lease_token"]
        stop, cancellation = threading.Event(), threading.Event()
        hb = threading.Thread(target=heartbeat_loop,args=(job_id,lease,stop,cancellation),daemon=True)
        hb.start()
        try:
            output, metadata = generate_one(pipe,torch,job)
            if cancellation.is_set():
                request_json(f"/video/worker/jobs/{job_id}/fail",
                             {"error":"Cancellation requested or worker heartbeat lost during inference","retryable":False},lease)
                continue
            # Keep renewing the lease while the MP4 is uploaded; the API also
            # refreshes it while streaming and checks for owner cancellation.
            result = upload_artifact(job_id,lease,output)
            print(f"Completed {job_id}: {result.get('result_uri')}",flush=True)
        finally:
            stop.set()
            hb.join(timeout=2)
        except Exception as exc:
            stop.set(); hb.join(timeout=2)
            try:
                request_json(f"/video/worker/jobs/{job_id}/fail",
                             {"error":f"{type(exc).__name__}: {exc}","retryable":True},lease)
            except Exception as report_exc:
                print(f"Could not report worker failure: {report_exc}",flush=True)
            print(f"Job {job_id} failed: {exc}",flush=True)


if __name__ == "__main__":
    main()
