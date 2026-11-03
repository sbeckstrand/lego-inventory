from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration, populated from environment variables.

    In local dev these come from docker-compose; in k8s they come from a
    ConfigMap/Secret. Nothing here is specific to the dev setup.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # SQLAlchemy URL. Default points at the compose `db` service; override with
    # your real Postgres server in prod.
    database_url: str = "postgresql+psycopg://lego:lego@db:5432/lego"

    # Rebrickable API — https://rebrickable.com/api/
    rebrickable_api_key: str = ""
    rebrickable_base_url: str = "https://rebrickable.com/api/v3/lego"

    # Where set images/assets are written. Bind-mounted locally in dev; an
    # NFS-backed volume in k8s. Same path either way.
    assets_dir: str = "/data/assets"


@lru_cache
def get_settings() -> Settings:
    return Settings()
