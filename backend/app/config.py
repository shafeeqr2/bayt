from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://bayt:bayt@localhost:5432/bayt"
    cors_origins: list[str] = ["http://localhost:3000"]

    # Zoning pathways phase 2: reading free text and writing the cited answer.
    # Without a key the API returns the deterministic analysis alone.
    llm_api_key: str | None = None
    # auto | anthropic | openrouter | nvidia | openai. "auto" reads the key prefix:
    # sk-ant- -> anthropic, sk-or- -> openrouter, nvapi- -> nvidia (NIM). Any
    # OpenAI-style chat endpoint works with llm_provider=openai + llm_base_url.
    llm_provider: str = "auto"
    llm_base_url: str | None = None
    # Model id in the provider's naming. Empty = the provider's default in
    # app.zoning.answer.PROVIDERS (claude-opus-5-5 on Anthropic, a Nemotron on OpenRouter).
    zoning_model: str = ""
    # Vision model for the photo labels. Empty = the provider's default in
    # app.photos.reader.DEFAULT_MODELS (a Nemotron VL on OpenRouter and NIM, Claude on Anthropic).
    photo_model: str = ""
    # Text-and-vision model that writes the house profile (facts + 4 persona pitches) for
    # "similar homes". Empty = the provider's default in app.similar.profile.DEFAULT_MODELS.
    profile_model: str = ""
    # Embedding model for the persona pitches. Empty = app.similar.embed.DEFAULT_MODELS.
    embed_model: str = ""


settings = Settings()
