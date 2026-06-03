"""Configuration and taste-profile loading.

Resolves paths relative to the project root, loads/validates `config.yaml` and
`taste.yaml` into Pydantic models, layers in `.env` secrets, and ensures the `data/`
output directories exist. Validation errors are raised as `ConfigError` for the CLI to
render cleanly.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import ValidationError

from investbot.models.recommendation import AppConfig, TasteProfile

# Project root = two levels up from this file (investbot/config/loader.py -> repo root).
PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.yaml"
DEFAULT_TASTE_PATH = PROJECT_ROOT / "taste.yaml"


class ConfigError(Exception):
    """Raised when configuration or taste files are missing or invalid."""


def _read_yaml(path: Path) -> dict:
    if not path.exists():
        raise ConfigError(f"File not found: {path}")
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"Expected a mapping at top level of {path}")
    return data


def resolve_path(path_str: str) -> Path:
    """Resolve a config path string against the project root unless already absolute."""
    p = Path(path_str)
    return p if p.is_absolute() else (PROJECT_ROOT / p)


def load_config(path: str | Path | None = None) -> AppConfig:
    """Load and validate config.yaml, applying .env overrides for IB connection."""
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    cfg_path = Path(path) if path else DEFAULT_CONFIG_PATH
    raw = _read_yaml(cfg_path)
    try:
        config = AppConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(f"Invalid config in {cfg_path}:\n{exc}") from exc

    # .env overrides (secrets / environment-specific connection settings).
    if host := os.getenv("IB_HOST"):
        config.ibkr.host = host
    if port := os.getenv("IB_PORT"):
        try:
            config.ibkr.port = int(port)
        except ValueError as exc:
            raise ConfigError(f"IB_PORT must be an integer, got {port!r}") from exc
    if client_id := os.getenv("IB_CLIENT_ID"):
        try:
            config.ibkr.client_id = int(client_id)
        except ValueError as exc:
            raise ConfigError(f"IB_CLIENT_ID must be an integer, got {client_id!r}") from exc

    ensure_data_dirs(config)
    return config


def load_taste(path: str | Path | None = None) -> TasteProfile:
    """Load and validate taste.yaml."""
    taste_path = Path(path) if path else DEFAULT_TASTE_PATH
    raw = _read_yaml(taste_path)
    try:
        return TasteProfile.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(f"Invalid taste profile in {taste_path}:\n{exc}") from exc


def taste_path(path: str | Path | None = None) -> Path:
    return Path(path) if path else DEFAULT_TASTE_PATH


def ensure_data_dirs(config: AppConfig) -> None:
    """Create snapshot/memo/fixture dirs and the recommendations file if absent."""
    for d in (config.data.snapshots_dir, config.data.memos_dir, config.data.fixtures_dir):
        resolve_path(d).mkdir(parents=True, exist_ok=True)
    rec_file = resolve_path(config.data.recommendations_file)
    rec_file.parent.mkdir(parents=True, exist_ok=True)
    rec_file.touch(exist_ok=True)


def get_anthropic_api_key() -> str | None:
    """Return the Anthropic API key from the environment (loaded from .env)."""
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    return os.getenv("ANTHROPIC_API_KEY")


def today_str() -> str:
    """Local date as YYYY-MM-DD, used for snapshot/memo filenames."""
    return date.today().isoformat()


# Convenience path builders -------------------------------------------------

def snapshot_path(config: AppConfig, day: str | None = None) -> Path:
    day = day or today_str()
    return resolve_path(config.data.snapshots_dir) / f"{day}_portfolio.json"


def memo_path(config: AppConfig, day: str | None = None) -> Path:
    day = day or today_str()
    return resolve_path(config.data.memos_dir) / f"{day}_memo.md"


def fixture_path(config: AppConfig, name: str = "sample_portfolio.json") -> Path:
    return resolve_path(config.data.fixtures_dir) / name


def recommendations_path(config: AppConfig) -> Path:
    return resolve_path(config.data.recommendations_file)
