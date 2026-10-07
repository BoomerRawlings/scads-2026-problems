"""Read bundled defaults; keep writable output in the caller's workspace."""
from __future__ import annotations

import atexit
from contextlib import ExitStack
from functools import lru_cache
from importlib.resources import as_file, files
import json
import os
from pathlib import Path

from .errors import AnalyticsError


ASSETS = (
    "config/development.json",
    "config/catalog.json",
    "config/mapping.json",
    "fixtures/manifest.json",
    "fixtures/requests.jsonl",
)
_resources = ExitStack()
atexit.register(_resources.close)


@lru_cache(maxsize=None)
def asset_path(name: str) -> Path:
    """Return a bundled asset path, valid until this process exits.

    Normal wheel installs read directly from the package. Resource extraction,
    if required by a loader, uses importlib's temporary files, never runs_dir.
    """
    if name not in ASSETS:
        raise ValueError("Unknown bundled asset")
    resource = files("analytics311").joinpath("assets", *name.split("/"))
    return Path(_resources.enter_context(as_file(resource))).resolve()


def default_config_path() -> Path:
    return asset_path("config/development.json")


def load_profile(config_path=None, *, workdir=None) -> tuple[Path, dict]:
    """Resolve a profile without creating or modifying any files.

    Explicit profiles, including ANALYTICS311_CONFIG, use profile-relative paths.
    The bundled profile always reads bundled assets and writes to workdir/runs
    (the current directory by default), including when passed explicitly by a
    CLI or background worker. Custom profiles retain their own runs_dir setting.
    """
    chosen = config_path or os.environ.get("ANALYTICS311_CONFIG")
    path = Path(chosen).resolve() if chosen else default_config_path()
    try:
        config = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise AnalyticsError("invalid_configuration", f"Cannot read JSON file: {path.name}") from exc
    if not isinstance(config, dict):
        raise AnalyticsError("invalid_configuration", "Configuration must be a JSON object")
    if path == default_config_path():
        config.update(
            fixture_path=str(asset_path("fixtures/requests.jsonl")),
            manifest_path=str(asset_path("fixtures/manifest.json")),
            catalog_path=str(asset_path("config/catalog.json")),
            runs_dir=str((Path(workdir) if workdir is not None else Path.cwd()).resolve() / "runs"),
        )
    else:
        for key in ("fixture_path", "manifest_path", "catalog_path", "runs_dir"):
            if key in config:
                try:
                    config[key] = str((path.parent / config[key]).resolve())
                except (TypeError, ValueError) as exc:
                    raise AnalyticsError("invalid_configuration", f"Invalid {key} path") from exc
    return path, config
