# bashOS service image — used by both the `bashos` terminal container and the
# `langgraph-dev` API server. Node is required for the Claude Code CLI, which
# the Claude Agent SDK drives for OAuth-backed model calls.
FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends nodejs npm git curl shellcheck \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g @anthropic-ai/claude-code

WORKDIR /app

COPY pyproject.toml README.md langgraph.json ./
COPY src ./src
COPY .claude ./.claude
COPY docs ./docs

RUN pip install -e ".[trace]" "langgraph-cli[inmem]>=0.2"

CMD ["bashos"]
