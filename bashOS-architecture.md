---
title: "bashOS: a reference architecture for the agent appliance"
description: "A buildable software stack for bashOS — an image-based Linux appliance where the agent kernel is a first-class OS service, from microVMs to policy plane"
author: "Amr Abdel-Motaleb"
layout: article
date: 2026-06-20T14:00:00.000Z
lastmod: 2026-06-20T14:00:00.000Z
draft: true
categories:
    - tech
    - AI
tags:
    - ai
    - agentic-ai
    - architecture
    - linux
    - operating-systems
    - security
    - mcp
    - open-source
    - system-design
keywords:
    - ai native operating system architecture
    - agent kernel linux appliance
    - mcp agent sandbox firecracker
    - spiffe agent identity opa policy
    - image-based linux bootc agent
    - build an ai agent operating system
preview: /assets/images/previews/bashos-reference-architecture.png
featured: false
excerpt: "bashOS as a buildable thing: an immutable Linux appliance with an agent kernel as PID-1-adjacent service, microVM sandboxes, a policy plane, and the shell as its system-call interface. Whitepaper plus MVP spec."
---

In [bashos: the new command-line operating system](/bashos-the-new-command-line-operating-system/) I argued that the terminal is growing an operating system of its own — that agents now schedule work, manage context, broker tools, and enforce access the way a kernel manages processes. That piece was about the *posture*. This one is about the *plumbing*: if you took bashOS seriously as a product — an opinionated Linux appliance where the agent kernel is a first-class OS service, not an app you install afterward — what stack would deliver it?

What follows is half whitepaper, half build spec. The first part lays out the architecture and the reasoning; the second part is a minimum viable product (MVP) you could start building this quarter with components that exist today. Nothing here requires inventing new science. It requires *assembling* — which has always been the systems trade's actual superpower.

## Design goals

Five commitments drive every choice below. State them first, because a stack is just goals with version numbers.

1. **The agent is a system service, not an app.** It starts at boot, survives logout, holds durable memory, and is supervised like `sshd` — because a thing with that much authority deserves init-system discipline, not a dotfile.
2. **Humans stay in the approval path for anything irreversible.** The architecture must make "plan, diff, approve" cheap and "act unsupervised on prod" structurally hard, not just discouraged in a README.
3. **Every action is attributable.** Each agent has its own cryptographic identity, every tool call passes a policy gate, and the audit log is append-only. "Which agent did this, on whose intent, under which policy?" must be answerable in one query.
4. **The base OS is boring and immutable.** Agents mutate things for a living; the platform under them must not be mutable by them. Image-based, atomic updates, one-command rollback.
5. **Model-agnostic by construction.** Local weights and frontier APIs behind one gateway. The model is a component, not the architecture — models will churn every six months; the OS should not.

## The architecture in one diagram

```text
┌─────────────────────────────────────────────────────────────────┐
│  L6  INTERFACE        bashos shell (intent + POSIX) · SSH · TUI │
│                       ACP-compatible terminals · web console    │
├─────────────────────────────────────────────────────────────────┤
│  L5  AGENT KERNEL     bashosd: scheduler · session manager      │
│                       context manager · memory · tool broker    │
├──────────────────────────────┬──────────────────────────────────┤
│  L4  POLICY & IDENTITY       │  L3  KNOWLEDGE PLANE             │
│  SPIRE (SPIFFE IDs)          │  AGENTS.md · skills/ playbooks   │
│  OPA policy gate             │  vector index of runbooks/docs   │
│  signed audit log (OTel)     │  git-backed memory store         │
├──────────────────────────────┴──────────────────────────────────┤
│  L2  EXECUTION SANDBOXES     Firecracker microVMs (untrusted)   │
│                              bubblewrap + Landlock (tools)      │
│                              podman containers (services)       │
├─────────────────────────────────────────────────────────────────┤
│  L1  INFERENCE GATEWAY       model router → local (llama.cpp /  │
│                              vLLM / Ollama) + cloud APIs        │
├─────────────────────────────────────────────────────────────────┤
│  L0  BASE OS                 image-based Linux (bootc/Fedora    │
│                              CoreOS lineage) · systemd · atomic │
│                              updates · read-only root           │
└─────────────────────────────────────────────────────────────────┘
```

The layers are numbered from the metal up, but the design conversation runs top-down: the interface defines what the kernel must do, the kernel defines what must be sandboxed, and the sandbox requirements pick the base OS. Walk through them.

## L0 — the base: immutable by policy, boring by design

bashOS ships as an image, not a package list. The base is an image-based Linux built with the `bootc` (bootable container) toolchain from the Fedora CoreOS lineage: the entire OS is a container image, updates are atomic, rollback is a boot-menu entry, and the root filesystem is read-only. First-boot configuration comes in as a declarative Ignition file — hostname, users, which agents to enable, where the audit log ships — so provisioning a new node is `dd` plus a config, and a fleet of fifty is a for-loop.

