"""LangChain CPV Version 2008 tools."""

from __future__ import annotations

import json

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field


class CPVArgs(BaseModel):
    query: str = Field(description="Eight-digit CPV code or plain-language CPV label")
    language: str = Field(default="en", description="Two-letter label language")


def _cpv_lookup(**kwargs) -> str:
    from db import SessionLocal
    from pricing.cpv import import_official_tree, search_cpv
    args = CPVArgs(**kwargs)
    db = SessionLocal()
    try:
        results = search_cpv(db, args.query, lang=args.language, limit=50)
        if not results and args.query.replace("-", "").isdigit():
            results = import_official_tree(db, args.query, max_nodes=100)
    finally:
        db.close()
    return json.dumps({"version": "2008", "query": args.query, "concepts": results}, default=str)


cpv_lookup = StructuredTool.from_function(
    func=_cpv_lookup, name="cpv_lookup",
    description="Resolve CPV Version 2008 codes and include imported descendants for broad categories.",
    args_schema=CPVArgs,
)
