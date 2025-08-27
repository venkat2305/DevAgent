from __future__ import annotations

from typing import Literal, Optional, List, Dict, Any
from pydantic import BaseModel, Field


class ShellArgs(BaseModel):
    command: str = Field(..., description="Shell command to execute")


class FsReadArgs(BaseModel):
    path: str = Field(..., description="Path to read (relative to workdir)")


class FsWriteArgs(BaseModel):
    path: str = Field(..., description="Path to write (relative to workdir)")
    content: str = Field(..., description="Content to write")


class DoneArgs(BaseModel):
    reason: str = Field(..., description="Why the task is done")


class ScaffoldArgs(BaseModel):
    recipe_id: str = Field(..., description="Recipe ID (e.g., react-vite-js)")
    name: Optional[str] = Field(None, description="Project name (optional)")


class RouterArgs(BaseModel):
    # Use optional superset of fields to avoid JSON Schema anyOf/oneOf
    command: Optional[str] = Field(
        None, description="Shell command to execute"
    )
    path: Optional[str] = Field(None, description="Path for fs_read/fs_write")
    content: Optional[str] = Field(None, description="Content for fs_write")
    reason: Optional[str] = Field(None, description="Why the task is done")
    recipe_id: Optional[str] = Field(
        None, description="Recipe ID for scaffold"
    )
    name: Optional[str] = Field(
        None, description="Project name for scaffold"
    )


class RouterAction(BaseModel):
    tool: Literal["shell", "fs_read", "fs_write", "done", "scaffold"]
    args: RouterArgs


class State(BaseModel):
    # Single source of truth
    messages: List[Dict[str, Any]] = Field(default_factory=list)
    actions_taken: List[str] = Field(default_factory=list)
    last_result: Optional[Dict[str, Any]] = None
    tool_result: Optional[Dict[str, Any]] = None
    done: bool = False
    reason: Optional[str] = None
    task: str
    # Transient carrier for router decision
    pending_action: Optional[RouterAction] = None

    class Config:
        extra = "ignore"
