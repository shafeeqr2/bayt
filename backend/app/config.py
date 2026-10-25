from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://bayt:bayt@localhost:5432/bayt"
    cors_origins: list[str] = ["http://localhost:3000"]

    # Zoning pathways phase 2: reading free text and writing the cited answer.
    # Named LLM_API_KEY, not after a vendor, so the provider can change later.
    # Today it is an Anthropic key. Without one the API returns the
    # deterministic analysis alone.
    llm_api_key: str | None = None
    zoning_model: str = "claude-opus-5-5"


settings = Settings()
