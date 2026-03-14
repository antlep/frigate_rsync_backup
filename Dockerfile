# --------------------------------------------------------------------------- #
# Builder – install Python deps                                               #
# --------------------------------------------------------------------------- #
FROM python:3.12-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# --------------------------------------------------------------------------- #
# Final image                                                                  #
# --------------------------------------------------------------------------- #
FROM python:3.12-slim

# rclone install
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && curl -fsSL https://rclone.org/install.sh | bash \
    && apt-get purge -y --auto-remove curl \
    && rm -rf /var/lib/apt/lists/*

# Copy Python packages from builder
COPY --from=builder /install /usr/local

WORKDIR /app
COPY src/ ./src/

# /config  → rclone.conf + config.yaml  (read-only mount recommended)
# /data    → SQLite persistence volume
# /tmp/frigate-sync  → ephemeral download staging (tmpfs recommended)
VOLUME ["/config", "/data"]

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src \
    CONFIG_PATH=/config/config.yaml

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c \
        "import urllib.request, sys; \
         r = urllib.request.urlopen('http://localhost:8080/health', timeout=4); \
         sys.exit(0 if r.status == 200 else 1)"

CMD ["python", "src/main.py"]
