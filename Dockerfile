# ─── Stage 1: Builder ─────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Системные зависимости для компиляции
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libffi-dev libssl-dev portaudio19-dev \
    && rm -rf /var/lib/apt/lists/*

# Установить зависимости в отдельный слой (кешируется)
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir --prefix=/install -r requirements.txt

# ─── Stage 2: Runtime ─────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.title="ARGOS Universal OS"
LABEL org.opencontainers.image.description="Автономная кроссплатформенная ИИ-система"
LABEL org.opencontainers.image.version="2.0.0"
LABEL org.opencontainers.image.source="https://github.com/iliyaqdrwalqu/Argoss"
LABEL org.opencontainers.image.licenses="Apache-2.0"

# Минимальные runtime-зависимости
RUN apt-get update && apt-get install -y --no-install-recommends \
    libssl3 libffi8 curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 1000 -s /bin/bash argos

# Скопировать установленные пакеты из builder
COPY --from=builder /install /usr/local

WORKDIR /app

# Скопировать исходники (порядок важен для кеша)
COPY --chown=argos:argos requirements.txt pyproject.toml ./
COPY --chown=argos:argos src/ ./src/
COPY --chown=argos:argos modules/ ./modules/
COPY --chown=argos:argos config/ ./config/
COPY --chown=argos:argos main.py genesis.py health_check.py ./
COPY --chown=argos:argos scripts/ ./scripts/

# Создать необходимые директории
RUN mkdir -p logs data && chown -R argos:argos /app

USER argos

# Инициализировать структуру при первом запуске
RUN python genesis.py 2>/dev/null || true

# Порты
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8080/api/health || exit 1

# Точка входа — headless режим с Dashboard
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

ENTRYPOINT ["python", "main.py"]
CMD ["--no-gui", "--dashboard"]
