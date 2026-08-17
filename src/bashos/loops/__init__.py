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
           Delegates to the OpenCode engine under the read-only permission
           ruleset in opencode/policy.py: the model inspects the actual
           machine — files, probes — the engine refuses anything outside the
           policy, and every action streams to the terminal as it happens.

No loop owns a reasoning loop of its own: `prompt` and `refine` call
`engine.complete()` through the LangChain adapter, `react` calls
`engine.act()`. bashOS decides what runs and what it may touch; the engine
decides how to think.

Adding a loop = one module exposing a node factory, one entry in the kernel's
_LOOP_NODES map, and a `loop:` value commands can declare.
"""
