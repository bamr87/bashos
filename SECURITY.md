# Security Policy

> Which bashOS versions get security fixes, how to report a vulnerability privately, what is in scope, and how fast you will hear back.

## Supported versions

| Version | Supported |
| --- | --- |
| The latest release (PyPI, GitHub release, GHCR image) | ✅ |
| `main` | ✅ |
| Anything older | ❌ |

Security fixes ship as a new patch release, cut by pushing a `vX.Y.Z` tag (see [CONTRIBUTING.md § Releasing](CONTRIBUTING.md#releasing)).

## Reporting a vulnerability

**Do not open a public issue.** Report privately through GitHub's [private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability) on this repository (**Security → Report a vulnerability**), or email **amr.abdel@gmail.com**.

Please include the version or commit, what an attacker can do, and the steps to reproduce.

## Scope

bashOS bridges a Claude Code login into an engine process and serves a local GUI, so these are the surfaces we most want to hear about:

- **Tool-policy bypass** — any way to make the engine run a tool, a `bash` command or an outbound call that the deny-by-default ruleset in `src/bashos/opencode/policy.py` does not allow. That file is the only place bashOS's blast radius is meant to widen.
- **Credential leakage** — the Claude Code OAuth token or `ANTHROPIC_API_KEY` reaching disk, the generated `opencode.jsonc`, logs or traces. `src/bashos/opencode/auth.py` is designed to keep the credential in the engine's environment only.
- **GUI guard bypass** — reaching the `bashos gui` API from another origin, another host or another local process without the per-process token enforced by `src/bashos/gui/server.py` (loopback bind, Host and Origin checks, token).
- **Remote probe injection** — getting `bashos remote` to run anything on a dev box beyond the fixed read-only probes in `remote.PROBES` (`src/bashos/remote.py`).

## Response window

You will get an acknowledgement **within 7 days**. We then agree a fix timeline with you, disclose in a GitHub security advisory once a fix is released, and credit you in it unless you ask us not to.
