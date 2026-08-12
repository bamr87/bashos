"""The kernel graph: parse → route (or classify) → orchestration loop → respond.

    input ─▶ parse ─┬─▶ dispatch ──▶ loop_prompt ─┐
                    │       ▲   └──▶ loop_refine ─┼─▶ respond ─▶ output
                    │       │   └──▶ loop_react ──┘
                    └─▶ classify (bare natural language → best command)

Slash input dispatches straight to the loop its command declares; bare natural
language goes through a one-call classifier node first. Unknown commands short-
circuit to respond with a did-you-mean.
"""

from __future__ import annotations

import difflib
from collections.abc import Callable

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph

from ..config import KernelConfig
from ..registry import CommandSpec
from .state import KernelState

FALLBACK_COMMAND = "sh"
_LOOP_NODES = {"prompt": "loop_prompt", "refine": "loop_refine", "react": "loop_react"}

_CLASSIFY_SYSTEM = (
    "You route terminal requests to bashOS commands. "
    "Reply with exactly one command name from the list — nothing else."
)


def parse_line(line: str) -> tuple[str | None, str]:
    """Split a terminal line into (command, args). No slash → (None, line)."""
    line = line.strip()
    if line.startswith("/"):
        head, _, rest = line[1:].partition(" ")
        return head.strip().lower(), rest.strip()
    return None, line


def build_kernel(
    registry: dict[str, CommandSpec],
    llm: BaseChatModel | None,
    config: KernelConfig,
    on_event: Callable[[str], None] | None = None,
):
    from ..loops.prompt import make_prompt_node
    from ..loops.react import make_react_node
    from ..loops.refine import build_refine_graph
    from ..runtime.llm import message_text

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
        if llm is None or config.dry_run:
            return {
                "command": FALLBACK_COMMAND,
                "args": text,
                "route": "fallback",
                "trace": [f"classify: no model available → /{FALLBACK_COMMAND}"],
            }
        menu = "\n".join(f"/{s.name} — {s.description}" for s in registry.values())
        reply = await llm.ainvoke(
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
    graph.add_node("loop_refine", build_refine_graph(registry, llm, config))
    graph.add_node("loop_react", make_react_node(registry, config, on_event=on_event))
    graph.add_node("respond", respond_node)

    graph.add_edge(START, "parse")
    graph.add_conditional_edges("parse", after_parse, ["classify", "respond", *_LOOP_NODES.values()])
    graph.add_conditional_edges("classify", dispatch, list(_LOOP_NODES.values()))
    for node in _LOOP_NODES.values():
        graph.add_edge(node, "respond")
    graph.add_edge("respond", END)
    return graph.compile()
