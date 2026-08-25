"""The kernel graph: parse → route (or classify) → orchestration loop → respond.

    input ─▶ parse ─┬─▶ dispatch ──▶ loop_prompt ─┐
                    │       ▲   └──▶ loop_refine ─┼─▶ respond ─▶ output
                    │       │   └──▶ loop_react ──┘
                    └─▶ classify (bare natural language → best command)

Slash input dispatches straight to the loop its command declares; bare natural
language is classified (heuristic first, then a model call) to a command.
Unknown commands short-circuit to respond with a did-you-mean.
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Callable

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph

from ..config import KernelConfig
from ..events import EventSink
from ..registry import CommandSpec
from .state import KernelState

FALLBACK_COMMAND = "sh"
_LOOP_NODES = {"prompt": "loop_prompt", "refine": "loop_refine", "react": "loop_react"}

_CLASSIFY_SYSTEM = (
    "You route terminal requests to bashOS commands. "
    "Reply with exactly one command name from the list — nothing else."
)

_FOLLOWUP = re.compile(
    r"^(now |also |instead |then |and |but |without |except |excluding |"
    r"make (it|that|this) |change |add |remove |exclude |include |keep |drop )",
    re.I,
)

# Conservative: only fire on strong signals. Anything doubtful goes to the model
# (or /sh when no model is available).
_HEURISTICS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(cron|crontab|every (day|hour|minute)|at \d{1,2}:\d{2})\b", re.I), "cron"),
    (re.compile(r"\b(regex|regexp|regular expression)\b", re.I), "regex"),
    (re.compile(r"\b(explain|what does this|man page)\b", re.I), "explain"),
    (re.compile(r"\b(audit|security.?review|shell injection)\b", re.I), "audit"),
    (
        re.compile(
            r"\b(port|translate|convert)\b.*\b(bash|posix|zsh|powershell|python)\b",
            re.I,
        ),
        "port",
    ),
    (
        re.compile(r"\b(pipeline|awk|jq |unique ips?|access\.log)\b", re.I),
        "pipe",
    ),
    (re.compile(r"\b(write|generate|draft) a (bash )?script\b", re.I), "script"),
    (re.compile(r"\b(why (is|did).{0,40}fail|traceback|exit code \d+)\b", re.I), "debug"),
    (
        re.compile(
            r"\b(health check|is (this|the) (machine|box|host) (ok|healthy)|os-health)\b",
            re.I,
        ),
        "health",
    ),
    (
        re.compile(
            r"\b(how much (disk|memory|ram)|top processes|"
            r"why is this (machine|box) slow|system (status|load))\b",
            re.I,
        ),
        "sys",
    ),
]


def parse_line(line: str) -> tuple[str | None, str]:
    """Split a terminal line into (command, args). No slash → (None, line)."""
    line = line.strip()
    if line.startswith("/"):
        head, _, rest = line[1:].partition(" ")
        return head.strip().lower(), rest.strip()
    return None, line


def looks_like_followup(text: str) -> bool:
    return bool(_FOLLOWUP.match(text.strip()))


def guess_command(text: str, registry: dict[str, CommandSpec]) -> str | None:
    """Return a command name when the request matches a high-confidence heuristic."""
    for pattern, name in _HEURISTICS:
        if name in registry and pattern.search(text):
            return name
    return None


def _delta_trace(compiled, prefix: str):
    """Mount a compiled subgraph without re-emitting the parent trace.

    Nested graphs return their full accumulated `trace`; the parent's
    `operator.add` reducer would otherwise double the incoming entries.
    """

    async def node(state: KernelState) -> dict:
        result = await compiled.ainvoke(state)
        out = {key: result[key] for key in ("output", "error", "route") if key in result}
        out["trace"] = [line for line in result.get("trace", []) if line.startswith(prefix)]
        return out

    return node


def build_kernel(
    registry: dict[str, CommandSpec],
    llm: BaseChatModel | None,
    config: KernelConfig,
    on_event: Callable[[str], None] | None = None,
    classify_llm: BaseChatModel | None = None,
    on_engine_event: EventSink | None = None,
):
    from ..loops.prompt import make_prompt_node
    from ..loops.react import make_react_node
    from ..loops.refine import build_refine_graph
    from ..runtime.llm import message_text

    router = classify_llm or llm

    def parse_node(state: KernelState) -> dict:
        command, args = parse_line(state["input"])
        if command is None:
            return {"args": args, "trace": ["parse: natural language input"]}
        if command in registry:
            return {
                "command": command,
                "args": args,
                "route": "slash",
                "trace": [f"parse: /{command} → loop={registry[command].loop}"],
            }
        suggestion = difflib.get_close_matches(command, list(registry), n=1)
        hint = f" Did you mean /{suggestion[0]}?" if suggestion else ""
        return {
            "error": f"bashos: /{command}: command not found.{hint} Try `list`.",
            "route": "error",
            "trace": [f"parse: unknown command /{command}"],
        }

    async def classify_node(state: KernelState) -> dict:
        text = state.get("args") or state["input"]
        last = state.get("last_command")
        if last and last in registry and looks_like_followup(text):
            prior = (state.get("last_input") or "").strip()
            args = f"{prior}\n\nRevision: {text}" if prior else text
            return {
                "command": last,
                "args": args,
                "route": "followup",
                "trace": [f"classify: follow-up → /{last}"],
            }
        if guessed := guess_command(text, registry):
            return {
                "command": guessed,
                "args": text,
                "route": "classified",
                "trace": [f"classify: heuristic → /{guessed}"],
            }
        if router is None or config.dry_run:
            return {
                "command": FALLBACK_COMMAND,
                "args": text,
                "route": "fallback",
                "trace": [f"classify: no model available → /{FALLBACK_COMMAND}"],
            }
        menu = "\n".join(f"/{s.name} — {s.description}" for s in registry.values())
        reply = await router.ainvoke(
            [
                SystemMessage(_CLASSIFY_SYSTEM),
                HumanMessage(f"Commands:\n{menu}\n\nRequest:\n{text}"),
            ]
        )
        raw = message_text(reply).strip()
        name = raw.lstrip("/").split()[0].lower() if raw else FALLBACK_COMMAND
        if name not in registry:
            name = FALLBACK_COMMAND
        return {
            "command": name,
            "args": text,
            "route": "classified",
            "trace": [f"classify: routed to /{name}"],
        }

    def dispatch(state: KernelState) -> str:
        return _LOOP_NODES[registry[state["command"]].loop]

    def after_parse(state: KernelState) -> str:
        if state.get("route") == "error":
            return "respond"
        if not state.get("command"):
            return "classify"
        return dispatch(state)

    def respond_node(state: KernelState) -> dict:
        if state.get("error") and not state.get("output"):
            return {"output": state["error"]}
        return {}

    graph = StateGraph(KernelState)
    graph.add_node("parse", parse_node)
    graph.add_node("classify", classify_node)
    graph.add_node("loop_prompt", make_prompt_node(registry, llm, config))
    graph.add_node("loop_refine", _delta_trace(build_refine_graph(registry, llm, config), "refine:"))
    graph.add_node(
        "loop_react",
        make_react_node(
            registry, config, on_event=on_event, on_engine_event=on_engine_event
        ),
    )
    graph.add_node("respond", respond_node)

    graph.add_edge(START, "parse")
    graph.add_conditional_edges("parse", after_parse, ["classify", "respond", *_LOOP_NODES.values()])
    graph.add_conditional_edges("classify", dispatch, list(_LOOP_NODES.values()))
    for node in _LOOP_NODES.values():
        graph.add_edge(node, "respond")
    graph.add_edge("respond", END)
    return graph.compile()
