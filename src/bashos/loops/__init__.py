"""Orchestration loops — the AI harness at the core of bashOS.

Every command declares one loop in its frontmatter; the kernel dispatches to it.
Each loop is a self-contained orchestration pattern over the model runtime:

  prompt   render spec → one model call → answer.
           The syscall of loops: cheap, stateless, deterministic routing.

  refine   generate → verify (external critic) → repair, bounded.
           The draft runs through a deterministic verifier (shellcheck); if the
           critic objects, the critique is fed back for a repair pass. Model
           judgment is checked by real tooling, not self-review.

  react    reason ↔ act until done.
           Delegates to the Claude Code harness (Agent SDK) under a read-only
           tool policy: the model inspects the actual machine — files, probes —
           and every action streams to the terminal as it happens.

Adding a loop = one module exposing a node factory, one entry in the kernel's
_LOOP_NODES map, and a `loop:` value commands can declare.
"""
