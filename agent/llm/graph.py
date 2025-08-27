from __future__ import annotations

import base64
import os
from pathlib import Path
from shutil import make_archive
from typing import Any, Dict

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.runnables import RunnableConfig
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver
import atexit
import contextlib

from .schema import State, RouterAction
from .tools import ToolEnv, make_tools


SYSTEM_TEXT = (
    "You are a precise coding agent.\n"
    "Return only tool selections as structured output.\n"
    "Tools available: shell, fs_read, fs_write, scaffold, done.\n"
    "Use 'scaffold' with recipe_id 'react-vite-js' to create React projects.\n"
    "Never suggest risky shell commands; keep to the job workspace.\n"
)


def _default_job_dir() -> Path:
    if os.path.exists("/job") or os.environ.get("MODAL_ENVIRONMENT"):
        return Path("/job")
    return Path.cwd() / "test_job"


def _safe_json_fragment(d: Dict[str, Any]) -> str:
    try:
        import json

        return json.dumps(d, ensure_ascii=False)[:20000]
    except Exception:
        return str(d)[:20000]


def _package_outputs(work_dir: Path, output_dir: Path) -> tuple[str, str]:
    # Prefer a directory with package.json
    app_dir: Path | None = None
    for c in work_dir.iterdir():
        if c.is_dir() and (c / "package.json").exists():
            app_dir = c
            break
    if app_dir is None:
        base = output_dir / "artifact"
        archive_path = make_archive(str(base), "zip", root_dir=str(work_dir))
        filename = "artifact.zip"
    else:
        base = output_dir / app_dir.name
        archive_path = make_archive(str(base), "zip", root_dir=str(app_dir))
        filename = f"{app_dir.name}.zip"
    b64 = base64.b64encode(Path(archive_path).read_bytes()).decode("ascii")
    return filename, b64


_CM_CLEANUPS = []  # hold __exit__ callbacks for context-managed resources


def _make_checkpointer(db_path: Path):
    """Return a SqliteSaver instance, compatible with multiple LangGraph versions."""
    # Try modern API: may return a context manager
    try:
        cm = SqliteSaver.from_conn_string(str(db_path))
        # If it's already a usable saver, return it
        if hasattr(cm, "get_next_version"):
            return cm
        # Otherwise, treat as context manager
        if hasattr(cm, "__enter__") and hasattr(cm, "__exit__"):
            saver = cm.__enter__()
            # Ensure the context is exited on process shutdown
            def _cleanup():
                with contextlib.suppress(Exception):
                    cm.__exit__(None, None, None)

            _CM_CLEANUPS.append(_cleanup)
            atexit.register(_cleanup)
            return saver
    except Exception:
        pass

    # Fallback: older API may allow direct constructor
    try:
        return SqliteSaver(str(db_path))  # type: ignore[arg-type]
    except Exception:
        return None


