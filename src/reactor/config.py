"""Validated local configuration; secrets are never included in representations."""

from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Mapping

from dotenv import dotenv_values


class ConfigurationError(ValueError):
    pass


def _required(values: Mapping[str, str | None], name: str) -> str:
    value = (values.get(name) or "").strip()
    if not value or value.startswith(("replace-with", "wss://your-project")):
        raise ConfigurationError(f"{name} is missing or a placeholder")
    return value


@dataclass(frozen=True)
class AgentConfig:
    livekit_url: str
    livekit_key: str = field(repr=False)
    livekit_secret: str = field(repr=False)
    google_key: str = field(repr=False)
    model: str = ""
    mode: str = "benchmark"
    free_quota_confirmed: bool = False

    @classmethod
    def from_values(cls, values: Mapping[str, str | None]) -> "AgentConfig":
        url = _required(values, "LIVEKIT_URL")
        if not url.startswith("wss://") or "/" in url.removeprefix("wss://"):
            raise ConfigurationError("LIVEKIT_URL must be a wss:// LiveKit project hostname")
        mode = values.get("REACTOR_MODE") or "benchmark"
        if mode not in ("benchmark", "kitchen"):
            raise ConfigurationError("REACTOR_MODE must be benchmark or kitchen")
        model = _required(values, "GOOGLE_LIVE_MODEL")
        return cls(
            livekit_url=url,
            livekit_key=_required(values, "LIVEKIT_API_KEY"),
            livekit_secret=_required(values, "LIVEKIT_API_SECRET"),
            google_key=_required(values, "GOOGLE_API_KEY"),
            model=model, mode=mode,
            free_quota_confirmed=(values.get("REACTOR_FREE_QUOTA_CONFIRMED") == "yes"),
        )

    def require_live_access(self) -> None:
        if not self.free_quota_confirmed:
            raise ConfigurationError("Confirm the selected model's free quota and set REACTOR_FREE_QUOTA_CONFIRMED=yes")


def load_config(path: Path | str = ".env.local") -> AgentConfig:
    target = Path(path)
    if not target.is_file():
        if (path == ".env.local" or str(path) == ".env.local") and Path(".env").is_file():
            target = Path(".env")
        else:
            raise ConfigurationError("Create .env.local in the repository root")
    values = dotenv_values(target)
    # Permit nonsecret one-off run settings without rewriting the user's API keys.
    for name in ("GOOGLE_LIVE_MODEL", "REACTOR_FREE_QUOTA_CONFIRMED", "REACTOR_MODE"):
        if name in os.environ:
            values[name] = os.environ[name]
    return AgentConfig.from_values(values)
