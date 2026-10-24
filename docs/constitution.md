<!-- kit: governance v0.1.0 · seeded from bamr87/bamr87 templates/governance/. Owned by this repo after seeding;
     change it ONLY through an amendment record in docs/amendments/ (see § 8). Validate: python3 <hub>/tools/governance_lint.py check . -->
# bashos — Constitution

> The rules every change to this repo must satisfy, whoever makes it — a human or an AI agent.
> Agents read this before [AGENTS.md](../AGENTS.md) conventions, the [PRD](../PRD.md), or the
> [feature catalog](../features/features.yml). Ratified by merged PR; amended only per § 8.

## 1. Mission

PR #20 proposes/lands `bashos gui`: a GUI access layer beside the terminal, not above it. One page, seven hash-routed scenes (Overview, Console, Commands, Runs, Health, Engine, Settings), same kernel as the CLI, no-build front end.

_Source: [docs/frontend/PRD-os-shell.md](frontend/PRD-os-shell.md)._

## 2. Invariants (non-negotiable)

These rules are lifted from the repo's own agent guide; breaking one is grounds to reject a PR.

- bashOS never implements a reasoning loop. Loops call the engine, never a model directly. _(AGENTS.md)_
- Loops never get network or write tools. Never add a tool that writes, reaches the network, or spawns an agent not bound by the policy. _(AGENTS.md)_
- `opencode.jsonc` is generated, committed, and credential-free. Never hand-edit it. _(AGENTS.md)_
- Anthropic model IDs are limited to `claude-opus-5-5` (the default), `claude-sonnet-5-5` and `claude-haiku-5-5`, optionally `anthropic/`-qualified. Use no other Claude model strings. _(AGENTS.md)_
- Nothing blocks on a human. _(AGENTS.md)_
- Everything is async; never call sync `invoke` inside the kernel — use `await llm.ainvoke(...)`. _(AGENTS.md)_
- Kernel and engine code never print — emit typed events (`src/bashos/events.py`) and let the surface render them. _(AGENTS.md)_
- The desktop owns the alternate screen: kernel/engine code must never print — emit typed events (`events.py`) and let the surface render them. _(AGENTS.md)_
- Loops must short-circuit on missing args (usage) and `config.dry_run` (rendered prompt, no model call) — tests rely on the dry-run path. _(AGENTS.md)_
- Anything that could block on a human must not: approval requests are _(AGENTS.md)_
- Secrets (tokens, API keys) are never printed, logged or committed. _(fleet rule)_
- `CHANGELOG.md`, when present, is not hand-edited once release-please owns it. _(fleet rule)_

## 3. Authority and precedence

When two documents disagree, the higher one wins and the lower one is fixed in the same PR:

1. This constitution (and its ratified amendments in [docs/amendments/](amendments/))
2. [AGENTS.md](../AGENTS.md) — how to work here (commands, conventions, Definition of Done)
3. The PRD ([`docs/frontend/PRD-os-shell.md`](frontend/PRD-os-shell.md)) — what the product must do (requirement ids `FRn` / `NFRn`)
4. [features/features.yml](../features/features.yml) — what it does today (stable feature ids)
5. ADRs in [docs/adr/](adr/) and specs — why and how a specific change was made
6. Code, tests, generated files

## 4. Roles: humans and AI agents

| Actor | May | May not |
| --- | --- | --- |
| Maintainer (human) | Ratify amendments, PRD changes and releases by merging PRs; change settings, secrets, branch protection | — |
| AI agent | Read this file first; open PRs on a branch with Conventional Commit titles; update the feature catalog, PRD block and docs in the same PR as the change; propose amendments | Merge its own PRs; push to the default branch; force-push; change repo settings or branch protection; print or commit secrets; invent features or requirements (unknown = **TBD**) |

## 5. How the artifacts relate

| Artifact | Answers | Owned by | Rule |
| --- | --- | --- | --- |
| `docs/constitution.md` | What must always hold | Maintainer | Changes only by amendment (§ 8) |
| `docs/amendments/NNNN-*.md` | How and why the rules changed | Proposer → maintainer | Append-only; ratified by merged PR |
| `AGENTS.md` / `CLAUDE.md` | How to work here | Repo | Must link this file; `CLAUDE.md` imports `@AGENTS.md` |
| PRD | What the product must do | Maintainer | Requirements carry stable ids (`FRn`, `NFRn`) |
| `features/features.yml` | What the product does, where, proven how | Repo | Every user-facing feature has an id, `status`, location and `prd:` refs |
| PRD "Feature catalog" block | PRD → feature trace | Generated | `governance_lint.py prd-sync`; never hand-edit |
| `docs/adr/NNNN-*.md` | Why a hard-to-reverse decision was made | Proposer | One ADR per decision; an amendment may cite one |
| `CHANGELOG.md` | What shipped | release-please | Generated from Conventional Commits; never hand-edit |

## 6. Change process

| Change | Required in the same PR |
| --- | --- |
| Typo, docs fix, refactor with no user-visible effect | Conventional Commit title |
| New or changed user-facing feature | Entry in `features/features.yml` (`status`, `link`/`docs`, `prd:`), regenerated PRD block |
| New or changed requirement | PRD edit with a new `FRn`/`NFRn` id (ids are never reused), feature `prd:` refs updated |
| Hard-to-reverse technical decision | ADR in `docs/adr/` |
| Change to this constitution | Amendment record in `docs/amendments/` (§ 8) |

## 7. Quality gates

Every PR passes the checks the repo's guide names:

- `make test` _(AGENTS.md)_
- `make lint` _(AGENTS.md)_
- `pytest -q` _(AGENTS.md)_
- `python3 <bamr87/bamr87>/tools/governance_lint.py prd-sync . --write` _(AGENTS.md)_
- `python3 <bamr87/bamr87>/tools/governance_lint.py check .` (feature catalog ↔ PRD, constitution, amendments)

## 8. Amendments

This constitution changes only through a numbered record in [docs/amendments/](amendments/) (`NNNN-kebab-slug.md`, copied from [0000-template.md](amendments/0000-template.md)):

1. **Propose** — open a PR that adds the record (`Status: proposed`) *and* the edit to this file it describes.
   Name what it affects: constitution sections, PRD requirement ids, feature ids.
2. **Review** — the maintainer reviews; an agent never approves or merges its own amendment.
3. **Ratify** — merging the PR ratifies it. The record says `Status: ratified` and `Ratified by:` the PR.
   A rejected or withdrawn PR keeps its record with that status; numbers are never reused.
4. **Supersede** — a later amendment may replace an earlier one; mark the old record `superseded by NNNN`.

Records are append-only history: fix a ratified rule with a new amendment, never by editing an old record. [0001](amendments/0001-ratify-constitution.md) ratifies this document.
