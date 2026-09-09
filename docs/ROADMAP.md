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
- Item-first supplier variance dashboards use the latest observation per public offer, compare
  suppliers within one selected country by default and expose EU country ranges as a secondary view.
- Open Google/email signup. Each account receives isolated watchlists and can issue revocable,
  scoped API keys.
- Durable PostgreSQL scan and observation-job queues now use idempotency keys, atomic claims,
  leases, bounded retries and per-market outcomes. Watchlists support create, edit, pause/resume,
  delete, run-now, source evidence and run history in English and French.
- The third-party surface includes cursor-paged, quota-controlled asynchronous observation jobs
  and an authenticated read-only MCP Streamable HTTP alpha at `/mcp/` with six tools and a
  methodology resource.

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
6. **Worker separation is not deployed.** Jobs are durable and lease-safe, and a standalone
   worker entry point exists, but the current deployment also runs a worker thread in the web
   process. A dedicated Coolify worker, per-domain concurrency/throttling and queue SLOs remain.
7. **Quota coverage is partial.** Async observation jobs have per-user daily quotas and rate-limit
   headers. Manual watch scans, the legacy synchronous observe route and source-level Exa/fetch
   budgets still need one shared usage ledger.
8. **API lifecycle is incomplete.** Observation-job cursor pagination is implemented, but all
   list resources need consistent cursors, webhook delivery, usage reporting and a formal
   version/deprecation policy before broad third-party use.
9. **Open-signup abuse controls are not complete.** Email signup verifies ownership and Google
   tokens validate audience, but bot protection, anomaly controls and plan-level scan quotas are
   still needed before paid live discovery is enabled for every account.
10. **Operational evidence needs maturation.** Extraction fixtures cover core formats, but
    parser drift alerts, source compliance records, end-to-end scan tracing, retention controls
    and historical artifact reconstruction are limited.
11. **MCP authentication is transitional.** The alpha supports current and 2025-era clients via
    the official SDK and requires a scoped FastCPI API key as a bearer token. OAuth authorization,
    consent, dynamic client registration and registry publication are not yet implemented.

## Next slice — defensible comparable offers and production workers

Target: make daily monitoring independently operable and make supplier ranking defensible enough
for a procurement analyst to export and review.

- Deploy `python -m scripts.watchlist_worker` as a separate Coolify process and turn off the web
  worker there; add readiness/queue-depth metrics, stalled-lease alerts and a dead-letter view.
- Add one shared usage ledger for Exa searches and fetched pages, then enforce user/day and
  domain/minute budgets for watch scans, sync observation and async jobs.
- Run the three starter scans against current public sources, rank recurring domains and build
  fixtures/adapters for the strongest France-paper, Germany-toner and Estonia-IT sources.
- Extend the evidence model with normalized pack quantity, VAT, shipping, MOQ, delivery country,
  service period and supplier entity. Preserve raw evidence alongside every normalized field.
- Introduce comparable-offer eligibility and explicit exclusion reasons. Default variance charts
  use eligible offers; incompatible offers remain visible below the ranking.
- Add signed webhook subscriptions for job/scan completion and threshold events, with an outbox,
  retries, replay protection and delivery history.
- Publish an MCP client example and `llms.txt`, run MCP Inspector/conformance in CI, and implement
  OAuth protected-resource/authorization metadata before registry submission.
- Expand evals with parser fixtures, tenant-crossing attempts, queue restart recovery, quota
  exhaustion, French/English question-language behavior and clickable provenance.

Acceptance criteria:

- All three starter scans complete in the dedicated worker on schedule for seven consecutive
  days; retries never create duplicate runs/observations and a worker restart loses no job.
- Every displayed price has a clickable HTTP(S) source, capture time, original price/currency,
  comparable basis, extraction method, confidence and warnings.
- Every ranked offer passes documented identity/unit/commercial-term gates; every exclusion has
  a machine-readable reason visible in the API and UI.
- Quotas cover every paid discovery path and usage totals reconcile to Exa/fetch execution logs.
- No result is called the cheapest/best in a market unless the copy says “lowest observed
  comparable price” and states sample coverage.

## MCP server status and plan

The read-only alpha is implemented with the official Python SDK and reuses the FastCPI
repository layer without calling the public HTTP API from inside the process. It is served over
stateless Streamable HTTP at `/mcp/`, validates host/origin, publishes protected-resource
metadata and maintains compatibility with 2025-era clients.

References: [current Streamable HTTP specification](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2026-07-28/basic/transports/streamable-http.mdx),
[current authorization specification](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2026-07-28/basic/authorization/index.mdx),
[official Python SDK compatibility notes](https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/whats-new.md).

### Implemented MCP alpha surface

- Tools: `search_catalog`, `search_cpv`, `price_variance`, `market_overview`,
  `list_watchlists` and `scan_run_status`.
- Resource: `fastcpi://methodology`.
- Every price-variance offer returns its public source URL and evidence metadata. Tools are marked
  read-only, non-destructive and idempotent for client discovery.

### MCP access and discovery

- The endpoint and bearer-key example are published in `/developers`. Next publish OpenAPI vendor
  metadata and `llms.txt`, then
  register the server in the official MCP Registry once the alpha is stable.
- The alpha returns `401` plus protected-resource metadata for unauthenticated clients and accepts
  revocable `prices:read` API keys in `Authorization: Bearer`. Next exchange user identity for
  OAuth access tokens with audience binding and granular scopes such as `prices:read`, `cpv:read`
  and `indices:read`.
- Validate `Origin`, protocol-version and method/name headers at the edge. Apply the same tenant
  isolation, quotas and audit trail as the REST API.

### MCP later phases

1. Add MCP Inspector/conformance CI, client examples and remaining observation/index resources.
2. Add OAuth authorization endpoints, consent, granular scopes and registry metadata.
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
