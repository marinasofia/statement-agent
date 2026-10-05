"""
Client and format config loader.

Architecture:
- formats_library/{format_id}.yaml  → canonical format definitions (universal)
- clients/{client_id}/settings.yaml → client metadata (id, display name)
- clients/{client_id}/overrides/{format_id}.yaml → optional per-client tweaks

The format library is shared source. A client's overrides deep-merge over
the library entry, so an override only states what differs.

Security model:
- CLIENT_ID is set once at process boot via environment variable.
- All client_id values are validated against the on-disk allowlist (folders
  under clients/).
- All format_id values are validated against the on-disk allowlist (yamls
  under formats_library/).
- File paths are resolved with realpath and checked against their base
  directories (defense in depth against path traversal).
"""

import os
import yaml
import logging
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from pydantic import BaseModel
from typing import Optional

class ClientSettings(BaseModel):
    client_id: str
    client_name: str

class FieldDefinition(BaseModel):
    name: str
    label: str
    type: str
    required: bool = False
    description: Optional[str] = None

class DetectionConfig(BaseModel):
    signatures: list = []
    min_matches: int = 1

class ExcelOutput(BaseModel):
    columns: list[str] = []

class FormatConfig(BaseModel):
    format_id: str
    format_name: str
    fields: list[FieldDefinition]
    detection: DetectionConfig = DetectionConfig()
    excel_output: ExcelOutput = ExcelOutput()


logger = logging.getLogger(__name__)

# --- Base paths, resolved once at import time ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CLIENTS_DIR = (PROJECT_ROOT / "clients").resolve()
LIBRARY_DIR = (PROJECT_ROOT / "formats_library").resolve()


# ---------------------------------------------------------------------------
# Allowlist helpers (filesystem-derived, never hardcoded)
# ---------------------------------------------------------------------------

def _list_client_ids() -> list[str]:
    """Every folder under clients/ is a known client."""
    if not CLIENTS_DIR.is_dir():
        return []
    return sorted(p.name for p in CLIENTS_DIR.iterdir() if p.is_dir())


def _list_format_ids() -> list[str]:
    """Every yaml under formats_library/ is a known format."""
    if not LIBRARY_DIR.is_dir():
        return []
    return sorted(p.stem for p in LIBRARY_DIR.iterdir() if p.suffix == ".yaml")


def _safe_resolve(path: Path, base_dir: Path) -> Path:
    """
    Resolve a path and verify it stays inside base_dir.
    Raises PermissionError if the resolved path escapes base_dir.
    """
    resolved = path.resolve()
    if not str(resolved).startswith(str(base_dir) + os.sep):
        raise PermissionError(f"Path escapes base directory: {resolved}")
    return resolved


# ---------------------------------------------------------------------------
# Client identity (env-var-driven)
# ---------------------------------------------------------------------------

def get_client_id() -> str:
    """
    Read CLIENT_ID from environment, validate against on-disk allowlist.
    Falls back to 'default' for local development.
    """
    client_id = os.getenv("CLIENT_ID", "default")

    allowed = _list_client_ids()
    if client_id not in allowed:
        raise ValueError(
            f"CLIENT_ID '{client_id}' is not a valid client. "
            f"Known clients: {allowed}"
        )

    return client_id


# ---------------------------------------------------------------------------
# Settings loader
# ---------------------------------------------------------------------------

@lru_cache(maxsize=32)
def load_client_settings(client_id: str) -> dict:
    """Load clients/{client_id}/settings.yaml."""
    if client_id not in _list_client_ids():
        raise ValueError(f"Unknown client_id: '{client_id}'")

    path = _safe_resolve(
        CLIENTS_DIR / client_id / "settings.yaml",
        CLIENTS_DIR,
    )

    if not path.is_file():
        raise FileNotFoundError(f"Settings not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        settings = yaml.safe_load(f) or {}

    logger.info(f"Loaded settings for client='{client_id}'")
    return ClientSettings(**settings).model_dump()


# ---------------------------------------------------------------------------
# Format loader (library + optional per-client override)
# ---------------------------------------------------------------------------

def _deep_merge(base: dict, override: dict) -> dict:
    """
    Recursively merge override into a copy of base.
    - Dicts merge recursively.
    - Lists and scalars in override fully replace base.
    """
    result = deepcopy(base)
    for key, override_value in override.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(override_value, dict)
        ):
            result[key] = _deep_merge(result[key], override_value)
        else:
            result[key] = deepcopy(override_value)
    return result


@lru_cache(maxsize=128)
def load_format_config(client_id: str, format_id: str) -> dict:
    """
    Load a format from the library, then apply the client's override if one
    exists at clients/{client_id}/overrides/{format_id}.yaml.

    Returns the merged config dict.
    """
    if client_id not in _list_client_ids():
        raise ValueError(f"Unknown client_id: '{client_id}'")
    if format_id not in _list_format_ids():
        raise ValueError(
            f"Unknown format_id '{format_id}'. "
            f"Known formats: {_list_format_ids()}"
        )

    # Load the library yaml
    library_path = _safe_resolve(
        LIBRARY_DIR / f"{format_id}.yaml",
        LIBRARY_DIR,
    )
    if not library_path.is_file():
        raise FileNotFoundError(f"Library config not found: {library_path}")

    with open(library_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    # Apply override if it exists. Missing override is normal, not an error.
    override_path = (
        CLIENTS_DIR / client_id / "overrides" / f"{format_id}.yaml"
    )
    if override_path.is_file():
        override_path = _safe_resolve(override_path, CLIENTS_DIR)
        with open(override_path, "r", encoding="utf-8") as f:
            override = yaml.safe_load(f) or {}
        config = _deep_merge(config, override)
        logger.info(
            f"Loaded format '{format_id}' for client='{client_id}' "
            f"with override applied"
        )
    else:
        logger.info(
            f"Loaded format '{format_id}' for client='{client_id}' "
            f"(no override)"
        )

    return FormatConfig(**config).model_dump()


# ---------------------------------------------------------------------------
# Library introspection (used by the detection node)
# ---------------------------------------------------------------------------

def list_available_formats(client_id: str) -> list[dict]:
    """
    Return summary metadata for every format in the library, with this
    client's overrides applied. Used by the detection node to know what
    signatures to scan against.
    """
    formats = []
    for format_id in _list_format_ids():
        cfg = load_format_config(client_id, format_id)
        formats.append({
            "format_id": cfg.get("format_id", format_id),
            "format_name": cfg.get("format_name", format_id),
            "signatures": cfg.get("detection", {}).get("signatures", []),
            "min_matches": cfg.get("detection", {}).get("min_matches", 1),
        })
    return formats