Why immutable is non-negotiable here, not a fashion choice: the whole premise of the appliance is that semi-autonomous processes execute commands on it all day. An agent that can be talked into modifying its own platform — editing the policy engine's binary, disabling the audit shipper — is a compromised appliance waiting for a clever prompt. On an image-based system the platform is not writable at runtime, full stop. The agent's writable world is `/var` and its sandboxes; everything else changes only through a new signed image. Security people have converged on image-based systems for exactly this property, and by 2026 the tooling (bootc, Fedora Atomic lineage, Flatcar) is mainstream, not exotic.

The alternative worth naming: NixOS gets you reproducibility and rollback through functional package management rather than a read-only root, and for a team already fluent in Nix it is a defensible base. For the appliance product, bootc wins on a simpler story — "the OS is a container image" is one sentence an SMB's IT lead already understands.

## L1 — inference: the model is a tenant, not a landlord

All model access — local and cloud — goes through one on-box gateway service with an OpenAI-compatible interface. Behind it:

- **Local lane:** llama.cpp or Ollama for CPU/consumer-GPU boxes; vLLM when the appliance has serious GPU and needs throughput. Open-weight models handle the always-on, low-stakes work: log triage, summarization, first-pass drafting, anything with data that must not leave the box.
- **Cloud lane:** frontier APIs (Anthropic, OpenAI, Google) for the heavy reasoning — the plan-making, the gnarly refactor, the incident analysis. The gateway holds the keys; agents never see raw credentials.

The gateway is where three cross-cutting concerns live, once, instead of in every agent: **routing** (which class of task goes to which model, with per-route cost ceilings), **redaction** (personally identifiable information (PII) scrubbing before anything leaves the box — this is a policy decision enforced in one choke point), and **metering** (per-agent token accounting, because the finance conversation about agent spend is coming to every shop). LiteLLM is the obvious off-the-shelf starting point; the MVP treats it as a swappable part.

This layer is why "model-agnostic by construction" is achievable. The 2026 pattern across the industry is exactly this shape — a router in front of interchangeable inference backends — and it is what lets bashOS survive the six-month model churn without re-architecture.

## L2 — execution: three sandboxes, matched to trust

The single most consequential security decision in an agent OS is where generated commands actually run. bashOS uses three tiers, and the policy plane (L4) decides which tier a given action lands in:

| Tier | Technology | Used for | Isolation story |
|---|---|---|---|
| **Hard** | Firecracker microVMs | Untrusted/generated code, anything network-facing, multi-step jobs | Hardware virtualization boundary; ~125 ms boot, ~5 MB overhead, disposable per job |
| **Medium** | bubblewrap + Landlock + seccomp | Individual tool calls: file edits, builds, test runs | Kernel-enforced filesystem and syscall restriction; near-zero overhead |
| **Soft** | podman containers (rootless) | Long-running agent-managed services the human has approved | Standard container isolation; survives across sessions |

This mirrors what the agent vendors themselves converged on — Claude Code sandboxes with bubblewrap, Codex CLI with Landlock plus seccomp, and the hosted platforms (E2B, Vercel, Lambda) standardized on microVMs as the per-request execution unit. bashOS's contribution is making the *tier assignment a policy decision* rather than a per-tool hardcode: the same `psql` invocation might run in the medium tier against staging and be flat-out denied against prod, and that difference lives in one reviewable policy file, not in tribal knowledge.

The practical payoff: "let the agent try it" becomes cheap. A microVM that boots in an eighth of a second and evaporates afterward means the default answer to "should the agent run this experimentally first?" is always yes — in the disposable tier, with the diff coming back for review.

## L3 — knowledge: context as a mounted filesystem

Context engineering beats prompt cleverness, so bashOS gives context a filesystem-grade home rather than leaving it scattered in dotfiles:

- **`/etc/bashos/AGENTS.md` and per-project `AGENTS.md`** — the convention the whole industry already reads. Machine role, conventions, do-not-touch list, build/test commands. This file is provisioned by Ignition on first boot like any other config.
- **`/var/lib/bashos/skills/`** — versioned, git-backed playbooks: "how we rotate certs," "how we do a release," "the postmortem template." Each is a governed procedure an agent can load on demand — the runbook, promoted from wiki-rot to executable asset.
- **`/var/lib/bashos/memory/`** — durable agent memory as plain markdown files with frontmatter, git-committed, so memory is diffable, reviewable, and revertible like everything else. What did we decide about the firewall in March? `git log` knows.
- **A local vector index** (SQLite-vec class — embedded, no service to run) over the runbooks, past incidents, and docs, giving agents retrieval without shipping your operational history to anyone.

