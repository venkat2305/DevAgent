import modal
import json


image = modal.Image.from_dockerfile("Dockerfile")

app = modal.App("glassbox-agent", image=image)

# Shared dict to publish session metadata (e.g., VNC URL) by job_id
SESSION_META = modal.Dict.from_name(
    "glassbox-session-meta",
    create_if_missing=True)


def run_job(job_id: str, task: str) -> dict:
    """Run job and expose noVNC on :6080 while executing."""
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


# Apply Modal decorator dynamically to include port exposure
try:
    from typing import Any

    _func: Any = app.function
    _kwargs: dict[str, Any] = {
        "image": image,
        "timeout": 3600,
        "cpu": 2,
        "memory": 4096,
        "secrets": [modal.Secret.from_name("gemini")],
    }
    try:
        run_job = _func(ports={6080: 6080}, **_kwargs)(run_job)
    except TypeError:
        run_job = _func(**_kwargs)(run_job)
except Exception:
    # As a last resort, leave function undecorated to avoid crashes
    pass


@app.local_entrypoint()
def main(job_id: str, task: str):
    """Local entrypoint to run the job and print pure JSON."""
    res = run_job.remote(job_id, task)
    print(json.dumps(res))
