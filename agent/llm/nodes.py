from __future__ import annotations

from typing import Any, Dict

from .helpers import safe_json_fragment
from .schema import State


def decide_action(state: State, structured_model) -> Dict[str, Any]:
    print(f"[LOG] Deciding next action for task: {state.task}")

    SYSTEM_TEXT = (
        "You are a precise coding agent.\n"
        "Return only tool selections as structured output.\n"
        "Tools available: shell, fs_read, fs_write, scaffold, done.\n"
        "Use 'scaffold' with recipe_id 'react-vite-js' to create "
        "React projects.\n"
        "Never suggest risky shell commands; keep to the job workspace.\n"
    )

    conversation = [{"role": "system", "content": SYSTEM_TEXT}, *state.messages]
    action = structured_model.invoke(conversation)
    print(f"[LOG] Decided action: {action}")
    return {"pending_action": action}


def run_shell(state: State, tools) -> Dict[str, Any]:
    action = state.pending_action
    assert action is not None and action.tool == "shell"
    cmd = getattr(action.args, "command", None)
    print(f"[LOG] Calling shell tool with command: {cmd}")
    res = tools[0].invoke({"command": cmd})
    print(f"[LOG] Shell tool output: {res}")
    return {"tool_result": res}


def run_fs_read(state: State, tools) -> Dict[str, Any]:
    action = state.pending_action
    assert action is not None and action.tool == "fs_read"
    path = getattr(action.args, "path", None)
    print(f"[LOG] Calling fs_read tool with path: {path}")
    res = tools[1].invoke({"path": path})
    print(f"[LOG] fs_read tool output: {res}")
    return {"tool_result": res}


def run_fs_write(state: State, tools) -> Dict[str, Any]:
    action = state.pending_action
    assert action is not None and action.tool == "fs_write"
    path = getattr(action.args, "path", None)
    content = getattr(action.args, "content", None)
    print(f"[LOG] Calling fs_write tool with path: {path}")
    res = tools[2].invoke({"path": path, "content": content})
    print(f"[LOG] fs_write tool output: {res}")
    return {"tool_result": res}


def finish_done(state: State, tools) -> Dict[str, Any]:
    action = state.pending_action
    assert action is not None and action.tool == "done"
    reason = getattr(action.args, "reason", None)
    print(f"[LOG] Calling done tool with reason: {reason}")
    res = tools[3].invoke({"reason": reason})
    print(f"[LOG] done tool output: {res}")
    return {"tool_result": res}


def run_scaffold(state: State, tools) -> Dict[str, Any]:
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
    action_json = safe_json_fragment(action.model_dump())
    messages = list(state.messages)
    messages.append({"role": "assistant", "content": action_json})
    messages.append({
        "role": "tool",
        "content": safe_json_fragment(result),
    })
    new_state = {
        "messages": messages,
        "actions_taken": [*state.actions_taken, action_json],
        "last_result": result,
        "pending_action": None,
        "tool_result": None,
    }

    if action.tool == "done" or bool(result.get("done")):
        new_state.update({"done": True, "reason": result.get("reason")})

    print(f"[LOG] New state after result: done={new_state.get('done', False)}")
    return new_state


def maybe_interrupt(state: State) -> Dict[str, Any]:
    done = getattr(state, 'done', False)
    print(f"[LOG] maybe_interrupt called. State done: {done}")
    return {}
