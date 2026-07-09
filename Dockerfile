FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    NODE_BIN=/usr/bin/node \
    APP_HOST=0.0.0.0 \
    APP_PORT=8002

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        nodejs \
        libglib2.0-0 \
        libgl1 \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-ai.txt ./
RUN pip install --upgrade pip \
    && pip install -r requirements.txt \
    && pip install -r requirements-ai.txt

COPY . .

RUN mkdir -p outputs/runtime outputs/users uploads/users \
    && chmod +x scripts/start_asis_full_stack.sh scripts/deploy_demo.sh asis-agent-runtime/scripts/*.sh

EXPOSE 8002

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -fsS http://127.0.0.1:${APP_PORT}/health >/dev/null || exit 1

CMD ["./scripts/deploy_demo.sh"]

