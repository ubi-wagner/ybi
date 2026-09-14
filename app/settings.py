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
    #: The organisation's shared first-login password, for a round where a
    #: set of accounts is opened at once and each person claims their own.
    #: YBI_INITIAL_PASSWORD.
    #:
    #: It is a **setting and never anybody's stored hash.** An account opened
    #: against it is given an unusable random hash, and login accepts this
    #: value in addition, for accounts that have not yet set their own. Three
    #: things follow, and they are the reason for the indirection:
    #:
    #: - clearing the variable closes the door immediately, for everybody
    #:   still on it. A shared password written into forty rows would need
    #:   forty resets to withdraw.
    #: - rotating it is one change rather than forty.
    #: - the shared secret is never at rest in the database, so a copy of the
    #:   record is not a copy of the credential.
    #:
    #: An account that has set its own password stops accepting it, so the
    #: door closes person by person as the round completes. Anything shorter
    #: than twelve characters is ignored outright rather than honoured — a
    #: short organisational default is worse than none, because it reads as
    #: a control while being none.
    initial_password: str = ""
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
