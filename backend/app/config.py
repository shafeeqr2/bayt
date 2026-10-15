from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://bayt:bayt@localhost:5432/bayt"
    cors_origins: list[str] = ["http://localhost:3000"]


settings = Settings()
