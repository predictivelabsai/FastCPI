# FastCPI delivery roadmap

Updated 2026-09-09. FastCPI is a source-backed web-market observation and price-intelligence
product for procurement teams. It is not an official consumer price index.

## Current implementation

- Ten EU markets, CPV Version 2008 search/descendant expansion, text/SKU/MPN/GTIN identity
  classification, Exa discovery, public-page fetching, evidence persistence and scoped API keys.
- Three pilot catalogue items and starter daily watches: A4 office paper in France, HP W2210A
  toner in Germany and hourly IT support in Estonia.
- Generic JSON-LD, microdata, Open Graph and visible hourly-rate extraction, plus one
  recurring-domain adapter. URL/redirect SSRF controls and robots policy checks are enforced.
- Source-backed observations, discovery-only candidates, daily scan events, alert email support,
  FastAPI/OpenAPI endpoints, streamed chat, Plotly charts and a fully localised French workspace.
- Open Google/email signup. Each account receives isolated watchlists and can issue revocable,
  scoped API keys.

## Known limitations

1. **Coverage is a sample.** Exa finds candidates but does not guarantee market completeness;
   only pages FastCPI can fetch and parse become observations. JavaScript-only catalogues,
   authenticated portals, PDFs and quote-only suppliers are mostly discovery-only.
2. **Parser depth is shallow.** Structured metadata works well when present, but only one
   domain-specific adapter exists. Supplier address/entity, pack size, MOQ, delivery zone,
   contract duration and price-break extraction are incomplete.
3. **Comparability needs stronger gates.** Currency conversion exists, but VAT, shipping,
   quantity, service scope, product variant and effective-date differences can still prevent
   defensible ranking. Product equivalence is not yet a canonical graph.
4. **Geographic confidence is limited.** Market selection and source locality need supplier
   address, delivery-country and domain evidence rather than query intent or ccTLD alone.
5. **Indices are pilot-grade.** Current base-100 series have sparse samples and no published
   revision policy, outlier model, seasonal treatment, confidence intervals or quality tier.
6. **Scheduling is process-local.** A daemon thread polls due watches without leases, durable
   jobs, per-domain throttles, retry state, cost budgets or horizontal-worker coordination.
7. **Watchlist UI is create/read only.** The API supports update/delete, but the workspace still
   needs edit, pause, delete, run-now, scan history and per-watch evidence drill-down.
8. **API hardening is incomplete.** Cursor pagination, idempotency, async observation jobs,
   rate limits/quotas, usage metering, webhook delivery and a formal version/deprecation policy
   are still required before broad third-party use.
9. **Open-signup abuse controls are not complete.** Email signup verifies ownership, but API
   signup parity, bot protection and scan quotas must be added before paid live discovery is
   enabled for every account.
10. **Operational evidence needs maturation.** Extraction fixtures cover core formats, but
    parser drift alerts, source compliance records, end-to-end scan tracing, retention controls
    and historical artifact reconstruction are limited.

## Next slice — dependable monitoring foundation

Target: the three pilot watches run daily, visibly and repeatably without depending on a web
process staying alive.

- Add `scan_runs` and `scan_run_items` with queued/running/succeeded/partial/failed states,
  attempt count, timings, Exa/fetch usage, error class and observation IDs.
- Move execution to a durable worker with PostgreSQL leases, idempotent job keys, exponential
  retry, per-domain concurrency limits and per-user daily discovery quotas.
- Add watchlist edit/pause/delete/run-now controls, last/next-run state and a detail page linking
  every observation to its public source.
- Implement and fixture the recurring supplier domains found in the France paper, Germany toner
  and Estonia IT-service scans; add pack/VAT/shipping/MOQ confidence fields.
- Add comparable-offer eligibility rules. The ranking excludes unresolved unit, VAT, product
  identity or service-scope mismatches and explains every exclusion.
