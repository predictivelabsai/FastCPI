# FastCPI delivery roadmap

Updated 2026-09-21. FastCPI is a source-backed web-market observation and price-intelligence
product for procurement teams. It is not an official consumer price index.

## Current implementation

- Ten EU markets, CPV Version 2008 search/descendant expansion, text/SKU/MPN/GTIN identity
  classification, Exa discovery, public-page fetching, evidence persistence and scoped API keys.
- Three starter daily watches remain: A4 office paper in France, HP W2210A toner in Germany and
  hourly IT support in Estonia.
- The catalogue now has 110 researched local-government procurement lines across ten sectors and
  100 concrete products beneath ten web-price-ready lines. The concrete layer has ten products per
  line, searchable manufacturer identifiers, English/French names and official identity sources.
  A controlled 20-item cohort (two per sampled line) is prepopulated but paused until EXA access is
  restored.
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
- A versioned comparable-offer policy is implemented locally and awaiting deployment. It exposes
  ranking eligibility, machine-readable exclusion reasons and commercial-term caveats through the
  market dashboard, REST API and MCP output; excluded evidence remains visible but cannot influence
  supplier statistics.
- A shared paid-usage ledger now meters Exa searches and page fetches across chat, manual watches,
  synchronous observation and asynchronous jobs. The standalone worker topology exposes a
  readiness/queue-health endpoint; deployment as a separate Coolify process remains outstanding.

## Known limitations

1. **Coverage is a sample.** Exa finds candidates but does not guarantee market completeness;
   only pages FastCPI can fetch and parse become observations. JavaScript-only catalogues,
   authenticated portals, PDFs and quote-only suppliers are mostly discovery-only.
2. **Parser depth is shallow.** Structured metadata works well when present, but only one
   domain-specific adapter exists. Supplier address/entity, pack size, MOQ, delivery zone,
   contract duration and price-break extraction are incomplete.
3. **Comparability evidence remains incomplete.** The first versioned ranking gate now covers
   confidence, normalised units, known identifier conflicts and market conflicts, while retaining
   VAT, delivery, identity and supplier caveats. Pack quantity, MOQ, service scope, product variant,
   effective dates and a canonical product-equivalence graph still need structured evidence.
4. **Geographic confidence is limited.** Market selection and source locality need supplier
   address, delivery-country and domain evidence rather than query intent or ccTLD alone.
5. **Indices are pilot-grade.** Current base-100 series have sparse samples and no published
   revision policy, outlier model, seasonal treatment, confidence intervals or quality tier.
6. **Worker separation is not deployed.** The repository has distinct web/worker services, disables
   scan execution in the web container and records worker heartbeats, queue depth and failures. A
   dedicated Coolify worker, stalled-lease alerts, per-domain throttling and queue SLOs still need
   production configuration and a seven-day soak.
7. **Quotas need production reconciliation.** The shared ledger and per-user daily Exa/fetch limits
   cover all paid discovery paths. Domain/minute budgets, an operator usage view and reconciliation
   against provider invoices/logs remain.
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

## Delivery plan beyond the pilot

The previous next slice combined data quality, infrastructure, metering, integrations and source
coverage. It is now split into independently testable releases.

### Release A — comparable-offer contract

Status: first increment implemented locally; production deployment and evidence-field expansion remain.

- Apply `offer-comparability-v1` to country and EU statistics, with excluded observations visible
  below the ranking and machine-readable reasons in REST and MCP results.
- Extend the evidence model with normalized pack quantity, VAT, shipping, MOQ, delivery country,
  service period and supplier entity. Preserve raw evidence alongside every normalized field.
- Add analyst CSV/XLSX evidence export after the required format is confirmed.

Acceptance criteria:

- Every ranked offer passes documented identity, unit, confidence and geographic checks.
- Every excluded offer remains source-linked and has a machine-readable reason visible in API and UI.
- Commercial caveats are explicit and never silently converted into known terms.

### Release B — independently operable monitoring

Status: repository implementation complete for split web/worker services, worker heartbeats and
shared paid-usage quotas; Coolify worker deployment, alerts and soak verification remain.

- Deploy `python -m scripts.watchlist_worker` as a separate Coolify process and turn off the web
  worker there; add readiness/queue-depth metrics, stalled-lease alerts and a dead-letter view.
- Reconcile the implemented shared Exa/page-fetch ledger and per-user daily limits in production,
  then add domain/minute budgets for watch scans, sync observation and async jobs.

Acceptance criteria:

- All three starter scans complete in the dedicated worker on schedule for seven consecutive days.
- Retries never create duplicate runs or observations and a worker restart loses no job.
- Quotas cover every paid discovery path and totals reconcile to Exa and fetch execution logs.

### Release C — evidence-driven source coverage

Status: 100 concrete samples, the paused 20-item cohort, recurring-domain report and maintained
starter-source fixtures are implemented locally. Live cohort activation is blocked by EXA HTTP 402.

- Continue ranking recurring domains from live usage and add adapters when fixtures reveal a real
  gap; generic JSON-LD/microdata already parses the strongest observed starter sources.
- Activate and measure the selected 20-item cohort after EXA billing is restored; do not enqueue all
  100 products or all 110 procurement lines by default.

Acceptance criteria:

- Each starter category has maintained extraction fixtures for its strongest recurring sources.
- Parser drift produces an operational alert before silently degrading market coverage.

### Release D — third-party delivery and LLM discovery

- Add signed webhook subscriptions for job/scan completion and threshold events, with an outbox,
  retries, replay protection and delivery history.
- Publish an MCP client example and `llms.txt`, run MCP Inspector/conformance in CI, and implement
  OAuth protected-resource/authorization metadata before registry submission.

Acceptance criteria:

- Webhook retries are idempotent, signed and inspectable by the owning tenant.
- MCP clients can discover authentication metadata, run conformance tests and reproduce a documented
  catalogue-to-price-variance workflow.

### Cross-release quality work

- Expand evals with parser fixtures, tenant-crossing attempts, queue restart recovery, quota
  exhaustion, French/English question-language behavior and clickable provenance.
- Require every displayed price to include a clickable HTTP(S) source, capture time, original
  price/currency, comparable basis, extraction method, confidence and warnings.
- Never call a result cheapest or best in a market unless the copy says “lowest observed comparable
  price” and states sample coverage.

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
