import modal
import json


image = modal.Image.from_dockerfile("Dockerfile")

app = modal.App("glassbox-agent", image=image)

# Shared dict to publish session metadata (e.g., VNC URL) by job_id
SESSION_META = modal.Dict.from_name("glassbox-session-meta", create_if_missing=True)


def _run_impl(job_id: str, task: str) -> dict:
    """Core implementation shared by all entry points."""
    from main import run_agent_brain

    # Expose the noVNC port publicly; publish the URL for the orchestrator
    try:
        with modal.forward(6080) as tunnel:
            try:
                SESSION_META[job_id] = {"vnc_url": tunnel.url}
            except Exception:
                pass
            return run_agent_brain(job_id, task)
    finally:
        # Best-effort cleanup of metadata
        try:
            del SESSION_META[job_id]
        except Exception:
            pass


# Define two functions so orchestrator can look up either name
def run_job(job_id: str, task: str) -> dict:
    """Run job and expose noVNC on :6080 while executing."""
    return _run_impl(job_id, task)


def run_agent(job_id: str, task: str) -> dict:
    """Alias for run_job; kept for compatibility."""
    return _run_impl(job_id, task)


# Apply Modal decorator dynamically to optionally include port exposure for both
try:
    # Use Any to sidestep static checks for optional kwargs across SDK versions
    from typing import Any

    _func: Any = app.function
    _kwargs: dict[str, Any] = {"image": image, "timeout": 3600, "cpu": 2, "memory": 4096}
    try:
        # type: ignore[misc]
        run_job = _func(ports={6080: 6080}, **_kwargs)(run_job)
        run_agent = _func(ports={6080: 6080}, **_kwargs)(run_agent)
    except TypeError:
        run_job = _func(**_kwargs)(run_job)
        run_agent = _func(**_kwargs)(run_agent)
except Exception:
    # As a last resort, leave functions undecorated to avoid import-time crashes
    pass


@app.local_entrypoint()
def main(job_id: str, task: str):
    """Local entrypoint to run the job and print pure JSON."""
    res = run_job.remote(job_id, task)
    print(json.dumps(res))
