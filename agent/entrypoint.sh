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
XVFB_PID=$!

# Start window manager (lightweight)
fluxbox &

# Optional demo windows so noVNC shows activity
if [ "${DESKTOP_DEMO:-0}" = "1" ]; then
  # Simple clock as visual heartbeat
  nohup sh -lc 'xclock -digital -update 1' >/dev/null 2>&1 &
  # Tail a log file in a terminal for visibility
  nohup sh -lc 'mkdir -p /tmp; touch /tmp/agent.log; xterm -fa Monospace -fs 11 -geometry 120x28+40+40 -e bash -lc "echo \"[demo] tailing /tmp/agent.log\"; tail -F /tmp/agent.log"' >/dev/null 2>&1 &
fi

# Start VNC server on :5900 (no auth for dev). Bind IPv4 only to silence IPv6 warning.
x11vnc -display :0 -nopw -forever -rfbport 5900 -shared -4 &

# Expose via noVNC (websockify) on :6080
websockify --web=/usr/share/novnc/ 6080 localhost:5900 &

# Exec passed command (e.g., uvicorn) or just sleep if run under Modal ASGI
exec "$@"
