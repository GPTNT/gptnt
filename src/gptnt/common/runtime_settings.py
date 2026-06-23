from __future__ import annotations

from pydantic import Field, RedisDsn
from pydantic_settings import BaseSettings


class RuntimeSettings(BaseSettings):
    """Where the runtime services live: the experiment-manager endpoint and the Redis DSN.

    Each field keeps its own env-var name via `validation_alias`, so the EM vars (`GPTNT_EM_*`) and
    the conventional `REDIS_DSN` coexist without a forced prefix.
    """

    em_host: str = Field(default="localhost", validation_alias="GPTNT_EM_HOST")
    em_port: int = Field(default=8085, validation_alias="GPTNT_EM_PORT")
    redis_dsn: RedisDsn = Field(
        default=RedisDsn("redis://localhost:6379"), validation_alias="REDIS_DSN"
    )

    @property
    def em_base_url(self) -> str:
        """Base URL of the experiment manager."""
        return f"http://{self.em_host}:{self.em_port}"

    @property
    def em_health_url(self) -> str:
        """Health-check URL of the experiment manager."""
        return f"{self.em_base_url}/health"
