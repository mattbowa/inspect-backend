from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    anthropic_api_key: str
    redis_url: str = "redis://localhost:6379"
    database_url: str = "postgresql://seo:seo@localhost:5432/seo"

    model_config = {"env_file": ".env"}


settings = Settings()
