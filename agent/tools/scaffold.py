from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, Any, Optional

from .shell import ShellTool


class ScaffoldTool:
    """Create project scaffolds using pre-configured recipes."""

    def __init__(self, cwd: Path):
        self.cwd = Path(cwd)
        self.shell = ShellTool(cwd)
        self.recipes_path = Path(__file__).parent / "../scaffold/recipes.json"

    def _load_recipes(self) -> Dict[str, Any]:
        """Load recipes from JSON file."""
        try:
            with open(self.recipes_path, 'r') as f:
                return json.load(f)
        except Exception:
            return {}

    def _sanitize_name(self, name: str) -> str:
        """Sanitize project name to be filesystem-safe."""
        # Remove special chars, keep alphanumeric and hyphens
        sanitized = re.sub(r'[^a-zA-Z0-9-_]', '-', name)
        # Remove multiple consecutive hyphens
        sanitized = re.sub(r'-+', '-', sanitized)
        # Remove leading/trailing hyphens
        sanitized = sanitized.strip('-')
        return sanitized.lower() or "my-app"

    def _resolve_name_collision(self, name: str) -> str:
        """Handle name collisions by appending numbers."""
        base_name = name
        counter = 1
        while (self.cwd / name).exists():
            name = f"{base_name}-{counter}"
            counter += 1
        return name

    def create(self, recipe_id: str, name: Optional[str] = None) -> Dict[str, Any]:
        """Create a project using the specified recipe."""
        recipes = self._load_recipes()

        if recipe_id not in recipes:
            return {
                "ok": False,
                "error": f"Recipe '{recipe_id}' not found. Available: " +
                         f"{list(recipes.keys())}"
            }

        recipe = recipes[recipe_id]

        # Handle project name
        if not name:
            name = "my-app"

        name = self._sanitize_name(name)
        name = self._resolve_name_collision(name)

        # Resolve command template
        command = recipe["command"].format(name=name)

        print(f"[SCAFFOLD] Creating {recipe_id} project: {name}")
        print(f"[SCAFFOLD] Command: {command}")

        # Execute the scaffold command
        result = self.shell.run(command)

        if result["ok"]:
            project_path = self.cwd / name
            if project_path.exists():
                # Return a success payload that upstream can use to auto-complete
                # by including a human-readable completion hint.
                return {
                    "ok": True,
                    "recipe_id": recipe_id,
                    "project_name": name,
                    "project_path": str(project_path),
                    "command": command,
                    "stdout": result["stdout"],
                    "stderr": result["stderr"],
                    # Hint for the agent's record_result to mark done
                    "reason": f"Scaffolded {recipe_id} project '{name}' successfully",
                }
            # If the command executed but project not found, propagate failure
            return {
                "ok": False,
                "recipe_id": recipe_id,
                "project_name": name,
                "command": command,
                "stdout": result.get("stdout", ""),
                "stderr": result.get("stderr", ""),
                "error": "scaffold command finished but project directory missing",
            }
        # Command failed
        return {
            "ok": False,
            "error": "Scaffold command failed",
            "command": command,
            "exit_code": result.get("exit_code"),
            "stdout": result.get("stdout", ""),
            "stderr": result.get("stderr", ""),
        }

    def list_recipes(self) -> Dict[str, Any]:
        """List available recipes."""
        recipes = self._load_recipes()
        return {
            "ok": True,
            "recipes": {
                rid: {
                    "name": recipe.get("name", rid),
                    "description": recipe.get("description", "")
                }
                for rid, recipe in recipes.items()
            }
        }
