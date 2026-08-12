"""Kernel configuration, resolved from environment with per-invocation overrides."""

from __future__ import annotations

import os

from pydantic import BaseModel

DEFAULT_MODEL = "claude-opus-5"

BACKEND_CLAUDE_CODE = "claude-code"
BACKEND_API = "api"


class KernelConfig(BaseModel):
    model: str = DEFAULT_MODEL
    backend: str | None = None  # "claude-code" | "api" | None = auto-detect
    max_output_tokens: int = 16000
    react_max_turns: int = 12
    refine_max_iters: int = 2  # bounded repair passes in the refine loop
    dry_run: bool = False
    verbose: bool = False

    @classmethod
    def from_env(cls, **overrides: object) -> KernelConfig:
        data: dict[str, object] = {}
        env_map = {
            "model": "BASHOS_MODEL",
            "backend": "BASHOS_BACKEND",
            "max_output_tokens": "BASHOS_MAX_OUTPUT_TOKENS",
            "react_max_turns": "BASHOS_REACT_MAX_TURNS",
        }
        for field, var in env_map.items():
            if value := os.environ.get(var):
                data[field] = value
        data.update({k: v for k, v in overrides.items() if v is not None})
        return cls(**data)  # type: ignore[arg-type]
