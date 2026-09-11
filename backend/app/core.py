from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "sqlite:///./reposage.db"
    redis_url: str = "redis://redis:6379/0"
    qdrant_url: str = "http://qdrant:6333"
    jwt_secret: str = "development-only-change-me"
    cors_origins: str = "http://localhost:3000"
    embedding_model: str = "text-embedding-3-large"

    # Multi-provider LLM Configuration
    # Supported providers: "auto", "openai", "gemini", "groq", "ollama", "openrouter", "deepseek", "custom"
    llm_provider: str = "auto"
    llm_api_key: str | None = None
    llm_model: str | None = None
    llm_base_url: str | None = None

    # Dedicated Provider Keys & Models
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"

    gemini_api_key: str | None = None
    gemini_model: str = "gemini-flash-latest"

    groq_api_key: str | None = None
    groq_model: str = "llama-3.3-70b-versatile"

    openrouter_api_key: str | None = None
    openrouter_model: str = "nex-agi/nex-n2.5-mini:free"

    deepseek_api_key: str | None = None
    deepseek_model: str = "deepseek-chat"

    ollama_base_url: str = "http://host.docker.internal:11434/v1"
    ollama_model: str = "llama3"

@lru_cache
def settings() -> Settings:
    return Settings()
