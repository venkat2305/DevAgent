#!/usr/bin/env bash
set -euo pipefail

# Ensure child processes are cleaned up on exit to avoid noisy XIOError logs
cleanup() {
  pkill -TERM -P $$ >/dev/null 2>&1 || true
  wait >/dev/null 2>&1 || true
}
trap cleanup TERM INT EXIT

# Start virtual display
Xvfb :0 -screen 0 1920x1080x24 &
for i in $(seq 1 50); do [ -S /tmp/.X11-unix/X0 ] && break; sleep 0.2; done

# Start window manager (lightweight)
fluxbox &

# Start VNC server on :5900 (no auth for dev). Bind IPv4 only to silence IPv6 warning.
x11vnc -display :0 -rfbport 5900 -forever -shared -nopw -noxdamage -xkb -listen 0.0.0.0 -bg

# Expose via noVNC (websockify) on :6080
websockify --web=/usr/share/novnc/ 6080 localhost:5900 &

# Exec passed command (e.g., uvicorn) or just sleep if run under Modal ASGI
exec "$@"
