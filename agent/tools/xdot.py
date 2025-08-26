from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Literal


@dataclass
class XdotResult:
    ok: bool
    command: str
    exit_code: int
    stderr: str


class XdotTool:
    """Minimal wrapper around `xdotool` for GUI automation.

    Note: requires running inside the container with Xvfb and window manager.
    """

    def run(self, action: Literal["type", "key", "click"], args: str | int) -> dict:
        if action == "type":
            cmd = ["xdotool", "type", str(args)]
        elif action == "key":
            cmd = ["xdotool", "key", str(args)]
        elif action == "click":
            cmd = ["xdotool", "click", str(args)]
        else:
            return {"ok": False, "error": f"unknown action: {action}"}
        proc = subprocess.run(cmd, capture_output=True, text=True)
        return {
            "ok": proc.returncode == 0,
            "command": " ".join(cmd),
            "exit_code": proc.returncode,
            "stderr": proc.stderr[-4000:],
        }

