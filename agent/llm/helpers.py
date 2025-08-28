from __future__ import annotations

import base64
import os
from pathlib import Path
from shutil import make_archive
from typing import Any, Dict
import atexit
import contextlib
import json

from langgraph.checkpoint.sqlite import SqliteSaver


def default_job_dir() -> Path:
    if os.path.exists("/job") or os.environ.get("MODAL_ENVIRONMENT"):
        return Path("/job")
    return Path.cwd() / "test_job"


def safe_json_fragment(d: Dict[str, Any]) -> str:
    try:
        return json.dumps(d, ensure_ascii=False)[:20000]
    except Exception:
        return str(d)[:20000]


def package_outputs(work_dir: Path, output_dir: Path) -> tuple[str, str]:
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


_CM_CLEANUPS = []


def make_checkpointer(db_path: Path):
    try:
        cm = SqliteSaver.from_conn_string(str(db_path))
        if hasattr(cm, "get_next_version"):
            return cm
        if hasattr(cm, "__enter__") and hasattr(cm, "__exit__"):
            saver = cm.__enter__()

            def _cleanup():
                with contextlib.suppress(Exception):
                    cm.__exit__(None, None, None)

            _CM_CLEANUPS.append(_cleanup)
            atexit.register(_cleanup)
            return saver
    except Exception:
        pass

    try:
        return SqliteSaver(str(db_path))
    except Exception:
        return None
