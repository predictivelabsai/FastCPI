# FastCPI implementation plan

## Locked product decisions

- Web-market observation and price intelligence, not an official CPI.
- Initial markets: DE, DK, EE, FI, FR, LT, LV, NL, PL and SE.
- Procurement/B2B pricing has priority.
- Users can add goods and services dynamically by text, CPV, SKU, MPN or GTIN.
- Broad CPV divisions expand through all imported descendants of CPV Version 2008.
- Exa discovers candidates; FastCPI fetches pages and applies generic or source-specific parsers.
- Discovery-only candidates remain visible beside extracted observations for comparison.
- User watchlists scan daily.
- All verified signups can create scoped API keys.
- Signup is open through Google or verified email; quotas and abuse controls are the next
  production-hardening slice.

## Delivery sequence

1. Domain tables and evidence contract.
2. CPV resolver, discovery, extraction and normalisation.
3. Read/observe API, market summaries, indices, scoped keys and watchlists.
4. FastCPI agents, three-pane evidence UX and shared streamed/static Plotly charts.
5. Daily scan execution, alert event generation and email delivery.
6. Source-frequency pilot for office paper, a unit-priced consumable and hourly IT support;
   implement parsers for the recurring supplier sites found in the ten markets.
7. Offline extraction tests, API contracts, multilingual agent evals and browser regression.
8. Google/Coolify configuration and production verification at `cpi.fastsme.com`.

## Release criteria

Each displayed observation includes source URL, original price/currency, comparable basis,
capture time and confidence/warnings. Failed extraction never becomes a price. Lowest-price claims
are scoped to observed comparable offers. Open-signup controls, OAuth validation, API scopes,
desktop/mobile behavior, health and OpenAPI documentation must pass before release.
