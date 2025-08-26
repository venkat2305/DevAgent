from __future__ import annotations

import base64
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from shutil import make_archive
from typing import Any, Optional

try:  # support both package and script import styles
    from .tools import ShellTool, FsTool, CodeExecTool  # type: ignore
except Exception:  # pragma: no cover
    from tools import ShellTool, FsTool, CodeExecTool  # type: ignore


SYSTEM_PROMPT = (
    "You are an autonomous software-building agent.\n"
    "You have access to tools for running shell commands, writing files, and reading files.\n\n"
    "Your task: build a working React \"todo app\" inside the container.\n\n"
    "Constraints:\n"
    "- Always respond with a single JSON object.\n"
    "- Do NOT include explanations or code fences.\n"
    "- Valid tools: [\"shell\", \"fs_write\", \"fs_read\", \"done\"].\n"
    "- Use `shell` for commands like npm, git, or bash commands.\n"
    "- Use `fs_write` to create or edit source files.\n"
    "- Use `fs_read` to inspect existing files.\n"
    "- When you are confident the app is scaffolded and built, use `done`.\n\n"
    "Examples:\n\n"
    "USER: Build me a todo app in React\n"
    "ASSISTANT:\n"
    '{"tool": "shell", "args": {"command": "npm create vite@latest todo-app -- --template react"}}\n\n'
    "USER: npm create vite failed: vite: not found\n"
    "ASSISTANT:\n"
    '{"tool": "shell", "args": {"command": "npm install -g create-vite && npm create vite@latest todo-app -- --template react"}}\n'
)


def _default_job_dir() -> Path:
    if os.path.exists("/job") or os.environ.get("MODAL_ENVIRONMENT"):
        return Path("/job")
    return Path.cwd() / "test_job"


