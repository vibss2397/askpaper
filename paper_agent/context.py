from pathlib import Path

import yaml

from . import config

CONTEXT_FILE = "context.yaml"


def _get_context_path() -> Path:
    vault_path = config._get_vault_path()
    return vault_path / config.CONFIG_DIR / CONTEXT_FILE


def _load_context() -> dict:
    path = _get_context_path()
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


def _save_context(data: dict) -> None:
    path = _get_context_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(data, f)


def get_last_space() -> str | None:
    return _load_context().get("last_space")


def get_last_source() -> dict:
    ctx = _load_context()
    return {
        "url": ctx.get("last_source_url", ""),
        "title": ctx.get("last_source_title", ""),
        "app": ctx.get("last_source_app", ""),
    }


def get_active_paper_id() -> str | None:
    return _load_context().get("active_paper_id")


def get_last_session_file() -> str | None:
    return _load_context().get("last_session_file")


def update_context(
    space: str | None = None,
    source_url: str | None = None,
    source_title: str | None = None,
    source_app: str | None = None,
    paper_id: str | None = None,
    session_file: str | None = None,
) -> None:
    ctx = _load_context()
    if space is not None:
        ctx["last_space"] = space
    if source_url is not None:
        ctx["last_source_url"] = source_url
    if source_title is not None:
        ctx["last_source_title"] = source_title
    if source_app is not None:
        ctx["last_source_app"] = source_app
    if paper_id is not None:
        ctx["active_paper_id"] = paper_id
    if session_file is not None:
        ctx["last_session_file"] = session_file
    _save_context(ctx)
