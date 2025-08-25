import modal


image = modal.Image.from_dockerfile("Dockerfile")

app = modal.App("glassbox-agent", image=image)


@app.function(cpu=0.5, memory=512, timeout=600)
def run_job(job_id: str, task: str) -> dict:
    # Execute the simple agent brain and return artifact inline
    from main import run_agent_brain

    result = run_agent_brain(job_id, task)
    return result
