from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class ShellResult:
    command: str
    exit_code: int
    stdout: str
    stderr: str


class ShellTool:
    """Execute shell commands in a controlled way.

    Uses `bash -lc` to support chaining (e.g., `cd app && npm install`).
    The `cwd` is constrained by the caller (typically a job workdir).
    """

    def __init__(self, cwd: Path, timeout: int = 600):
        self.cwd = Path(cwd)
        self.timeout = timeout
        self.cwd.mkdir(parents=True, exist_ok=True)

    def run(self, command: str, timeout: Optional[int] = None) -> dict:
        t = timeout or self.timeout
        try:
            proc = subprocess.run(
                ["bash", "-lc", command],
                cwd=str(self.cwd),
                capture_output=True,
                text=True,
                timeout=t,
                check=False,
            )
            return {
                "ok": proc.returncode == 0,
                "command": command,
                "exit_code": proc.returncode,
                # trim to avoid overlong context
                "stdout": proc.stdout[-8000:],
                "stderr": proc.stderr[-8000:],
            }
        except subprocess.TimeoutExpired as e:
            return {
                "ok": False,
                "command": command,
                "exit_code": 124,
                "stdout": (e.stdout or "")[-8000:]
                if isinstance(e.stdout, str)
                else "",
                "stderr": f"timeout after {t}s",
            }


if __name__ == "__main__":
    from pathlib import Path

    # Pick a test working directory
    workdir = Path("/app/test_job/workdir")
    tool = ShellTool(cwd=workdir)

    # Example command — you can replace with anything
    cmd = "npx -y create-vite@latest venkat-app --template react"

    print(f"[RUNNING] {cmd}")
    result = tool.run(cmd)

    print("\n--- RESULT ---")
    print(f"Exit code: {result['exit_code']}")
    print("\n--- STDOUT ---")
    print(result["stdout"])
    print("\n--- STDERR ---")
    print(result["stderr"])
