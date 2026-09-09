"""Text-to-SQL tool for agents -- queries carhero schema via sql/schema.json."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import pandas as pd
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

_SCHEMA_JSON = Path(__file__).resolve().parents[1] / "sql" / "schema.json"


def _load_schema_snippet() -> str:
    if not _SCHEMA_JSON.exists():
        return "(schema.json not found)"
    data = json.loads(_SCHEMA_JSON.read_text())
    lines = []
    for table_name, info in data.get("tables", {}).items():
        cols = info.get("columns", [])
        desc = info.get("description", "")
        lines.append(f"carhero.{table_name} -- {desc}")
        lines.append(f"  columns: {', '.join(cols)}")
        for k in ["sample_makes", "providers", "countries", "fuel_types",
                   "transmissions", "body_types", "conditions", "steering_sides", "seller_types"]:
            if k in info:
                lines.append(f"  {k}: {info[k]}")
        lines.append("")
    notes = data.get("notes", "")
    if notes:
        lines.append(f"Notes: {notes}")
    return "\n".join(lines)


class SQLQueryArgs(BaseModel):
    question: str = Field(
        description="Natural-language question about car market data, e.g. "
                    "'Average BMW X5 price by country' or 'Top 10 cheapest Porsche 911s'"
    )


def _draft_sql(question: str) -> str:
    from utils.llm import build_llm

    schema = _load_schema_snippet()
    system = f"""You translate plain-English questions into a single PostgreSQL SELECT query.

Rules:
- Return ONLY the raw SQL, nothing else. No markdown, no explanation.
- SELECT only. Never modify data.
- Use schema-qualified names (carhero.car_listings, carhero.price_history, etc.).
- LIMIT to 50 rows max unless aggregating.
- For time series, ORDER BY the time column.
- Use ILIKE for name matching.
- Prices are in EUR. Mileage is in km.
- Available makes: BMW, Mercedes-Benz, Audi, Porsche, Jaguar, Land Rover, Volvo, Tesla, Lexus.
- Providers: autotrader, mobile_de, autoscout24, autohero.
- Countries: GB, DE, EU.

Schema:
{schema}"""

    llm = build_llm()
    resp = llm.invoke(f"{system}\n\nQuestion: {question}\n\nSQL:").content
    sql = resp.strip().strip("`").strip()
    if sql.lower().startswith("sql"):
        sql = sql[3:].strip()
    sql = sql.rstrip(";")
    return sql


def _guard_sql(sql: str) -> None:
    lowered = sql.lower().strip()
    if not lowered.startswith("select") and not lowered.startswith("with"):
        raise ValueError("Only SELECT / WITH queries are allowed.")
    for kw in ["insert ", "update ", "delete ", "drop ", "truncate ", "alter ", "create "]:
        if kw in lowered:
            raise ValueError(f"Disallowed keyword: {kw.strip()}")


def _run_query(question: str) -> str:
    sql = _draft_sql(question)
    _guard_sql(sql)

    from db import SessionLocal
    from sqlalchemy import text

    db = SessionLocal()
    try:
        result = db.execute(text(sql))
        rows = [dict(r._mapping) for r in result]
    finally:
        db.close()

    if not rows:
        return "No results found for this query."

    df = pd.DataFrame(rows)

    for col in df.select_dtypes(include=["float", "int"]).columns:
        if df[col].abs().max() > 1000:
            df[col] = df[col].apply(lambda x: f"{x:,.0f}" if pd.notna(x) else "")

    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].astype(str).str[:60]

    preview = df.head(20)
    headers = " | ".join(str(c) for c in preview.columns)
    separator = " | ".join("---" for _ in preview.columns)
    body_rows = []
    for _, row in preview.iterrows():
        body_rows.append(" | ".join(str(v) for v in row.values))

    lines = [f"Query results ({len(df)} rows):\n"]
    lines.append(headers)
    lines.append(separator)
    lines.extend(body_rows)

    if len(df) > 20:
        lines.append(f"\n*Showing first 20 of {len(df)} rows.*")

    return "\n".join(lines)


def _safe_query(**kw) -> str:
    args = SQLQueryArgs(**kw)
    try:
        return _run_query(args.question)
    except Exception as e:
        log.warning("SQL query failed: %s", e)
        return f"Query failed: {e}"


car_market_query = StructuredTool.from_function(
    func=_safe_query,
    name="car_market_query",
    description=(
        "Query the CarHero car market database using natural language. "
        "Contains listings from 4 European marketplaces (AutoTrader UK, mobile.de, AutoScout24, Autohero) "
        "for 9 premium brands. Use for: price analysis, market statistics, depreciation trends, "
        "geographic price comparisons, model comparisons, fuel type analysis."
    ),
    args_schema=SQLQueryArgs,
)
