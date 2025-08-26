from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Literal


class CodeExecTool:
    """Run tiny snippets in Python or Node.

    Not sandboxed beyond the process level; use for small helpers only.
    """

    def __init__(self, cwd: Path):
        self.cwd = Path(cwd)
        self.cwd.mkdir(parents=True, exist_ok=True)

    def run(self, language: Literal["python", "node"], code: str, timeout: int = 120) -> dict:
        if language == "python":
            cmd = ["python3", "-c", code]
        elif language == "node":
            cmd = ["node", "-e", code]
        else:
            return {"ok": False, "error": f"unsupported language: {language}"}
        try:
            proc = subprocess.run(cmd, cwd=str(self.cwd), capture_output=True, text=True, timeout=timeout)
            return {
                "ok": proc.returncode == 0,
                "language": language,
                "exit_code": proc.returncode,
                "stdout": proc.stdout[-8000:],
                "stderr": proc.stderr[-8000:],
            }
        except subprocess.TimeoutExpired:
            return {"ok": False, "language": language, "exit_code": 124, "stderr": f"timeout after {timeout}s"}

