from __future__ import annotations

import re
from typing import Any, Dict
from pathlib import Path

from langchain_core.tools import tool
from pydantic import BaseModel, Field

# Always import from the top-level "tools" package that lives next to "llm"
# This works both locally (running main.py) and inside the container (/app)
from tools import ShellTool, FsTool  # type: ignore


# --- Safety: deny/allow policy for shell ---
_DENY_PATTERNS = [
    r"\brm\s+-rf\b",
    r"\bmkfs\b",
    r"\bdd\s+if=",
    r"\bchmod\s+777\b",
    r"\bchown\s+-R\b",
    r"\bmount\b",
    r"\bssh\b",
    r"/(etc|root)\b",
    r"\b(adduser|useradd|deluser|userdel)\b",
    r":\(\)\{:\|:&\};:",  # fork bomb
    r"\b(curl|wget)\s+http",
]


def is_risky_command(cmd: str) -> bool:
    s = cmd.strip()
    for pat in _DENY_PATTERNS:
        if re.search(pat, s, flags=re.IGNORECASE):
            return True
    return False


class ShellInput(BaseModel):
    command: str = Field(..., description="Shell command to execute")


class FsReadInput(BaseModel):
    path: str = Field(..., description="File path to read")


class FsWriteInput(BaseModel):
    path: str = Field(..., description="File path to write")
    content: str = Field(..., description="File content to write")


class DoneInput(BaseModel):
    reason: str = Field(..., description="Completion reason")


class ToolEnv:
    def __init__(self, job_dir: Path, work_dir: Path):
        self.job_dir = Path(job_dir)
        self.work_dir = Path(work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.shell = ShellTool(self.work_dir)
        self.fs = FsTool(self.work_dir, allowed_root=self.job_dir)


def make_tools(env: ToolEnv):
    @tool("shell", args_schema=ShellInput)
    def shell_tool(command: str) -> Dict[str, Any]:
        """Run a safe shell command in the job workdir."""
        if is_risky_command(command):
            return {
                "ok": False,
                "exit_code": 126,
                "stderr": "blocked by policy: risky command",
                "command": command,
            }
        return env.shell.run(command)

    @tool("fs_read", args_schema=FsReadInput)
    def fs_read_tool(path: str) -> Dict[str, Any]:
        """Read a text file under the job directory."""
        return env.fs.read(path)

    @tool("fs_write", args_schema=FsWriteInput)
    def fs_write_tool(path: str, content: str) -> Dict[str, Any]:
        """Write a text file under the job directory."""
        return env.fs.write(path, content)

    @tool("done", args_schema=DoneInput)
    def done_tool(reason: str) -> Dict[str, Any]:
        """Signal completion of the task."""
        return {"done": True, "reason": reason}

    return [shell_tool, fs_read_tool, fs_write_tool, done_tool]
