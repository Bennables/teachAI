from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    vlm_provider: str = "openai"
    openai_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    selenium_headless: bool = False
    selenium_timeout: int = 15


settings = Settings()
