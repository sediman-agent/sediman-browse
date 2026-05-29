# ---- Build stage ----
FROM python:3.11-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /build

COPY pyproject.toml uv.lock ./
COPY src/ src/

RUN uv pip install --system --no-cache .

# ---- Runtime stage ----
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/root/.cache/ms-playwright

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin/sediman /usr/local/bin/sediman
COPY --from=builder /build/src /app/src

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
        libcups2 libdrm2 libxkbcommon0 libxcomposite1 \
        libxdamage1 libxrandr2 libgbm1 libpango-1.0-0 \
        libcairo2 libasound2 libxshmfence1 && \
    rm -rf /var/lib/apt/lists/* && \
    python -m playwright install chromium && \
    mkdir -p /root/.sediman

WORKDIR /app

EXPOSE 8080

CMD ["sediman", "serve", "--host", "0.0.0.0", "--port", "8080", "--headless"]
