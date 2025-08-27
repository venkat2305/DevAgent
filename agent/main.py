from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict

# Add the current directory to the path for local execution
if __name__ == "__main__":
    sys.path.append(str(Path(__file__).parent))

from llm import run_graph_agent


def run_agent_brain(job_id: str, task: str) -> Dict:
    """Run the LangGraph-based agent for the given task.

    This replaces the legacy AgentBrain implementation.
    """
    return run_graph_agent(job_id, task)


if __name__ == "__main__":
    task = "Build me a todo app in React"
    print("Starting the Agent", task)
    res = run_agent_brain("test-job", task)
    print("Result keys:", list(res.keys()))
