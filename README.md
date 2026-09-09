# FastCPI

FastCPI is a B2B web-market observation and price-intelligence service. It discovers public
supplier pages with Exa, fetches and parses attributable price evidence, normalises commercial
terms, and tracks observed asking-price movements. It is not an official consumer price index.

## Product surfaces

- `/` — public FastSME-style landing page
- `/app` — three-pane streaming price-intelligence chat
- `/app/market-overview` — item-first Plotly supplier-variance dashboard, country view by default
- `/app/watchlists` — user-specific daily price monitors
- `/app/daily-scan` — latest watchlist movements
- `/developers` — API guide with Swagger, ReDoc and versioned OpenAPI links
- `/api/docs` and `/api/redoc` — interactive API documentation
- `/api/openapi/v1.json` — versioned OpenAPI schema
- `/api/v1/items/{item_id}/price-variance` — latest-offer country benchmark with EU context

Initial markets are Germany, Denmark, Estonia, Finland, France, Lithuania, Latvia, the
Netherlands, Poland and Sweden. Queries may use plain language, CPV Version 2008 codes, SKUs,
MPNs or GTINs.

Signup is open through Google or verified email. The language selector remains available in the
authenticated workspace. The French workspace is fully localised; agent answers follow the
language of each latest question without translating or rewriting it for search.

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp env.sample .env
python main.py
```

PostgreSQL is required. The application creates the configured `DB_SCHEMA` and tables at startup.
Use strong `APP_SECRET` and `JWT_SECRET` values outside local development.

## Tests and evals

```bash
pytest -q tests/test_pricing.py tests/test_fastcpi_router.py
python -m evals.run_eval --limit 3
```

Unit tests are deterministic and network-free. Agent evals require the configured LLM and Exa
credentials and verify routing, source provenance, coverage language and global-market-claim
guardrails.

Watchlist scans run daily in production. Threshold events include the best observed source URL;
when email is enabled, one Postmark alert is sent for that scan and the event is marked notified.

## Evidence contract

API and UI results distinguish fetched **observations** from **discovery-only** candidates. Every
observation retains its URL, extraction method, capture timestamp, evidence excerpt and content
hash. Conflicting country-code domains are excluded from in-market rankings, while generic domains
are labelled geographically unverified. “Lowest” means lowest observed comparable price in the
current sample—not the entire market.

See [docs/ROADMAP.md](docs/ROADMAP.md) for current limitations, the dependable-monitoring next
slice and the read-only MCP server plan.

The screenshot-led [user guide](docs/fastcpi_user_guide.md) can be regenerated as dated PDF and
PowerPoint files with `scripts/build_user_guide.sh`. `scripts/build_demo_gif.sh` rebuilds the
landing-page walkthrough at `static/product-demo.gif` from the reviewed `screenshots/` set.
