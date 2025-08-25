import modal
import json


image = modal.Image.from_dockerfile("Dockerfile")

app = modal.App("glassbox-agent", image=image)


@app.function(cpu=0.5, memory=512, timeout=600)
def run_job(job_id: str, task: str) -> dict:
    # Execute the simple agent brain and return artifact inline
    from main import run_agent_brain

    result = run_agent_brain(job_id, task)
    return result


@app.local_entrypoint()
def main(job_id: str, task: str):
    """Local entrypoint to run the job and print pure JSON."""
    res = run_job.remote(job_id, task)
    print(json.dumps(res))
