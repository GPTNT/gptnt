from __future__ import annotations

from pathlib import Path  # noqa: TC003  (Pydantic resolves this environment field at runtime)

from pydantic import Field, RedisDsn
from pydantic_settings import BaseSettings

MANUAL_ARTIFACTS_ENV = "GPTNT_MANUAL_ARTIFACTS"


class RuntimeSettings(BaseSettings):
    """Runtime service endpoints and prepared manual references supplied to player processes.

    Each field keeps its own env-var name via `validation_alias`, so the EM vars (`GPTNT_EM_*`) and
    the conventional `REDIS_DSN` coexist without a forced prefix. Manual artifact references are
    populated by `gptnt run` and are not user-authored configuration.
    """

    em_host: str = Field(default="localhost", validation_alias="GPTNT_EM_HOST")
    em_port: int = Field(default=8085, validation_alias="GPTNT_EM_PORT")
    redis_dsn: RedisDsn = Field(
        default=RedisDsn("redis://localhost:6379"), validation_alias="REDIS_DSN"
    )
    manual_artifacts: dict[str, Path] = Field(
        default_factory=dict, validation_alias=MANUAL_ARTIFACTS_ENV
    )
    """Prepared manual paths keyed by the runtime digest of their manual profile."""

    @property
    def em_base_url(self) -> str:
        """Base URL of the experiment manager."""
        return f"http://{self.em_host}:{self.em_port}"

    @property
    def em_health_url(self) -> str:
        """Health-check URL of the experiment manager."""
        return f"{self.em_base_url}/health"
