"""Configuration layer with defaults and environment variables."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class TrackerConfig(BaseSettings):
    """Issue tracker configuration."""

    model_config = SettingsConfigDict(env_prefix="SYMPHONY_TRACKER_")

    # Linear configuration
    linear_api_key: str | None = None
    linear_api_url: str = "https://api.linear.app/graphql"
    linear_team_id: str | None = None
    linear_project_id: str | None = None


class WorkspaceConfig(BaseSettings):
    """Workspace management configuration."""

    model_config = SettingsConfigDict(env_prefix="SYMPHONY_WORKSPACE_")

    base_path: Path = Field(default=Path("./workspaces"))
    template_path: Path | None = None
    cleanup_on_success: bool = True
    cleanup_on_failure: bool = False
    max_workspaces: int = 10
    pre_hooks: list[str] = Field(default_factory=list)
    post_hooks: list[str] = Field(default_factory=list)


class AgentConfig(BaseSettings):
    """Agent runner configuration."""

    model_config = SettingsConfigDict(env_prefix="SYMPHONY_AGENT_")

    executable: str = "codex"
    timeout_seconds: int = 3600  # 1 hour
    retry_limit: int = 3
    retry_delay_seconds: float = 60.0
    max_concurrent: int = 1
    protocol_version: str = "1.0"


class ServerConfig(BaseSettings):
    """HTTP server configuration."""

    model_config = SettingsConfigDict(env_prefix="SYMPHONY_SERVER_")

    host: str = "0.0.0.0"
    port: int = 8080
    debug: bool = False
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])


class LoggingConfig(BaseSettings):
    """Logging configuration."""

    model_config = SettingsConfigDict(env_prefix="SYMPHONY_LOG_")

    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    file_path: Path | None = None


class Config(BaseSettings):
    """Main Symphony configuration."""

    model_config = SettingsConfigDict(
        env_prefix="SYMPHONY_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    # Core settings
    workflow_path: Path = Field(default=Path("./WORKFLOW.md"))
    state_path: Path = Field(default=Path("./.symphony/state.json"))
    poll_interval_seconds: float = 30.0

    # Sub-configurations
    tracker: TrackerConfig = Field(default_factory=TrackerConfig)
    workspace: WorkspaceConfig = Field(default_factory=WorkspaceConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    @classmethod
    def from_env(cls) -> Config:
        """Load configuration from environment variables."""
        return cls()

    @classmethod
    def from_file(cls, path: Path) -> Config:
        """Load configuration from a file (YAML or JSON)."""
        import json

        import yaml

        content = path.read_text()
        if path.suffix in (".yaml", ".yml"):
            data = yaml.safe_load(content)
        else:
            data = json.loads(content)

        # Flatten nested config for pydantic-settings
        flat_data = cls._flatten_dict(data, "SYMPHONY")
        for key, value in flat_data.items():
            os.environ[key] = str(value)

        return cls.from_env()

    @staticmethod
    def _flatten_dict(d: dict[str, Any], prefix: str) -> dict[str, str]:
        """Flatten nested dict to environment variable format."""
        result: dict[str, str] = {}
        for key, value in d.items():
            env_key = f"{prefix}_{key.upper()}"
            if isinstance(value, dict):
                result.update(Config._flatten_dict(value, env_key))
            elif isinstance(value, list):
                result[env_key] = ",".join(str(v) for v in value)
            else:
                result[env_key] = str(value)
        return result


@lru_cache
def get_config() -> Config:
    """Get cached configuration instance."""
    return Config.from_env()


def clear_config_cache() -> None:
    """Clear the configuration cache."""
    get_config.cache_clear()
