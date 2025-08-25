from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uuid
from typing import Any

# Modal is optional at import time (useful for local dev
# without modal installed)
try:
    import modal  # type: ignore
except Exception:  # pragma: no cover
    modal = None  # type: ignore

app = FastAPI(title="DevAgent Orchestrator", version="0.1.0")

# In-memory job store for Step 1 (will replace with SQLite/Redis later)
JOBS: dict[str, dict] = {}


def _get_modal_run_fn():
    """Return the Modal run_job function defined in the agent app."""
    if modal is None:
        raise RuntimeError(
            "modal is not installed; cannot schedule remote jobs"
        )
    # Expecting a function named run_job in app 'glassbox-agent'
    return modal.Function.lookup("glassbox-agent", "run_job")


class ScheduleRequest(BaseModel):
    task: str


class ScheduleResponse(BaseModel):
    id: str


class StatusResponse(BaseModel):
    status: str
    download: str | None = None


@app.post("/schedule", response_model=ScheduleResponse)
def schedule(req: ScheduleRequest):
    job_id = str(uuid.uuid4())
    JOBS[job_id] = {"status": "queued", "task": req.task}
    # Try spawning on Modal; if modal not configured, leave as queued
    try:
        run_fn = _get_modal_run_fn()
        handle = run_fn.spawn(job_id, req.task)
        JOBS[job_id]["handle"] = handle
        JOBS[job_id]["status"] = "running"
    except Exception as e:
        # Keep queued/failed info for visibility
        JOBS[job_id]["error"] = str(e)
    return {"id": job_id}


@app.get("/status/{job_id}", response_model=StatusResponse)
def status(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    handle: Any | None = job.get("handle")
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
    return {"status": job["status"], "download": download}


# Optional health check for convenience
@app.get("/healthz")
def healthz():
    return {"ok": True}
