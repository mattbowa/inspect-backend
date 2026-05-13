from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    anthropic_api_key: str
    redis_url: str = "redis://localhost:6379"
    database_url: str = "postgresql://seo:seo@localhost:5432/seo"
    free_page_limit: int = 1
    stripe_secret_key: str
    stripe_webhook_secret: str
    stripe_price_business: str
    stripe_price_enterprise: str
    frontend_url: str = "http://localhost:3000"
    resend_api_key: str = ""
    email_from: str = "reports@inspectflux.com"
    claude_model: str = "claude-haiku-4-5"

    model_config = {"env_file": ".env"}


settings = Settings()
