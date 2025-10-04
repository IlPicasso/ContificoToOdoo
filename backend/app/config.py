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