The design rule: *everything an agent knows should be inspectable with `cat` and reversible with `git revert`.* No opaque memory blobs. When an agent behaves oddly, the first debugging move is reading its context — so the context must be readable.

## L4 — policy and identity: the layer that makes it an OS

This is the layer that separates bashOS from "a laptop with an agent CLI on it," and it has three parts.

**Identity.** Every agent process gets its own short-lived cryptographic identity via SPIFFE/SPIRE — the Cloud Native Computing Foundation (CNCF)-graduated workload-identity standard. No agent ever holds your credentials; it holds *its own*, scoped and expiring, and downstream systems (databases, clouds, other nodes) authenticate the agent as itself. This is the direction the entire industry is moving — agents as first-class identity principals with their own audit attribution — and NIST's 2026 concept work on agent identity frames exactly these requirements: strong identification, binding to human intent, non-repudiation.

**Policy.** Every side-effecting tool call passes through a policy gate before it reaches a sandbox. Open Policy Agent (OPA) evaluates: which agent, which tool, which arguments, which tier, which time of day, was there a human approval token? Policies are code — reviewed, versioned, tested like code. The starter policy set is small and opinionated: destructive verbs (`rm -rf`, `DROP`, `terraform destroy`) always require interactive approval; production-tagged targets require approval plus a second policy; everything else is allowed in medium tier and logged. Teams tighten or loosen from there in one auditable place.

**Audit.** Every intent, plan, tool call, policy decision, and diff is emitted as OpenTelemetry events into an append-only, hash-chained log, shipped off-box. The trace correlates the whole causal chain: human intent → agent plan → policy decision → sandboxed execution → result. When the auditor (or the postmortem) asks what happened at 3:14 a.m., the answer is a trace ID, not an archaeology project. Signed provenance (Sigstore-style) on the log closes the loop: the record itself is tamper-evident.

Together these three implement, in software, the discipline the first essay assigned to humans: least privilege, blast-radius thinking, and "trust the beast exactly as far as your verification reaches."

## L5 — the agent kernel: `bashosd`

The heart of the system is a single supervised daemon — call it `bashosd` — written in a boring, reliable systems language (Rust or Go; pick Rust for the memory-safety story in a security-critical component). It is deliberately *not* an inference engine and *not* an agent framework. It is the resource manager the metaphor promised, with five subsystems:

1. **Scheduler.** An intent queue. Interactive sessions get priority; background jobs ("re-run the backup verification nightly, report anomalies") run on timers; long jobs checkpoint so a reboot doesn't lose a half-finished migration. Concurrency limits per agent and per model route — because a runaway agent fleet is a denial-of-service against your own inference budget.
2. **Session manager.** Sessions are durable objects: detach from an SSH session, reattach from the web console, and the agent conversation — plan state, pending approvals — is where you left it. `tmux` semantics for agent work.
3. **Context manager.** Assembles the working set per task: the right `AGENTS.md`, the relevant skills, retrieval results from the vector index, recent session history — under an explicit token budget. Paging for intent.
4. **Tool broker.** Speaks Model Context Protocol (MCP) to tool servers and Agent Client Protocol (ACP) to terminals/editors, so any compliant agent or front-end plugs in. But the broker's *preference order* is deliberate: small local CLIs first, MCP servers second — a focused CLI call costs a couple of orders of magnitude fewer tokens than a fat protocol round-trip, and the Unix philosophy is now a cost-optimization strategy. Every brokered call carries the agent's SPIFFE identity and passes the L4 gate.
5. **Memory manager.** Owns the read/write discipline on `/var/lib/bashos/memory/` — write-through to git, no unversioned state.

Note what `bashosd` does *not* contain: a specific model, a specific agent's reasoning loop. Claude Code, Codex CLI, Gemini CLI, OpenCode — any of them can run *on* bashOS as the reasoning engine, the way any POSIX program runs on Linux. The OS supplies scheduling, identity, policy, sandboxes, memory, and audit; the agent supplies the thinking. That separation is the whole bet: reasoning engines will churn, the resource-management layer shouldn't.

## L6 — the interface: the shell, bilingual

The user-facing surface is a shell that is bash-compatible — every script you own still runs — with one addition: an intent channel. A line starting with `::` goes to the agent kernel instead of the parser:

```bash
$ df -h /var                          # POSIX, runs as always
$ :: why is /var filling up, and propose a cleanup I can review
  → plan: check journald retention, docker image cache, core dumps
  → found: 11 GB of container images unused for 90+ days
  → proposed: prune list (diff attached). approve? [y/N/edit]
```

The two languages interleave in one session, one history, one context. Alongside the shell: SSH (it's still the appliance's front door), a terminal user interface (TUI) dashboard for watching agent sessions and pending approvals, and ACP compatibility so Zed, the Microsoft Intelligent Terminal fork, or any ACP client can drive the same kernel. The web console exists for the approval queue on your phone — because the 3 a.m. page where you approve a remediation diff from bed is the actual killer feature.