def _b64_file(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def _safe_json(o: Any) -> str:
    try:
        return json.dumps(o, ensure_ascii=False)[:20000]
    except Exception:
        return str(o)[:20000]


@dataclass
class AgentConfig:
    model_name: str = "gemini-2.5-flash"
    max_steps: int = 20
    step_timeout: int = 900


class AgentBrain:
    def __init__(self, job_id: str, task: str, cfg: Optional[AgentConfig] = None):
        self.job_id = job_id
        self.task = task
        self.cfg = cfg or AgentConfig()
        self.job_dir = _default_job_dir()
        self.work_dir = self.job_dir / "workdir"
        self.output_dir = self.job_dir / "output"
        self.logs_dir = self.job_dir / "logs"
        self.report_path = self.job_dir / "report.md"
        for d in (self.work_dir, self.output_dir, self.logs_dir):
            d.mkdir(parents=True, exist_ok=True)

        # Tools
        self.shell = ShellTool(
            self.work_dir, timeout=min(self.cfg.step_timeout, 900))
        self.fs = FsTool(self.work_dir, allowed_root=self.job_dir)
        self.exec = CodeExecTool(self.work_dir)

        # Context/logging
        self.history: list[dict[str, Any]] = []

        # Emit an initial line to the demo VNC log if present
        try:
            with open("/tmp/agent.log", "a", encoding="utf-8") as f:
                f.write(f"[agent] job {job_id} starting: {task}\n")
        except Exception:
            pass

        # LLM setup (lazy)
        self._llm = None

    # --- LLM wiring ---
    def _ensure_llm(self):
        if self._llm is not None:
            return
        try:
            import google.generativeai as genai  # type: ignore

            api_key = os.environ.get("GEMINI_API_KEY")
            if not api_key:
                raise RuntimeError("GEMINI_API_KEY not set")
            genai.configure(api_key=api_key)
            self._llm = genai.GenerativeModel(self.cfg.model_name)
        except Exception as e:  # fallback if missing
            self._llm = None
            self._llm_error = str(e)

    def _ask_llm(self, context: str) -> dict:
        self._ensure_llm()
        if self._llm is None:
            # Fallback planner: a minimal scripted flow
            return self._fallback_plan()
        try:
            resp = self._llm.generate_content(context)
            text = resp.candidates[0].content.parts[0].text.strip()
            return json.loads(text)
        except Exception as e:
            return {"tool": "done", "args": {"reason": f"LLM error: {e}"}}

    # --- Fallback plan (no LLM) ---
    def _fallback_plan(self) -> dict:
        # Simple heuristic: if no app yet, scaffold it; else install; else build; then done
        app_dir = self.work_dir / "todo-app"
        if not app_dir.exists():
            # If previous attempt failed due to vite missing, try installing create-vite globally
            if self.history:
                last = self.history[-1]
                if (
                    isinstance(last, dict)
                    and last.get("action", {}).get("tool") == "shell"
                    and isinstance(last.get("result"), dict)
                    and not last["result"].get("ok")
                    and any(
                        s in (last["result"].get("stderr") or "")
                        for s in ["vite: not found", "create-vite: not found", "command not found"]
                    )
                ):
                    return {
                        "tool": "shell",
                        "args": {
                            "command": "npm install -g create-vite && npm create vite@latest todo-app -- --template react"
                        },
                    }
            return {
                "tool": "shell",
                "args": {
                    "command": "npm create vite@latest todo-app -- --template react"
                },
            }
        pkg = app_dir / "package.json"
        node_modules = app_dir / "node_modules"
        if pkg.exists() and not node_modules.exists():
            return {"tool": "shell", "args": {"command": "cd todo-app && npm install"}}
        dist = app_dir / "dist"
        if pkg.exists() and not dist.exists():
            return {"tool": "shell", "args": {"command": "cd todo-app && npm run build"}}
        return {"tool": "done", "args": {"reason": "fallback plan completed"}}

    # --- Logging helpers ---
    def _write_step_log(self, step_idx: int, content: str):
        path = self.logs_dir / f"step-{step_idx}.log"
        path.write_text(content, encoding="utf-8")

    # --- Execution loop ---
    def run(self) -> dict:
        context = f"{SYSTEM_PROMPT}\nUSER: {self.task}\n"
        done = False
        step = 0
        actions_taken: list[str] = []

        while not done and step < self.cfg.max_steps:
            step += 1
            action = self._ask_llm(context)
            tool = action.get("tool")
            args = action.get("args", {}) or {}
            actions_taken.append(_safe_json(action))

            # Execute tool
            if tool == "shell":
                cmd = str(args.get("command", ""))
                result = self.shell.run(cmd, timeout=self.cfg.step_timeout)
            elif tool == "fs_write":
                result = self.fs.write(
                    str(args.get("path", "")), str(args.get("content", "")))
            elif tool == "fs_read":
                result = self.fs.read(str(args.get("path", "")))
            elif tool == "done":
                done = True
                result = {"ok": True, "done": True,
                          "reason": args.get("reason", "")}
            else:
                result = {"ok": False, "error": f"unknown tool: {tool}"}

            # Record history and logs
            self.history.append(
                {"step": step, "action": action, "result": result})
            log_block = (
                f"Step {step}\n"
                f"Action: {_safe_json(action)}\n\n"
                f"Result: {_safe_json(result)}\n"
            )
            self._write_step_log(step, log_block)
            try:
                with open("/tmp/agent.log", "a", encoding="utf-8") as f:
                    f.write(f"[agent] step {step}: {tool}\n")
            except Exception:
                pass

            # Update LLM context
            context += f"TOOL RESULT: {_safe_json(result)}\n"

            # Simple stop condition on hard error from shell to avoid loops
            if tool == "shell" and result.get("exit_code") not in (0, None):
                # let LLM try to recover; fallback planner will also adjust
                context += f"ERROR: Command failed with exit {result.get('exit_code')}\n"

            # Safety: if LLM goes off rails, cap logs per step
            time.sleep(0.05)

        # Package outputs
        return self._finalize()

    # --- Packaging and report ---
    def _find_app_dir(self) -> Path | None:
        # Heuristic: prefer a top-level dir with package.json
        candidates = [p for p in self.work_dir.iterdir() if p.is_dir()]
        for c in candidates:
            if (c / "package.json").exists():
                return c
        return None

    def _finalize(self) -> dict:
        # Write report
        report_lines = [
            f"# Job {self.job_id} Report\n",
            f"Task: {self.task}\n\n",
            "## Actions\n",
        ]
        for h in self.history:
            report_lines.append(
                f"- Step {h['step']}: {_safe_json(h['action'])}\n")
        report_lines.append(
            "\n## Notes\n- Logs written to /job/logs/step-*.log\n")
        self.report_path.write_text("".join(report_lines), encoding="utf-8")

        # Determine what to zip
        app_dir = self._find_app_dir()
        if app_dir is not None:
            base = self.output_dir / app_dir.name
            archive_path = make_archive(
                str(base), "zip", root_dir=str(app_dir))
            filename = f"{app_dir.name}.zip"
        else:
            base = self.output_dir / "artifact"
            archive_path = make_archive(
                str(base), "zip", root_dir=str(self.work_dir))
            filename = "artifact.zip"

        b64 = _b64_file(Path(archive_path))
        return {
            "success": True,
            "artifact_filename": filename,
            "artifact_b64": b64,
            "report_path": str(self.report_path),
            "logs_path": str(self.logs_dir),
        }


def run_agent_brain(job_id: str, task: str) -> dict:
    """Compatibility wrapper used by modal_app.py and orchestrator.

    Instantiates AgentBrain and runs the main loop.
    """
    agent = AgentBrain(job_id, task)
    return agent.run()


if __name__ == "__main__":
    result = run_agent_brain("test-job", "Build me a todo app in React")
    print("Result keys:", list(result.keys()))
