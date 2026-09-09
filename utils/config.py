from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    db_url: str = Field(default="", alias="DB_URL")
    app_secret: str = Field(default="carhero-app-2026", alias="APP_SECRET")
    port: int = Field(default=5010, alias="PORT")

    xai_api_key: str = Field(default="", alias="XAI_API_KEY")
    xai_base_url: str = Field(default="https://api.x.ai/v1", alias="XAI_BASE_URL")
    grok_model: str = Field(default="grok-4-1-fast-reasoning", alias="GROK_MODEL")
    xai_agent_model: str = Field(default="", alias="XAI_AGENT_MODEL")

    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o", alias="OPENAI_MODEL")

    llm_provider: str = Field(default="xai", alias="LLM_PROVIDER")

    exa_api_key: str = Field(default="", alias="EXA_API_KEY")

    login_enabled: bool = Field(default=False, alias="LOGIN")


@lru_cache(maxsize=1)
def settings() -> Settings:
    return Settings()


_BRANDS_PATH = Path(__file__).resolve().parent.parent / "config" / "brands.yaml"


@lru_cache(maxsize=1)
def _load_brands() -> list[dict]:
    with open(_BRANDS_PATH) as f:
        return yaml.safe_load(f)["brands"]


def get_all_brands() -> list[str]:
    return [b["name"] for b in _load_brands()]


def get_featured_brands() -> list[str]:
    return [b["name"] for b in _load_brands() if b.get("featured")]


def get_brand_slugs(provider: str) -> dict[str, str]:
    return {b["name"]: b["slugs"][provider] for b in _load_brands() if provider in b.get("slugs", {})}
