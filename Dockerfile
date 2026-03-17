# ── Build stage ──────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# System deps needed to compile some Python packages (PyAudio, cryptography, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libffi-dev \
        libssl-dev \
        portaudio19-dev \
        git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# Install into a prefix so we can copy only the venv in the final stage
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Runtime stage ─────────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

LABEL org.opencontainers.image.title="Argos Universal OS" \
      org.opencontainers.image.description="Autonomous AI platform — headless/server mode" \
      org.opencontainers.image.source="https://github.com/labuaqlysnecy/Argoss" \
      org.opencontainers.image.version="1.4.0"

# Runtime system packages (audio libs keep TTS/STT from crashing silently)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libportaudio2 \
        espeak \
        ffmpeg \
        sqlite3 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

WORKDIR /app

# Create a non-root user for security
RUN useradd -m -u 1000 argos && \
    mkdir -p /app/logs /app/config /app/data /app/builds && \
    chown -R argos:argos /app

# Copy project source
COPY --chown=argos:argos . .

USER argos

# Expose web dashboard port
EXPOSE 8080

# Health-check: ping the web dashboard if available, else verify core import
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health', timeout=5)" \
     || python -c "import src.argos_logger; print('ok')" || exit 1

# Default: headless server mode (no GUI required)
CMD ["python", "main.py", "--no-gui"]
