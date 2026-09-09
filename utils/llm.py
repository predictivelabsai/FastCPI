from __future__ import annotations

from functools import lru_cache

from langchain_openai import ChatOpenAI

from utils.config import settings


def build_llm(model: str | None = None, temperature: float = 0.0, **kw) -> ChatOpenAI:
    s = settings()
    if s.llm_provider == "openai" and s.openai_api_key:
        return ChatOpenAI(
            model=model or s.openai_model,
            api_key=s.openai_api_key,
            temperature=temperature,
            timeout=300,
            **kw,
        )
    return ChatOpenAI(
        model=model or s.grok_model,
        api_key=s.xai_api_key,
        base_url=s.xai_base_url,
        temperature=temperature,
        timeout=300,
        **kw,
    )


def build_agent_llm(temperature: float = 0.0, **kw) -> ChatOpenAI:
    s = settings()
    model = s.xai_agent_model or s.grok_model
    return build_llm(model=model, temperature=temperature, **kw)


@lru_cache(maxsize=1)
def default_llm() -> ChatOpenAI:
    return build_llm()
