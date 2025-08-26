from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
import uuid
from typing import Any
import modal

app = FastAPI(title="DevAgent Orchestrator", version="0.1.0")

# In-memory job store (will replace with SQLite/Redis later)
JOBS: dict[str, dict] = {}


def _get_modal_run_fn():
    """Return the Modal function defined in the agent app."""
    if modal is None:
        raise RuntimeError(
            "modal is not installed; cannot schedule remote jobs"
        )
    return modal.Function.from_name("glassbox-agent", "run_job")


class ScheduleRequest(BaseModel):
    task: str


class ScheduleResponse(BaseModel):
    id: str


class StatusResponse(BaseModel):
    status: str
    download: str | None = None
    vnc_url: str | None = None


@app.post("/schedule", response_model=ScheduleResponse)
def schedule(req: ScheduleRequest):
    job_id = str(uuid.uuid4())
    JOBS[job_id] = {"status": "queued", "task": req.task}
    # Try spawning on Modal; if modal not configured, leave as queued
    try:
        run_fn = _get_modal_run_fn()
        print("run fn", run_fn)
        handle = run_fn.spawn(job_id, req.task)
        print("handle", handle)
        JOBS[job_id]["handle"] = handle
        JOBS[job_id]["status"] = "running"
    except Exception as e:
        # Keep queued/failed info for visibility
        JOBS[job_id]["error"] = str(e)
        print("error", e)
    return {"id": job_id}


@app.get("/status/{job_id}", response_model=StatusResponse)
def status(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    handle: Any | None = job.get("handle")
    vnc_url: str | None = None
    # Try to fetch live VNC URL published by agent via Modal Dict
    if modal is not None:
        try:
            session_meta = modal.Dict.from_name(
                "glassbox-session-meta", create_if_missing=True)
            meta = session_meta.get(job_id)
            if isinstance(meta, dict):
                vnc_url = meta.get("vnc_url")
        except Exception:
            vnc_url = None
    if handle and job.get("status") in {"queued", "running"}:
        try:
            # Non-blocking poll: returns immediately if not done
            result = handle.get(timeout=0)
            job["status"] = "complete"
            job["result"] = result
            # Persist artifact to a temp file and expose a simple download path
            if isinstance(result, dict) and "artifact_b64" in result:
                import base64
                from pathlib import Path
                artifacts_root = Path("/tmp/orchestrator_artifacts")
                artifacts_root.mkdir(parents=True, exist_ok=True)
                out_path = artifacts_root / f"{job_id}-artifact.zip"
                data = base64.b64decode(result["artifact_b64"])  # type: ignore
                out_path.write_bytes(data)
                job["download_path"] = str(out_path)
        except Exception:
            job["status"] = "running"
    download = None
    if job.get("status") == "complete" and job.get("download_path"):
        # For now we just echo the file path; a proper
        # file-serving route can be added later
        download = job.get("download_path")
    return {"status": job["status"], "download": download, "vnc_url": vnc_url}


@app.get("/download/{job_id}")
def download(job_id: str):
    """Serve the artifact zip for a completed job.

    Returns 404 if the job is unknown or not complete, or the artifact is missing.
    """
    # Primary: serve from in-memory job record
    job = JOBS.get(job_id)
    path: str | None = None
    if job:
        path = job.get("download_path")

    # Fallback: if job record not present (e.g., server restarted),
    # try the conventional path used by the status handler.
    if not path:
        from pathlib import Path
        p = Path("/tmp/orchestrator_artifacts") / f"{job_id}-artifact.zip"
        if p.exists():
            path = str(p)

    if not path:
        raise HTTPException(
            status_code=404, detail="artifact not available yet")

    try:
        return FileResponse(path, media_type="application/zip", filename=f"{job_id}.zip")
    except Exception:
        raise HTTPException(status_code=404, detail="artifact file missing")


@app.get("/healthz")
def healthz():
    return {"ok": True}
