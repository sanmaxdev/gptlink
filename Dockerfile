FROM node:22-bookworm-slim

ARG GPTLINK_VERSION=dev

LABEL org.opencontainers.image.title="GPTLink" \
      org.opencontainers.image.description="OpenAI-compatible and MCP-native GPT Image gateway" \
      org.opencontainers.image.source="https://github.com/sanmaxdev/gptlink" \
      org.opencontainers.image.version="${GPTLINK_VERSION}" \
      org.opencontainers.image.licenses="MIT"

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/gptlink-venv \
    PATH=/opt/gptlink-venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    HOME=/home/gptlink \
    GPTLINK_HOST=0.0.0.0 \
    GPTLINK_PORT=8787 \
    GPTLINK_DATA_DIR=/data \
    CODEX_HOME=/home/gptlink/.codex \
    GPTLINK_MCP_ALLOWED_ROOTS=/data/images

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates passwd python3 python3-pip python3-venv \
    && rm -rf /var/lib/apt/lists/* \
    && npm install --global @openai/codex \
    && npm cache clean --force \
    && python3 -m venv "$VIRTUAL_ENV"

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY gptlink ./gptlink
COPY manage.py run.py ./

RUN useradd --create-home --home-dir /home/gptlink --uid 10001 --shell /bin/bash gptlink \
    && install -d -o gptlink -g gptlink -m 0700 /data /data/images /home/gptlink/.codex \
    && chown -R gptlink:gptlink /app

USER gptlink

EXPOSE 8787
VOLUME ["/data", "/home/gptlink/.codex"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8787/health', timeout=3)" || exit 1

CMD ["uvicorn", "gptlink.main:app", "--host", "0.0.0.0", "--port", "8787", "--proxy-headers", "--forwarded-allow-ips=*"]
