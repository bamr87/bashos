"""Claude Code OAuth → OpenCode credential bridge.

bashOS's auth posture is subscription-native: the engine runs on the Claude
Code login the user already has, not on an API key they have to mint.

    discover()  ── CLAUDE_CODE_OAUTH_TOKEN            (explicit override)
                ── ~/.claude/.credentials.json        (Linux/Windows CLI login)
                ── macOS Keychain "Claude Code-credentials"

How the credential reaches the engine matters, and the mechanism here was
chosen against the running server rather than from its docs:

* OpenCode 1.18 dropped Anthropic OAuth as a login method — its `anthropic`
  integration offers `key` and `env` only, and a stored `{"type":"oauth"}`
  credential does not register the provider at all. So the token is carried the
  way Claude Code itself carries it: as an `Authorization: Bearer` header on
  the provider, declared through `provider.anthropic.options.headers`. The
  header name must be capitalised — a lowercase `authorization` key is dropped
  before the request goes out. `apiKey` is pinned empty so a bearer token is
  never also sent as `x-api-key`.
* The wiring is injected through `OPENCODE_CONFIG_CONTENT` /
  `OPENCODE_AUTH_CONTENT`, which merge with the project config at engine start.
  Two consequences, both deliberate: **no secret is ever written to disk**, and
  bashOS never mutates `~/.local/share/opencode/auth.json` — a user who ran
  `opencode auth login` keeps exactly what they had.

`ANTHROPIC_API_KEY` remains the fallback, and takes the plain `api` credential
path that OpenCode supports natively.

Set `BASHOS_OPENCODE_AUTH=never` to wire nothing and let the engine use
whatever credentials it already has.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

PROVIDER_ID = "anthropic"

CREDENTIALS_FILE = Path.home() / ".claude" / ".credentials.json"
KEYCHAIN_SERVICE = "Claude Code-credentials"

# The beta Anthropic requires for subscription (OAuth) inference, and the
# private env var the generated provider block reads the token from — the token
# itself never appears in the config, only this name.
OAUTH_BETA = "oauth-2025-04-20"
BEARER_ENV = "BASHOS_ANTHROPIC_BEARER"

# A `claude setup-token` access token carries no refresh token. Project its
# expiry forward so the engine uses it directly instead of attempting a refresh
# it cannot perform; a genuinely expired token then fails loudly at the
# provider, which is the honest outcome.
_BEARER_TTL_MS = 30 * 24 * 60 * 60 * 1000


@dataclass(frozen=True)
class ClaudeCredential:
    """A Claude Code OAuth credential, wherever it was found."""

    access: str
    refresh: str = ""
    expires: int = 0  # epoch milliseconds
    source: str = "unknown"

    @property
    def refreshable(self) -> bool:
        return bool(self.refresh)

    @property
    def expired(self) -> bool:
        return bool(self.expires) and self.expires <= _now_ms()

    def to_opencode_auth(self) -> dict[str, object]:
        """The OAuth blob OpenCode stores for a provider."""
        expires = self.expires
        if not self.refreshable and (not expires or expires <= _now_ms()):
            expires = _now_ms() + _BEARER_TTL_MS
        return {
            "type": "oauth",
            "access": self.access,
            "refresh": self.refresh,
            "expires": int(expires),
        }


def _now_ms() -> int:
    return int(time.time() * 1000)


def _from_env() -> ClaudeCredential | None:
    token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "").strip()
    if not token:
        return None
    return ClaudeCredential(access=token, source="CLAUDE_CODE_OAUTH_TOKEN")


def _parse_credentials_blob(text: str, source: str) -> ClaudeCredential | None:
    try:
        oauth = (json.loads(text) or {}).get("claudeAiOauth") or {}
    except (json.JSONDecodeError, AttributeError):
        return None
    access = str(oauth.get("accessToken") or "").strip()
    if not access:
        return None
    return ClaudeCredential(
        access=access,
        refresh=str(oauth.get("refreshToken") or "").strip(),
        expires=int(oauth.get("expiresAt") or 0),
        source=source,
    )


def _from_credentials_file(path: Path | None = None) -> ClaudeCredential | None:
    path = path or CREDENTIALS_FILE
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    return _parse_credentials_blob(text, f"{path}")


def _from_keychain() -> ClaudeCredential | None:
    """macOS keeps the Claude Code credential in the login keychain."""
    try:
        proc = subprocess.run(
            ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    return _parse_credentials_blob(proc.stdout, f"keychain:{KEYCHAIN_SERVICE}")


def discover() -> ClaudeCredential | None:
    """Find the Claude Code OAuth credential, richest usable source first.

    The environment token wins when set — that is how a user pins a specific
    credential, and it is what CI does — even though it carries no refresh
    token. A CLI login is used otherwise, and refreshes itself.
    """
    for finder in (_from_env, _from_credentials_file, _from_keychain):
        if credential := finder():
            return credential
    return None


def anthropic_api_key() -> str | None:
    key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
    return key.strip() or None if key else None


def enabled() -> bool:
    return os.environ.get("BASHOS_OPENCODE_AUTH", "").strip().lower() != "never"


def oauth_provider_config() -> dict[str, object]:
    """The `provider.anthropic` block that carries a Claude Code bearer token.

    Declaring `env` is what makes OpenCode register the provider at all; the
    header is what actually authenticates the request.
    """
    return {
        "provider": {
            PROVIDER_ID: {
                "env": [BEARER_ENV],
                "options": {
                    "apiKey": "",  # never send an OAuth token as x-api-key
                    "headers": {
                        "Authorization": f"Bearer {{env:{BEARER_ENV}}}",
                        "anthropic-beta": OAUTH_BETA,
                    },
                },
            }
        }
    }


def api_key_credential(key: str) -> dict[str, object]:
    return {PROVIDER_ID: {"type": "api", "key": key}}


def engine_environment() -> tuple[dict[str, str], str]:
    """Environment that authenticates a freshly spawned engine.

    Returns (env additions, human description). Nothing here is written to
    disk — the child process holds the secret and dies with it.
    """
    if not enabled():
        return {}, "skipped (BASHOS_OPENCODE_AUTH=never)"
    if credential := discover():
        note = "refreshable" if credential.refreshable else "bearer, no refresh"
        if credential.expired and credential.refreshable:
            note = "EXPIRED — run `claude` to refresh"
        return (
            {
                BEARER_ENV: credential.access,
                "OPENCODE_CONFIG_CONTENT": json.dumps(oauth_provider_config()),
            },
            f"claude code oauth ← {credential.source} ({note})",
        )
    if key := anthropic_api_key():
        return (
            {"OPENCODE_AUTH_CONTENT": json.dumps(api_key_credential(key))},
            "ANTHROPIC_API_KEY (fallback — no Claude Code login found)",
        )
    return {}, "no credential found — log in with `claude`, or set ANTHROPIC_API_KEY"


def attached_credential() -> tuple[dict[str, object], str] | None:
    """What can still be installed into an engine bashOS did not start.

    An attached server's environment is already fixed, so the header route is
    closed; only the API-key credential can be pushed over the API.
    """
    if not enabled():
        return None
    if key := anthropic_api_key():
        return {"type": "api", "key": key}, "ANTHROPIC_API_KEY"
    return None
