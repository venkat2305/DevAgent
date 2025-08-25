from fastapi import FastAPI
import os
import shutil
import subprocess


def create_app() -> FastAPI:
    """Create FastAPI app for agent sandbox."""
    app = FastAPI(title="Agent Runtime", version="0.1.0")

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    @app.get("/")
    def root():
        return {"service": "agent", "status": "ready"}

    @app.get("/env/tools")
    def tools_info():
        def exists(cmd: str) -> bool:
            return shutil.which(cmd) is not None

        def version(cmd: list[str]) -> str | None:
            try:
                out = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                txt = out.stdout.strip() or out.stderr.strip()
                return txt.splitlines()[0] if txt else None
            except Exception:
                return None

        return {
            "DISPLAY": os.environ.get("DISPLAY"),
            "node": version(["node", "--version"]),
            "npm": version(["npm", "--version"]),
            "xvfb": exists("Xvfb"),
            "x11vnc": exists("x11vnc"),
            "fluxbox": exists("fluxbox"),
            "xdotool": exists("xdotool"),
            "websockify": exists("websockify"),
            "novnc_web": os.path.isdir("/usr/share/novnc"),
        }

    return app


# Expose as `app` for ASGI servers
app = create_app()