## The stack, on one page

| Layer | Component | Choice (MVP) | Why |
|---|---|---|---|
| L0 | Base OS | bootc image, Fedora CoreOS lineage | Immutable, atomic, provisionable, mainstream |
| L0 | Init/supervision | systemd | Boring, universal, socket activation for `bashosd` |
| L1 | Model gateway | LiteLLM (swappable) | One API, routing, metering, key custody |
| L1 | Local inference | llama.cpp / Ollama; vLLM on GPU | Data-local lane for sensitive/always-on work |
| L2 | Hard sandbox | Firecracker | Sub-second disposable microVMs |
| L2 | Tool sandbox | bubblewrap + Landlock + seccomp | Kernel-enforced, near-zero overhead |
| L2 | Services | podman (rootless) | Approved long-running agent workloads |
| L3 | Context | AGENTS.md + git-backed skills/memory | Inspectable with cat, revertible with git |
| L3 | Retrieval | SQLite-vec (embedded) | No extra service; data never leaves box |
| L4 | Identity | SPIFFE/SPIRE | Short-lived per-agent credentials, CNCF standard |
| L4 | Policy | OPA | Policy-as-code gate on every side effect |
| L4 | Audit | OpenTelemetry + hash-chained log | Traceable causal chain, tamper-evident |
| L5 | Agent kernel | `bashosd` (Rust) | Scheduler, sessions, context, broker, memory |
| L5 | Protocols | MCP + ACP | Any compliant agent or front-end plugs in |
| L6 | Shell | bash-compatible + `::` intent channel | Zero migration cost, one history, one context |

## The MVP: three phases, each independently useful

The trap in OS projects is building the bottom first and shipping nothing for a year. Invert it — each phase is a usable product, and each de-risks the next.

**Phase 1 — the daemon on any box (6–8 weeks of focused work).** Skip the distro entirely. Ship `bashosd` as a systemd service installable on any existing Linux host, plus the `::` shell hook as a bash plugin. Subsystems: session manager, context manager, tool broker fronting *one* existing agent CLI, bubblewrap-tier sandboxing, OPA gate with the starter policy set, file-based audit log. No SPIRE yet — Unix users and sudo rules approximate identity. **What you learn:** whether the intent-channel workflow actually beats running the agent CLI raw, and whether the policy gate's friction is tolerable. If Phase 1 isn't obviously better than a bare agent CLI, stop — the distro won't save it.

**Phase 2 — the appliance image (the next quarter).** Build the bootc image: immutable base, Ignition provisioning, `bashosd` and the model gateway baked in, Firecracker tier added, local-inference lane on boxes with the hardware, TUI dashboard and web approval queue. This is the demo that sells the concept: boot a fresh virtual machine (VM) from the image, feed it an Ignition file and an `AGENTS.md`, and have a governed agent workstation in ninety seconds.

**Phase 3 — the fleet (when someone actually needs it).** SPIRE rollout for real agent identity, off-box audit shipping, multi-node scheduling ("run this against all staging boxes"), agent-to-agent delegation with policy inheritance. This is where the appliance becomes infrastructure — and where the enterprise conversation (the auditor, the CISO) already has answers because L4 existed from Phase 1.

**Explicit non-goals**, because an MVP is defined by its refusals: no custom reasoning loop (bring an existing agent), no custom model (bring any model), no GUI desktop (it's an appliance), no Kubernetes operator until Phase 3 demands it, and no autonomous-by-default anything — unattended operation is a per-policy, per-target opt-in, forever.

## What could kill it, named honestly

Three risks deserve to be in the document rather than discovered later. First, **the vendors may absorb the layer**: if the agent CLIs each grow their own scheduler, policy gate, and identity story, bashOS's kernel becomes redundant per-vendor — the bet is that *cross-vendor* governance is precisely what no single vendor will build. Second, **policy fatigue**: if the OPA gate nags too often, humans will rubber-stamp, and the audit trail becomes theater — the starter policies must be tuned so approval interrupts are rare and meaningful. Third, **the sandbox escape**: bubblewrap and friends have had CVEs and will again; that is exactly why the hard tier is a hardware boundary and the base is immutable — defense in depth is the architecture admitting any single layer can fail.

## Next step

The honest summary: every component in this stack exists today, is open source or has an open standard, and is running in production somewhere — what does not yet exist is the assembly. That is a systems-integration project, not a research program, and Phase 1 is small enough for one motivated engineer with a quarter of nights and weekends.

If you're an IT lead looking at this and thinking "I want the governed-agent workstation but not the build project," that gap — assembling governed AI on infrastructure you control — is exactly the kind of work we scope. [Get in touch](/contact/) and bring your ugliest runbook.