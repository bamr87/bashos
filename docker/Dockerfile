# bashOS service image — used by both the `bashos` terminal container and the
# `langgraph-dev` API server. Node carries two things bashOS needs: the
# OpenCode engine it runs on, and the Claude Code CLI (the fallback backend,
# and the source of the OAuth credential the engine is wired with).
FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends nodejs npm git curl shellcheck \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g opencode-ai @anthropic-ai/claude-code

WORKDIR /app

# Dependencies first, keyed on the packaging files alone. The editable install
# is made against a one-file stub package: it only records /app/src on the
# import path (a .pth file) plus the `bashos` entry point, so the real source
# copied below is what runs, and a change under src/, .claude/ or docs/ reuses
# this layer instead of resolving and installing every dependency again.
COPY pyproject.toml README.md ./
RUN mkdir -p src/bashos \
    && touch src/bashos/__init__.py \
    && pip install -e ".[trace]" "langgraph-cli[inmem]>=0.2"

# The source last, with nothing run after it: a source change rebuilds only
# these copies.
COPY langgraph.json opencode.jsonc ./
COPY src ./src
COPY .claude ./.claude
COPY docs ./docs

CMD ["bashos"]
