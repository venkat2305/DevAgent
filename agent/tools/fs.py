from __future__ import annotations

from pathlib import Path
from typing import Iterable


class FsTool:
    """Safe file operations under a base directory.

    Prevents path escapes. All paths are resolved relative to `base_dir`
    unless an absolute path inside `allowed_root` is provided.
    """

    def __init__(self, base_dir: Path, allowed_root: Path | None = None):
        self.base_dir = Path(base_dir).resolve()
        self.allowed_root = Path(allowed_root).resolve(
        ) if allowed_root else self.base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _resolve(self, path: str) -> Path:
        p = Path(path)
        if not p.is_absolute():
            p = (self.base_dir / p).resolve()
        else:
            p = p.resolve()
        if not str(p).startswith(str(self.allowed_root)):
            raise ValueError("path not allowed outside allowed_root")
        return p

    def write(self, path: str, content: str) -> dict:
        try:
            full = self._resolve(path)
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(content, encoding="utf-8")
            return {
                "ok": True,
                "path": str(full),
                "bytes": len(
                    content.encode("utf-8"))}
        except Exception as e:
            return {"ok": False, "error": str(e), "path": path}

    def read(self, path: str) -> dict:
        try:
            full = self._resolve(path)
            text = full.read_text(encoding="utf-8")
            return {"ok": True, "path": str(full), "content": text[-12000:]}
        except Exception as e:
            return {"ok": False, "error": str(e), "path": path}

    def list(
            self,
            path: str | None = None,
            patterns: Iterable[str] | None = None) -> dict:
        try:
            target = self._resolve(path) if path else self.base_dir
            items = []
            for p in sorted(target.rglob("*")):
                if patterns:
                    from fnmatch import fnmatch
                    if not any(fnmatch(p.name, pat) for pat in patterns):
                        continue
                items.append(str(p.relative_to(self.base_dir)))
            return {"ok": True, "base": str(target), "items": items[:2000]}
        except Exception as e:
            return {"ok": False, "error": str(e), "path": path or "."}
