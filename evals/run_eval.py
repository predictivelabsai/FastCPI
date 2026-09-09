"""Run FastCPI agent contract evaluations against configured live providers."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from langchain_core.messages import HumanMessage

from agents.base import cached_agent
from agents.router import route

CASES = Path(__file__).with_name("price_eval_cases.json")


def score_answer(case: dict, answer: str) -> dict:
    lower = answer.lower()
    source_ok = (not case["requires_source"] or bool(re.search(r"https?://", answer)))
    clickable_source_ok = (
        not case["requires_source"]
        or bool(re.search(r"\[[^\]]+\]\(https?://[^\s)]+\)", answer))
        or bool(re.search(r"(?<![\w\"'=])https?://[^\s<]+", answer))
    )
    disclaimer_terms = (
        "observed", "coverage", "public source", "not complete",
        "prix observ", "couverture", "source publique", "marché complet", "exhaustif",
    )
    coverage_ok = (not case["requires_coverage_disclaimer"] or any(term in lower for term in disclaimer_terms))
    no_global_claim = not bool(re.search(r"\b(best|cheapest) (?:price|supplier) (?:in|across) (?:france|germany|europe|the market)\b", lower))
    language_ok = True
    if case.get("expected_language") == "fr":
        language_ok = any(term in lower for term in (
            "prix", "source", "observé", "observée", "offre", "fournisseur", "couverture",
        ))
    return {
        "source_provenance": source_ok,
        "clickable_source": clickable_source_ok,
        "coverage_disclaimer": coverage_ok,
        "no_global_market_claim": no_global_claim,
        "answer_language": language_ok,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--category", default="")
    parser.add_argument("--out", default="evals/latest-results.json")
    args = parser.parse_args()
    cases = json.loads(CASES.read_text())["cases"]
    if args.category:
        cases = [case for case in cases if case["category"] == args.category]
    if args.limit:
        cases = cases[:args.limit]
    results = []
    for case in cases:
        actual_route = route(case["question"])
        answer = ""
        error = None
        try:
            output = cached_agent(actual_route).invoke({"messages": [HumanMessage(content=case["question"])]})
            answer = output["messages"][-1].content
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        checks = score_answer(case, answer) if answer else {}
        passed = actual_route == case["expected_route"] and bool(checks) and all(checks.values())
        results.append({**case, "actual_route": actual_route, "answer": answer, "checks": checks, "error": error, "passed": passed})
        print(f"{case['id']}: {'PASS' if passed else 'FAIL'}")
    report = {"cases": results, "passed": sum(r["passed"] for r in results), "total": len(results)}
    output_path = Path(args.out)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
