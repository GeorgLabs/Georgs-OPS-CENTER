"""Settings. They come from environment variables (prefix OPS_) or from the .env file.

Rule number one of secure software: secrets never live in the source code.
`setup.bat` / `setup.sh` generates a random OPS_SECRET_KEY for you in `.env`.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OPS_", env_file=ROOT / ".env", extra="ignore")

    secret_key: SecretStr  # signs the login tokens - required, no default on purpose
    database_url: str = f"sqlite:///{(ROOT / 'opscenter.db').as_posix()}"
    dev: bool = False  # dev tools (traffic panel, Mission Control, /docs) - off unless asked for
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 30
    online_window_seconds: int = 60  # a host counts as "online" if it reported this recently

    @field_validator("secret_key")
    @classmethod
    def _long_enough(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 32:
            raise ValueError("OPS_SECRET_KEY must be at least 32 characters long")
        return value


@lru_cache
def get_settings() -> Settings:
    try:
        return Settings()  # type: ignore[call-arg]
    except ValidationError as exc:
        first = exc.errors()[0]
        raise SystemExit(
            "\nOps Center is not configured yet.\n"
            "Run setup.bat (Windows) or ./setup.sh to create your .env file.\n"
            f"Problem: {'.'.join(str(p) for p in first['loc'])}: {first['msg']}\n"
        ) from exc
