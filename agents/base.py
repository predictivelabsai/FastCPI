"""Shared helpers for building LangGraph ReAct agents."""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

from langchain_core.tools import BaseTool
from langgraph.prebuilt import create_react_agent

from agents.registry import AgentSpec
from utils.llm import build_agent_llm

log = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts" / "system"
SHARED_PROMPT_FILE = Path(__file__).resolve().parent.parent / "prompts" / "shared" / "car_context.md"


def _load_system_prompt(slug: str) -> str:
    shared = SHARED_PROMPT_FILE.read_text() if SHARED_PROMPT_FILE.exists() else ""
    specific_file = PROMPTS_DIR / f"{slug}.md"
    specific = specific_file.read_text() if specific_file.exists() else ""
    if not specific:
        log.warning("no system prompt for %s -- using shared context only", slug)
    voice_file = PROMPTS_DIR / "voice.md"
    voice = voice_file.read_text() if slug == "kenri" and voice_file.exists() else ""
    parts = [shared, specific, voice]
    return "\n\n".join(p for p in parts if p).strip()


def build_agent(spec: AgentSpec, tools: list[BaseTool]):
    system = _load_system_prompt(spec.slug)
    llm = build_agent_llm()
    return create_react_agent(llm, tools, prompt=system or None)


@lru_cache(maxsize=64)
def cached_agent(slug: str):
    from agents import registry
    spec = registry.by_slug(slug)
    if spec is None:
        raise ValueError(f"unknown agent slug: {slug}")

    import importlib
    module = importlib.import_module(f"agents.{spec.category}.{spec.slug}")
    return module.build()