def build_graph(job_id: str, task: str):
    job_dir = _default_job_dir()
    work_dir = job_dir / "workdir"
    output_dir = job_dir / "output"
    logs_dir = job_dir / "logs"
    for d in (work_dir, output_dir, logs_dir):
        d.mkdir(parents=True, exist_ok=True)

    # LLM and tools
    model = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        temperature=0.1,
    )

    env = ToolEnv(job_dir=job_dir, work_dir=work_dir)
    tools = make_tools(env)
    structured = model.with_structured_output(RouterAction)

    # Initial state
    init_state = State(
        messages=[
            {"role": "system", "content": SYSTEM_TEXT},
            {"role": "user", "content": task},
        ],
        task=task,
    )

    # Node implementations
    def decide_action(state: State) -> Dict[str, Any]:
        print(f"[LOG] Deciding next action for task: {state.task}")
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", SYSTEM_TEXT),
                ("human", "{task}"),
            ]
        )
        chain = prompt | structured
        action: RouterAction = chain.invoke({"task": state.task})
        print(f"[LOG] Decided action: {action}")
        return {"pending_action": action}

    def run_shell(state: State) -> Dict[str, Any]:
        action = state.pending_action
        assert action is not None and action.tool == "shell"
        cmd = getattr(action.args, "command", None)
        print(f"[LOG] Calling shell tool with command: {cmd}")
        res = tools[0].invoke({"command": cmd})
        print(f"[LOG] Shell tool output: {res}")
        return {"tool_result": res}

    def run_fs_read(state: State) -> Dict[str, Any]:
        action = state.pending_action
        assert action is not None and action.tool == "fs_read"
        path = getattr(action.args, "path", None)
        print(f"[LOG] Calling fs_read tool with path: {path}")
        res = tools[1].invoke({"path": path})
        print(f"[LOG] fs_read tool output: {res}")
        return {"tool_result": res}

    def run_fs_write(state: State) -> Dict[str, Any]:
        action = state.pending_action
        assert action is not None and action.tool == "fs_write"
        path = getattr(action.args, "path", None)
        content = getattr(action.args, "content", None)
        print(f"[LOG] Calling fs_write tool with path: {path}")
        res = tools[2].invoke({"path": path, "content": content})
        print(f"[LOG] fs_write tool output: {res}")
        return {"tool_result": res}

    def finish_done(state: State) -> Dict[str, Any]:
        action = state.pending_action
        assert action is not None and action.tool == "done"
        reason = getattr(action.args, "reason", None)
        print(f"[LOG] Calling done tool with reason: {reason}")
        res = tools[3].invoke({"reason": reason})
        print(f"[LOG] done tool output: {res}")
        return {"tool_result": res}

    def run_scaffold(state: State) -> Dict[str, Any]:
        action = state.pending_action
        assert action is not None and action.tool == "scaffold"
        recipe_id = getattr(action.args, "recipe_id", None)
        name = getattr(action.args, "name", None)
        print(f"[LOG] Calling scaffold tool with recipe_id: {recipe_id}, "
              f"name: {name}")
        res = tools[4].invoke({"recipe_id": recipe_id, "name": name})
        print(f"[LOG] scaffold tool output: {res}")
        return {"tool_result": res}

    def record_result(state: State) -> Dict[str, Any]:
        action = state.pending_action
        assert action is not None
        result = state.tool_result or {}
        print(f"[LOG] Recording result for tool: {action.tool}")
        action_json = _safe_json_fragment(action.model_dump())
        messages = list(state.messages)
        messages.append({"role": "assistant", "content": action_json})
        messages.append(
            {
                "role": "tool",
                "content": _safe_json_fragment(result),
            }
        )
        new_state = {
            "messages": messages,
            "actions_taken": [*state.actions_taken, action_json],
            "last_result": result,
            "pending_action": None,
            "tool_result": None,
        }
        # Mark completion either when the explicit done tool is used,
        # or when a tool returns a done hint (e.g., successful scaffold)
        if action.tool == "done" or bool(result.get("done")):
            new_state.update({"done": True, "reason": result.get("reason")})
        print(
            f"[LOG] New state after result: "
            f"done={new_state.get('done', False)}"
        )
        return new_state

    def maybe_interrupt(state: State) -> Dict[str, Any]:
        # Minimal stub: pass-through; policy enforced inside shell tool already
        print(
            "[LOG] maybe_interrupt called. State done: "
            f"{getattr(state, 'done', False)}"
        )
        return {}

    # Graph wiring
    sg = StateGraph(State)

    # Define nodes in the graph
    sg.add_node("decide_action", decide_action)
    sg.add_node("run_shell", run_shell)
    sg.add_node("run_fs_read", run_fs_read)
    sg.add_node("run_fs_write", run_fs_write)
    sg.add_node("finish_done", finish_done)
    sg.add_node("run_scaffold", run_scaffold)
    sg.add_node("record_result", record_result)
    sg.add_node("maybe_interrupt", maybe_interrupt)

    # Route from decision based on chosen tool
    def route(state: State):
        action = state.pending_action
        if action is None:
            return "decide_action"
        return action.tool

    sg.add_conditional_edges(
        "decide_action",
        route,
        {
            "shell": "run_shell",
            "fs_read": "run_fs_read",
            "fs_write": "run_fs_write",
            "done": "finish_done",
            "scaffold": "run_scaffold",
        },
    )

    for tool_node in (
        "run_shell",
        "run_fs_read",
        "run_fs_write",
        "finish_done",
        "run_scaffold",
    ):
        sg.add_edge(tool_node, "record_result")
        sg.add_edge("record_result", "maybe_interrupt")

    # Termination condition: stop if state.done
    def _should_end(state: State):
        return END if state.done else None

    sg.set_entry_point("decide_action")
    sg.add_conditional_edges(
        "maybe_interrupt",
        _should_end,
        {END: END, None: "decide_action"},
    )

    # Checkpointer
    chk_path = job_dir / "state.sqlite"
    checkpointer = _make_checkpointer(chk_path)
    # If checkpointer is unavailable, compile without it (no persistence across runs)
    if checkpointer is not None:
        app = sg.compile(checkpointer=checkpointer)
    else:
        app = sg.compile()

    return app, init_state, job_dir, work_dir, output_dir, logs_dir


def run_graph_agent(job_id: str, task: str) -> Dict[str, Any]:
    app, state, job_dir, work_dir, output_dir, logs_dir = build_graph(
        job_id, task
    )
    # Run until done (the tool ‘done’ will set done=True)
    # We cap to a reasonable number of steps using config if needed
    config = RunnableConfig(
        recursion_limit=40,
        configurable={
            "thread_id": job_id,        # stable per run/conversation
            "checkpoint_ns": "agent", # optional but recommended
        },
    )
    final_state: State = app.invoke(state, config=config)

    # Package outputs similar to previous implementation
    report_path = job_dir / "report.md"
    actions = "\n".join(final_state.actions_taken)
    report_path.write_text(
        f"# Job {job_id}\nTask: {task}\n\n## Actions\n{actions}\n",
        encoding="utf-8",
    )

    filename, b64 = _package_outputs(work_dir, output_dir)
    return {
        "success": True,
        "artifact_filename": filename,
        "artifact_b64": b64,
        "report_path": str(report_path),
        "logs_path": str(logs_dir),
    }


def resume_graph_agent(run_id: str, thread_id: str) -> Dict[str, Any]:
    # Placeholder for future resume API; not used by orchestrator yet
    return {"ok": False, "error": "resume not implemented in this build"}
