from functools import lru_cache
from typing import List

from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    app_name: str = "Portal de Sastrería"
    secret_key: str = Field(
        ...,
        min_length=32,
        description="Secret key for JWT signing. Must be at least 32 characters.",
    )
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24
    database_url: str = Field(
        "sqlite:///./sastreria.db",
        description="SQLAlchemy database URL. Defaults to a local SQLite database.",
    )
    cors_origins: List[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"],
        description="Origins allowed to make CORS requests.",
    )
    api_host: str = Field(
        "127.0.0.1",
        description="Host interface where the API should listen.",
    )
    api_port: int = Field(
        8000,
        ge=0,
        le=65535,
        description="Port number where the API should listen.",
    )
    api_reload: bool = Field(
        False,
        description="Enable auto reload when running the development server via python -m app.main.",
    )

    contifico_base_url: str = Field(
        "https://api.contifico.com/sistema/api/v1",
        description=(
            "Base URL for Contifico API requests documented at https://contifico.github.io/. "
            "Loaded from the CONTIFICO_BASE_URL environment variable or the .env file."
        ),
    )
    contifico_api_key: str | None = Field(
        None,
        description=(
            "API key issued by Contifico. Loaded from the CONTIFICO_API_KEY environment "
            "variable or the .env file."
        ),
    )
    contifico_api_token: str | None = Field(
        None,
        description=(
            "API token used alongside the API key to authenticate Contifico requests. "
            "Loaded from the CONTIFICO_API_TOKEN environment variable or the .env file."
        ),
    )
    contifico_company_numeric_id: str | None = Field(
        None,
        description=(
            "Optional Contifico numeric company identifier used for the 'empresa_id' query "
            "parameter. Loaded from CONTIFICO_COMPANY_NUMERIC_ID or the .env file."
        ),
    )
    contifico_timeout_seconds: float = Field(
        30.0,
        ge=0,
        description=(
            "HTTP timeout (in seconds) for Contifico requests. Loaded from "
            "CONTIFICO_TIMEOUT_SECONDS or the .env file."
        ),
    )
    contifico_rate_limit_per_minute: int = Field(
        50,
        ge=1,
        description=(
            "Maximum number of Contifico requests permitted per minute before "
            "triggering retries. Loaded from CONTIFICO_RATE_LIMIT_PER_MINUTE or the .env file."
        ),
    )
    contifico_max_retries: int = Field(
        3,
        ge=0,
        description=(
            "Maximum number of retries for transient Contifico errors. Loaded from "
            "CONTIFICO_MAX_RETRIES or the .env file."
        ),
    )
    contifico_retry_backoff_seconds: float = Field(
        2.0,
        ge=0,
        description=(
            "Base backoff interval (in seconds) between Contifico retry attempts. "
            "Loaded from CONTIFICO_RETRY_BACKOFF_SECONDS or the .env file."
        ),
    )

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache()
def get_settings() -> Settings:
    """Return cached settings instance."""

    try:
        return Settings()
    except ValidationError as exc:
        secret_key_errors = [
            error for error in exc.errors() if error.get("loc") == ("secret_key",)
        ]
        if secret_key_errors:
            raise RuntimeError(
                "SECRET_KEY no está configurada o es demasiado corta. "
                "Define la variable de entorno SECRET_KEY o agrégala al archivo .env "
                "con un valor de al menos 32 caracteres."
            ) from exc
        raise
