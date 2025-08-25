#!/usr/bin/env bash
set -euo pipefail

# Start virtual display
Xvfb :0 -screen 0 1920x1080x24 &
XVFB_PID=$!

# Start window manager (lightweight)
fluxbox &

# Start VNC server on :5900 (no auth for dev)
x11vnc -display :0 -nopw -forever -rfbport 5900 -shared &

# Expose via noVNC (websockify) on :6080
websockify --web=/usr/share/novnc/ 6080 localhost:5900 &

# Exec passed command (e.g., uvicorn) or just sleep if run under Modal ASGI
exec "$@"
