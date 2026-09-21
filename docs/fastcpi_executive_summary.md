# FastCPI executive summary

Status: 21 September 2026

## Product overview

- **Procurement price intelligence** — FastCPI helps procurement teams observe public supplier prices for goods and services without presenting the result as an official consumer price index.
- **Evidence-led decisions** — Every extracted price retains a clickable public source, capture time, original price and currency, comparable basis, extraction method, confidence and warnings.
- **Flexible product search** — Users can search in plain language, by CPV 2008 code and descendants, or by identifiers such as SKU, MPN and GTIN.
- **Initial European coverage** — The current service covers Germany, Denmark, Estonia, Finland, France, Lithuania, Latvia, the Netherlands, Poland and Sweden.

## Delivered pilot functionality

- **Live market discovery** — FastCPI discovers candidate supplier pages, fetches publicly accessible evidence and separates extracted observations from discovery-only results.
- **Supplier variance view** — Users select an item and country to compare the latest eligible supplier observations, with cross-EU ranges available as secondary context.
- **Streaming analyst workspace** — The three-pane chat provides full narrative analysis in the centre and concise, clickable source evidence in the right-hand pane.
- **Daily monitoring** — Each user has isolated watchlists, scheduled scans, run history, threshold events and source-linked email alerts.
- **Developer access** — Scoped and revocable API keys support REST integrations, interactive OpenAPI documentation and a read-only MCP server for compatible AI clients.
- **Account access** — Signup supports Google and verified email/password accounts, with language switching retained inside the authenticated workspace.
- **French experience** — The principal workspace, monitoring and market views are available in French, while assistant answers follow the language of each question.
- **Municipal catalogue** — The catalogue has two levels: 110 CPV-validated procurement lines across ten sectors, plus 100 concrete products sampled from ten web-price-ready lines (ten products per line). Each concrete item has an English/French name, brand/model, searchable identifier and clickable manufacturer source.
- **Controlled daily cohort** — Twenty of the 100 products (two per sampled line) form the recommended next monitoring cohort. The watches are prepopulated but intentionally paused while the configured EXA account returns HTTP 402; they can be activated together after provider billing is restored.

## Trust and operating boundaries

- **Observed sample** — Results describe the public sources successfully discovered and parsed; they do not claim complete supplier or market coverage.
- **Transparent ranking** — A versioned comparability policy is implemented locally and awaiting deployment, keeping excluded evidence visible while preventing low-confidence, mismatched or incompatible offers from influencing price statistics.
- **Commercial caveats** — Unknown VAT, delivery, supplier entity and market-delivery terms are shown explicitly rather than silently assumed.
- **Current constraints** — JavaScript-only catalogues, authenticated portals, PDFs, quote-only suppliers and many source-specific commercial terms remain only partially supported.

## Roadmap beyond the pilot

- **Comparable evidence** — Complete structured capture of pack quantity, VAT, shipping, minimum order, delivery country, service period and supplier identity, with reviewable exclusion reasons.
- **Reliable daily operations** — A standalone Coolify worker, shared Exa/page-fetch usage ledger, daily user quotas and worker-health endpoint are implemented. The remaining operational proof is seven consecutive healthy scan days, plus stalled-job alerts and dead-letter operations.
- **Broader supplier coverage** — Recurring-source reporting and maintained fixtures now cover the strongest observed starter sources. Next, add source-specific adapters only where real extraction failures justify them, then expand evidence depth across the ten-line sample.
- **Integration maturity** — Add signed webhooks, usage reporting, consistent API pagination, MCP conformance testing and standards-based OAuth discovery.
- **Procurement workflow** — Add evidence exports, saved CPV baskets, organisation teams, role controls, quote comparison and approval workflows.
- **Index methodology** — Introduce minimum sample rules, robust outlier treatment, revisions, quality tiers and confidence bands before positioning any series as a durable market index.

## Near-term success target

- **Production-ready next release** — Restore EXA access, activate the controlled 20-item cohort, run daily scans independently for seven consecutive days, and verify that every ranked offer passes documented rules while paid usage reconciles to the shared ledger.
