import modal
import json


image = modal.Image.from_dockerfile("Dockerfile")

app = modal.App("glassbox-agent", image=image)


def run_agent(job_id: str, task: str) -> dict:
    """Run agent and expose noVNC on :6080."""
    from main import run_agent_brain

    return run_agent_brain(job_id, task)


# Apply Modal decorator dynamically to optionally include port exposure
try:
    # Use Any to sidestep static checks for optional kwargs across SDK versions
    from typing import Any

    _func: Any = app.function
    _kwargs: dict[str, Any] = {"image": image,
                               "timeout": 3600, "cpu": 2, "memory": 4096}
    try:
        # type: ignore[misc]
        run_agent = _func(ports={6080: 6080}, **_kwargs)(run_agent)
    except TypeError:
        run_agent = _func(**_kwargs)(run_agent)
except Exception:
    # As a last resort, leave function undecorated to avoid import-time crashes
    pass


@app.local_entrypoint()
def main(job_id: str, task: str):
    """Local entrypoint to run the job and print pure JSON."""
    res = run_agent.remote(job_id, task)
    print(json.dumps(res))
