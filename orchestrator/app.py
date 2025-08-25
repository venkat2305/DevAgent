from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uuid

app = FastAPI(title="DevAgent Orchestrator", version="0.1.0")

# In-memory job store for Step 1 (will replace with SQLite/Redis later)
JOBS: dict[str, dict] = {}


class ScheduleRequest(BaseModel):
    task: str


class ScheduleResponse(BaseModel):
    id: str


class StatusResponse(BaseModel):
    status: str


@app.post("/schedule", response_model=ScheduleResponse)
def schedule(req: ScheduleRequest):
    job_id = str(uuid.uuid4())
    # Step 1: only queue the job; no worker yet
    JOBS[job_id] = {"status": "queued", "task": req.task}
    return {"id": job_id}


@app.get("/status/{job_id}", response_model=StatusResponse)
def status(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return {"status": job["status"]}


# Optional health check for convenience
@app.get("/healthz")
def healthz():
    return {"ok": True}
