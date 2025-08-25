import modal


image = modal.Image.from_dockerfile("Dockerfile")

app = modal.App("glassbox-agent", image=image)


@app.function(
    cpu=1.0,
    memory=1024,
    scaledown_window=200,
)
@modal.asgi_app()
def fastapi_app():
    # Imports happen inside the container
    from main import app as application
    return application
