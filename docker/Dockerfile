# bashOS service image — used by both the `bashos` terminal container and the
# `langgraph-dev` API server. Node carries two things bashOS needs: the
# OpenCode engine it runs on, and the Claude Code CLI (the fallback backend,
# and the source of the OAuth credential the engine is wired with).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends nodejs npm git curl shellcheck \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g opencode-ai @anthropic-ai/claude-code

WORKDIR /app

COPY pyproject.toml README.md langgraph.json opencode.jsonc ./
COPY src ./src
COPY .claude ./.claude
COPY docs ./docs

RUN pip install -e ".[trace]" "langgraph-cli[inmem]>=0.2"

CMD ["bashos"]
