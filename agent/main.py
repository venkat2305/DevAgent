from fastapi import FastAPI


def create_app() -> FastAPI:
    """Create FastAPI app for agent sandbox."""
    app = FastAPI(title="Agent Runtime", version="0.1.0")

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    @app.get("/")
    def root():
        return {"service": "agent", "status": "ready"}

    return app


# Expose as `app` for ASGI servers
app = create_app()
