"""All settings come from the environment (or a .env file); every limit has a safe default."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="WEBDATA_", extra="ignore")

    env: str = "development"
    database_url: str = "postgresql+psycopg://webdata:webdata@localhost:5432/webdata"
    redis_url: str = "redis://localhost:6379/0"
    secret_key: str = "change-me-in-.env"  # noqa: S105 - signs export links; must be overridden outside dev
    cookie_secure: bool = False  # True when served over HTTPS
    cors_origins: list[str] = ["http://localhost:5173"]
    data_dir: str = "./var"  # exports and optional page bodies live here
    celery_eager: bool = False  # run tasks inline (tests, single-process demo)

    # Crawler identity and politeness
    user_agent: str = "WebDataAI/0.1 (+http://localhost/crawler-info; contact: admin@example.invalid)"
    respect_robots: bool = True
    per_domain_concurrency: int = 2
    per_domain_delay_seconds: float = 1.0
    global_concurrency: int = 8
    connect_timeout: float = 10.0
    read_timeout: float = 20.0
    max_page_bytes: int = 3_000_000
    max_redirects: int = 5
    url_retry_limit: int = 3
    allowed_ports: list[int] = [80, 443]
    # Narrow admin exception to SSRF rules, e.g. ["127.0.0.1:8765"] for the local test sites.
    allow_private_targets: list[str] = Field(default_factory=list)
    # Optional outbound proxy for sandboxes that only allow egress through a proxy. DNS is still
    # validated locally, but the proxy makes the final connection, so prefer direct egress.
    crawl_proxy: str | None = None
    # Self-hosted SearXNG for website discovery, e.g. http://searxng:8080 (empty = not available).
    searxng_url: str = ""

    # Job limits (org overrides can only lower these)
    max_pages_per_job: int = 2000
    max_depth: int = 3
    max_job_seconds: int = 3600
    max_active_jobs_per_org: int = 3
    max_pages_per_org_month: int = 50_000
    max_records_per_job: int = 10_000
    max_export_rows: int = 100_000
    export_ttl_hours: int = 24
    retention_days: int = 90

    # Auth
    session_ttl_hours: int = 24 * 7
    login_attempts_per_15min: int = 10


@lru_cache
def get_settings() -> Settings:
    return Settings()
