"""Environment-driven configuration.

Everything is overridable via env vars (or a .env file you source before
launching). Defaults match the machine this was scaffolded on.
"""

import os
from pathlib import Path


def _env_path(name: str, default: str) -> Path:
    return Path(os.environ.get(name, default)).expanduser()


# Where the stack lives. The vault is just a folder of markdown — Obsidian
# renders it on every device, sync is whatever the vault already uses.
VAULT_PATH: Path = _env_path("POPSTACK_VAULT", "~/Documents/vault")
STACK_DIRNAME: str = os.environ.get("POPSTACK_DIR", "Stack")


def _env_paths(name: str, default: list[Path]) -> list[Path]:
    raw = os.environ.get(name)
    if not raw:
        return default
    return [Path(p.strip()).expanduser() for p in raw.split(",") if p.strip()]


# Knowledge vaults grounding searches (the user has several complementary
# vaults). Set POPSTACK_VAULTS as a comma-separated
# list; the Stack vault is always included. Grounding labels each hit with the
# vault it came from, which is what makes cross-vault connections possible.
VAULTS: list[Path] = _env_paths("POPSTACK_VAULTS", [VAULT_PATH])
if VAULT_PATH not in VAULTS:
    VAULTS = [VAULT_PATH, *VAULTS]

# Where the agent writes NEW notes. Defaults to a clearly-marked quarantine
# folder in the primary vault so agent-authored notes never silently mix into
# your KB until you file them. Set NOTES_VAULT to write into one of
# your knowledge vaults; NOTES_DIR is the subfolder.
NOTES_VAULT: Path = _env_path("POPSTACK_NOTES_VAULT", str(VAULT_PATH))
NOTES_DIR: str = os.environ.get("POPSTACK_NOTES_DIR", "popstack")

# Where cloned repos land (for codebase learning goals).
WORKSPACE: Path = _env_path("POPSTACK_WORKSPACE", "~/.popstack/repos")

# Active-pool cap. Pops draw only from active; overflow lands in the
# reservoir. Small on purpose — see the choice-overload moderators.
ACTIVE_LIMIT: int = int(os.environ.get("POPSTACK_ACTIVE_LIMIT", "20"))

# Default park cooldown (hours) so a just-parked task can't immediately re-pop.
DEFAULT_COOLDOWN_HOURS: float = float(os.environ.get("POPSTACK_COOLDOWN_HOURS", "4"))

# Zotero. Local API first (Zotero 7+: Settings → Advanced → "Allow other
# applications on this computer to communicate with Zotero"). The web API is
# used for writes (add by DOI) when a key is configured.
ZOTERO_LOCAL_URL: str = os.environ.get("ZOTERO_LOCAL_URL", "http://localhost:23119/api/users/0")
ZOTERO_API_KEY: str = os.environ.get("ZOTERO_API_KEY", "")
ZOTERO_USER_ID: str = os.environ.get("ZOTERO_USER_ID", "")

# AnkiConnect (Anki add-on 2055492159). Optional — tools degrade gracefully.
ANKI_URL: str = os.environ.get("ANKI_URL", "http://localhost:8765")
ANKI_DEFAULT_DECK: str = os.environ.get("ANKI_DEFAULT_DECK", "popstack")

# HTTP transport (for the claude.ai connector via Tailscale Funnel).
HOST: str = os.environ.get("POPSTACK_HOST", "127.0.0.1")
PORT: int = int(os.environ.get("POPSTACK_PORT", "8444"))
# If set, HTTP requests must carry "Authorization: Bearer <token>".
AUTH_TOKEN: str = os.environ.get("POPSTACK_AUTH_TOKEN", "")


def stack_root() -> Path:
    return VAULT_PATH / STACK_DIRNAME
