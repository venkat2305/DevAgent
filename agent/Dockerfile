FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    gnupg \
    xz-utils \
    # GUI + VNC stack
    xvfb \
    x11vnc \
    fluxbox \
    novnc \
    websockify \
    xdotool \
    # Node (Debian repo version is OK for v1)
    nodejs \
    npm \
    # misc
    wget \
    unzip \
    && rm -rf /var/lib/apt/lists/*

COPY . /app

# Modal's @modal.asgi_app will run the ASGI server; no CMD needed here.

# Headless display for future GUI flows
ENV DISPLAY=:0
EXPOSE 6080

# Make entrypoint executable for optional local runs
RUN chmod +x /app/entrypoint.sh
