from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://insight:insight@localhost:5432/insight"
    api_key: str = "change-me"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    clustering_hour: int = 3
    digest_hour: int = 7

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
