# bashOS Services

Deployment and observability guide for the optional container stack. Read
[HARNESS.md](HARNESS.md) first for the core architecture — this document covers
what runs *around* the terminal.

## The shape of the stack

LangChain and LangGraph are **libraries, not services** — the terminal runs the
whole harness in-process with zero daemons. Containers add three optional
capabilities:

```
                    ┌────────────────────────────────────────────────┐
   local terminal   │                 docker compose                 │
   ──────────────   │                                                │
   bashos (REPL/CLI)│  bashos ── containerized terminal (profile cli)│
        │           │                                                │
        │ optional  │  langgraph-dev ── the SAME kernel graph served │
        │ OTLP      │      :2024        over HTTP (Studio-compatible)│
        ▼           │        │ OTLP                                  │
   PHOENIX_COLLECTOR│        ▼                                       │
   _ENDPOINT ──────▶│  phoenix ──────── traces of every kernel loop  │
                    │      :6006 (UI + OTLP http) :4317 (OTLP grpc)  │
                    └────────────────────────────────────────────────┘
```

| service         | image                       | host port (env override)                  | purpose |
|-----------------|-----------------------------|-------------------------------------------|---------|
| `phoenix`       | `arizephoenix/phoenix`      | 6006 (`BASHOS_PHOENIX_UI_PORT`), 4317 (`BASHOS_PHOENIX_GRPC_PORT`) | [Arize Phoenix](https://github.com/Arize-ai/phoenix) observability: UI + OTLP collectors, data persisted in the `phoenix-data` volume |
| `langgraph-dev` | built from `docker/Dockerfile` | 2024 (`BASHOS_LANGGRAPH_PORT`)         | LangGraph API server loading `langgraph.json` → `bashos.kernel.server:graph` |
| `bashos`        | built from `docker/Dockerfile` | —                                      | the terminal itself; `profiles: [cli]`, started explicitly |

```bash
docker compose up -d                 # phoenix + langgraph-dev
docker compose run --rm bashos       # interactive containerized REPL
docker compose run --rm bashos bashos list   # one-shot inside the container
docker compose down                  # stop (phoenix data survives in the volume)
```

## The kernel over HTTP

`langgraph-dev` serves the exact graph the terminal runs — same registry, same
loops, same runtime. Health check and invocation:

```bash
curl http://localhost:2024/ok                        # {"ok":true}

curl -s http://localhost:2024/runs/wait -X POST \
  -H 'Content-Type: application/json' \
  -d '{"assistant_id": "kernel", "input": {"input": "/sh find files over 100MB", "trace": []}}'
```

The response is the final `KernelState`: `output`, `route`, and the `trace`
log. LangGraph Studio can attach to `http://localhost:2024` for a visual view
of the kernel graph.

> The graph reference in `langgraph.json` must be the **module path**
> (`bashos.kernel.server:graph`), not a file path — the server imports the
> installed package; file-path loading breaks the package's relative imports.

> The service runs `langgraph dev --allow-blocking`: on the claude-code backend
> the adapter spawns the Claude Code CLI, whose bootstrap does synchronous file
> IO that the dev server's blocking detector would otherwise reject as a
> `BlockingError`. Fine for a dev server; a production deployment would prefer
> the `api` backend (fully async) or thread-wrapped calls.

## Observability (Phoenix)

Tracing is opt-in and degrades to a no-op when unconfigured or uninstalled
(`runtime/tracing.py`). Enable it anywhere — containers or the local terminal:

```bash
pip install -e ".[trace]"                             # arize-phoenix-otel + openinference
export PHOENIX_COLLECTOR_ENDPOINT=http://localhost:6006
bashos run "/sh list open ports"                      # kernel spans → Phoenix project "bashos"
```

- In compose, `langgraph-dev` ships with tracing on, pointed at the bundled
  `phoenix` service.
- Spans cover kernel nodes and loop structure. On the `claude-code` backend the
  model call runs inside the `claude` subprocess, so its span carries timing
  but not token-level detail; the `api` backend yields full LLM telemetry.

### Already running a Phoenix?

Phoenix separates data by **project name** — bashOS reports as project
`bashos`, so it can share one Phoenix with other stacks. Two options:

1. **Reuse it** (recommended): skip the bundled service and point
   `PHOENIX_COLLECTOR_ENDPOINT` at the existing instance.
2. **Run both**: remap bashOS's host ports so they don't collide:

   ```bash
   # .env (compose reads it automatically)
   BASHOS_PHOENIX_UI_PORT=6007
   BASHOS_PHOENIX_GRPC_PORT=4318
   ```

## Auth inside containers

An interactive `claude` login is not possible in a container. Set one of these
in `.env` (compose passes them through):

```bash
CLAUDE_CODE_OAUTH_TOKEN=sk-ant-oat01-...   # mint with: claude setup-token
# or
ANTHROPIC_API_KEY=sk-ant-api03-...
```

The image bundles the Claude Code CLI (via npm) and shellcheck, so all three
loops — including `/script` verification and the react loop's tool harness —
work identically in and out of containers.

## Image layout

One image (`docker/Dockerfile`) backs both app services: `python:3.12-slim` +
Node (for the Claude Code CLI) + shellcheck + the package installed with
`.[trace]` extras + `langgraph-cli[inmem]`. The compose `command` selects the
role: default `bashos`, or `langgraph dev` for the API server.
