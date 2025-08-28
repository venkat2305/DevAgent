from __future__ import annotations

from typing import Any, Dict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, END

from .schema import State, RouterAction
from .tools import ToolEnv, make_tools
from .helpers import default_job_dir, package_outputs, make_checkpointer
from .llm_wrappers import RateLimitedLLM, FailoverLLM
from .nodes import (
    decide_action, run_shell, run_fs_read, run_fs_write,
    finish_done, run_scaffold, record_result, maybe_interrupt
)


def build_graph(job_id: str, task: str):
    job_dir = default_job_dir()
    work_dir = job_dir / "workdir"
    output_dir = job_dir / "output"
    logs_dir = job_dir / "logs"
    for d in (work_dir, output_dir, logs_dir):
        d.mkdir(parents=True, exist_ok=True)

    # Create rate-limited LLM with fallback
    flash = RateLimitedLLM("gemini-2.5-flash", rpm=10, temperature=0.1)
    pro = RateLimitedLLM("gemini-2.5-pro", rpm=5, temperature=0.1)

    # Optional: Add Groq as fallback (no rate limits typically)
    # groq = RateLimitedLLM("llama-3.1-70b-versatile", rpm=100,
    #                       provider="groq", temperature=0.1)
    # model = FailoverLLM([flash, groq, pro])

    model = FailoverLLM([flash, pro])

    env = ToolEnv(job_dir=job_dir, work_dir=work_dir)
    tools = make_tools(env)
    structured = model.with_structured_output(RouterAction)

    init_state = State(
        messages=[{"role": "user", "content": task}],
        task=task,
    )

    # Create closures that capture tools and structured model
    def decide_action_node(state: State) -> Dict[str, Any]:
        return decide_action(state, structured)

    def run_shell_node(state: State) -> Dict[str, Any]:
        return run_shell(state, tools)

    def run_fs_read_node(state: State) -> Dict[str, Any]:
        return run_fs_read(state, tools)

    def run_fs_write_node(state: State) -> Dict[str, Any]:
        return run_fs_write(state, tools)

    def finish_done_node(state: State) -> Dict[str, Any]:
        return finish_done(state, tools)

    def run_scaffold_node(state: State) -> Dict[str, Any]:
        return run_scaffold(state, tools)

    # Graph wiring
    sg = StateGraph(State)

    sg.add_node("decide_action", decide_action_node)
    sg.add_node("run_shell", run_shell_node)
    sg.add_node("run_fs_read", run_fs_read_node)
    sg.add_node("run_fs_write", run_fs_write_node)
    sg.add_node("finish_done", finish_done_node)
    sg.add_node("run_scaffold", run_scaffold_node)
    sg.add_node("record_result", record_result)
    sg.add_node("maybe_interrupt", maybe_interrupt)

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

    def should_end(state: State):
        return END if state.done else None

    sg.set_entry_point("decide_action")
    sg.add_conditional_edges(
        "maybe_interrupt",
        should_end,
        {END: END, None: "decide_action"},
    )

    chk_path = job_dir / "state.sqlite"
    checkpointer = make_checkpointer(chk_path)

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
            "thread_id": job_id,  # stable per run/conversation
            "checkpoint_ns": "agent",  # optional but recommended
        },
    )
    result_state = app.invoke(state, config=config)

    # Handle both dict and Pydantic State return types from LangGraph
    if hasattr(result_state, "actions_taken"):
        actions_list = getattr(result_state, "actions_taken", []) or []
    elif isinstance(result_state, dict):
        actions_list = result_state.get("actions_taken", []) or []
    else:
        actions_list = []

    # Package outputs similar to previous implementation
    report_path = job_dir / "report.md"
    actions = "\n".join(actions_list)
    report_path.write_text(
        f"# Job {job_id}\nTask: {task}\n\n## Actions\n{actions}\n",
        encoding="utf-8",
    )

    filename, b64 = package_outputs(work_dir, output_dir)
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