- Add API cursor pagination, `POST /observation-jobs`, `GET /observation-jobs/{id}`, idempotency
  keys, rate-limit headers and user/source cost metrics.
- Expand evals: French question/French answer, English question in French UI/English answer,
  clickable provenance, observed-vs-discovery labels, CPV descendants and no global-best claim.

Acceptance criteria:

- All three starter scans complete on schedule for seven consecutive days; retries never create
  duplicate observations and a worker restart loses no job.
- Every displayed price has a clickable HTTP(S) source, capture time, original price/currency,
  comparable basis, extraction method, confidence and warnings.
- A user can create, edit, pause, run and delete a watch from desktop and mobile; another user
  cannot access it through either browser routes or API.
- No result is called the cheapest/best in a market unless the copy says “lowest observed
  comparable price” and states sample coverage.

## MCP server plan

The first MCP release is read-only and reuses the FastCPI service/repository layer and Pydantic
schemas; it must not call the public HTTP API from inside the same process. Use the current
stateless Streamable HTTP transport at `POST /mcp`. The 2026-07-28 protocol uses a self-describing
request model and `server/discover`; every request carries protocol/client metadata and required
method/name headers. Maintain compatibility with 2025-era clients through the official Python
SDK rather than a hand-written compatibility layer.

References: [current Streamable HTTP specification](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2026-07-28/basic/transports/streamable-http.mdx),
[current authorization specification](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2026-07-28/basic/authorization/index.mdx),
[official Python SDK compatibility notes](https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/whats-new.md).

### MCP alpha surface

- Tools: `search_price_observations`, `get_price_observation`, `search_cpv`,
  `get_cpv_overview`, `get_market_overview`, `list_price_indices`, `list_catalog_items`.
- Resources: `fastcpi://methodology`, `fastcpi://markets`, `fastcpi://catalog`,
  `fastcpi://cpv/{code}` and `fastcpi://observations/{id}`.
- Prompts: `benchmark_requirement` and `compare_supplier_quotes`, both explicitly preserving
  user-language and evidence requirements.
- Every tool result returns structured content plus source URL, capture time, extraction method,
  evidence class, comparable basis, confidence/warnings and coverage statement.

### MCP access and discovery

- Publish the endpoint and examples in `/developers`, OpenAPI vendor metadata and `llms.txt`;
  register the server in the official MCP Registry once the alpha is stable.
- Return `401` plus protected-resource metadata for unauthenticated clients. Exchange existing
  user identity for OAuth access tokens with audience binding and scopes such as `prices:read`,
  `cpv:read` and `indices:read`; retain API-key auth only as a documented transitional option.
- Validate `Origin`, protocol-version and method/name headers at the edge. Apply the same tenant
  isolation, quotas and audit trail as the REST API.

### MCP later phases

1. Add the read-only endpoint, SDK conformance tests and MCP Inspector smoke tests.
2. Add OAuth protected-resource metadata, consent, scoped authorization and registry metadata.
3. Add asynchronous `observe_prices` only after job quotas/idempotency exist.
4. Add watchlist writes only with explicit confirmation, clear side-effect annotations and
   per-call audit records. Never expose admin, invitation, account deletion or raw SQL tools.

## Following slices

1. **Source expansion:** top recurring adapters in all ten markets, PDF/table extraction,
   supplier/entity resolution and browser-based extraction only where terms permit.
2. **Price model:** canonical items/variants, units and service scopes; VAT/shipping/MOQ and
   contract normalisation; quality tiers and manual evidence review.
3. **Index methodology:** minimum samples, robust outliers, weights, backfill/revisions,
   confidence bands and downloadable methodology/version history.
4. **Procurement workflow:** saved CPV baskets, quote upload/comparison, evidence exports,
   organisation teams/RBAC, approval flows and webhooks.
5. **Platform maturity:** billing/quotas, SLOs, tracing, audit/retention controls, source-policy
   registry, disaster recovery and staged API/MCP version lifecycle.
