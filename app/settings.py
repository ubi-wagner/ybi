from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Railway injects DATABASE_URL when a Postgres service is attached."""
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://postgres:postgres@localhost:5432/ybi"
    period: str = "2025"
    env: str = "dev"
    storage_dir: str = "storage"
    #: How long a session lasts before it has to be signed in
    #: again. A plain expiry, not an idle timer: a fixed lifetime
    #: is the one people can reason about, and a sliding one
    #: renews itself forever on a screen left open. Twelve hours
    #: is a working day. YBI_SESSION_HOURS to change it.
    session_hours: int = 12
    s3_bucket: str = ""
    s3_endpoint: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""

    @property
    def use_s3(self) -> bool:
        return bool(self.s3_bucket and self.s3_access_key)


settings = Settings(_env_prefix="YBI_")
try:  # DATABASE_URL is conventionally unprefixed
    import os
    if os.getenv("DATABASE_URL"):
        settings.database_url = os.environ["DATABASE_URL"]
    for k in ("S3_BUCKET", "S3_ENDPOINT", "S3_ACCESS_KEY", "S3_SECRET_KEY"):
        if os.getenv(k):
            setattr(settings, k.lower(), os.environ[k])
except Exception:
    pass
