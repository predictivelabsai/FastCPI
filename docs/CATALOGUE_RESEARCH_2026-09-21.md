# Local-government catalogue research

Date: 21 September 2026

## Research basis

FastCPI used official EU procurement sources to select the first broad municipal catalogue:

- [TED CPV 2008 vocabulary](https://ted.europa.eu/en/simap/cpv) — authoritative codes and English/French labels; CPV is the mandatory EU notice classification and uses a hierarchical division-to-category structure.
- [TED Search API](https://docs.ted.europa.eu/api/latest/search.html) — unauthenticated official notice search used for the frequency sample.
- [EU buyer legal type codelist](https://docs.ted.europa.eu/eforms/latest/reference/code-lists/buyer-legal-type.html) — local authority and local-authority-controlled buyer definitions.
- [Public Procurement Data Space](https://single-market-economy.ec.europa.eu/single-market/public-procurement/digital-procurement/public-procurement-data-space-ppds_en) — confirms that EU public buyers purchase services, works and supplies and explains the coverage boundary between TED and below-threshold national data.
- [Circular procurement in cities](https://circular-cities-and-regions.ec.europa.eu/support-materials/ccri-documents/circular-public-procurement-cities) — identifies schools, street lighting, waste, construction materials, refurbished IT and mobility as recurring city responsibilities.
- [European Commission green procurement priorities](https://commission.europa.eu/document/download/24c26f7d-2c51-4f69-8b06-2d5be859c7fc_en) — identifies ICT, infrastructure, logistics, furniture, office supplies, catering, cleaning and gardening as priority public-purchase groups.

## TED frequency sample

The query selected the latest version of notices published from 1 September 2025 using buyer legal types `la`, `body-pl-la`, `pub-undert-la` and `org-sub-la`. The analysis used the first 2,500 returned notices and counted each distinct CPV code once per notice to reduce repeated multi-lot classifications.

| Rank | CPV division | Sector | Notices containing division |
|---:|---:|---|---:|
| 1 | 45 | Construction work | 655 |
| 2 | 71 | Architectural, construction, engineering and inspection services | 372 |
| 3 | 90 | Sewage, refuse, cleaning and environmental services | 238 |
| 4 | 34 | Transport equipment and auxiliary products | 206 |
| 5 | 33 | Medical equipment, pharmaceuticals and personal-care products | 114 |
| 6 | 50 | Repair and maintenance services | 113 |
| 7 | 09 | Petroleum products, fuel, electricity and other energy sources | 112 |
| 8 | 39 | Furniture, furnishings, appliances and cleaning products | 109 |
| 9 | 79 | Business, consulting, printing and security services | 107 |
| 10 | 44 | Construction structures, materials and auxiliary products | 86 |
| 11 | 72 | IT services | 82 |
| 12 | 60 | Transport services | 81 |
| 13 | 48 | Software packages and information systems | 74 |
| 14 | 77 | Agricultural, forestry and related services | 64 |
| 15 | 66 | Financial and insurance services | 64 |

The same sample contained 1,124 notices with service lots, 758 with supply lots and 590 with works lots. A notice may contain more than one contract nature, and some records omit that field.

## Implemented catalogue lines

The `eu-local-government-v1-2026-09-21` catalogue contains 110 entries:

| Sector | Entries |
|---|---:|
| Construction and infrastructure | 12 |
| Facilities and building operations | 12 |
| Waste and environmental services | 10 |
| IT and digital services | 14 |
| Office and administration | 10 |
| Fleet and transport | 10 |
| Education and catering | 12 |
| Health, safety and social care | 12 |
| Parks and public realm | 9 |
| Utilities and energy | 9 |

The catalogue includes 61 goods and 49 services. Monitoring readiness is explicit: 58 entries are suitable for public web-price discovery, 37 normally require supplier quotes and 15 are better treated as tender benchmarks. Every entry has a unique validated CPV 2008 code, official English/French CPV labels and a French display name. Literal SKU identifiers are included only where verified; the starter HP toner retains SKU `W2210A`.

## Concrete 100-item sample

The second catalogue level contains exactly 100 concrete products: ten products beneath each of
ten public-price-ready catalogue lines. This preserves the broad 110-line municipal taxonomy while
giving search, watchlists and market views procurement-grade brand/model or manufacturer-part
identities.

| Sampled catalogue line | Concrete items | Daily cohort |
|---|---:|---:|
| A4 office paper | 10 | 2 |
| Standard black toner cartridges | 10 | 2 |
| Business laptops | 10 | 2 |
| 24-inch business monitors | 10 | 2 |
| Network laser printers | 10 | 2 |
| Business network switches | 10 | 2 |
| Office VoIP telephones | 10 | 2 |
| Commercial fire extinguishers | 10 | 2 |
| Industrial safety helmets | 10 | 2 |
| Exterior LED luminaires | 10 | 2 |

Each item records a unique searchable identifier, English and French display names, brand/model,
default EU market and clickable official manufacturer catalogue source. The complete auditable
seed is in [`data/product_samples.tsv`](../data/product_samples.tsv). Manufacturer pages establish
product identity; they are not treated as supplier price observations. Prices enter market
statistics only after FastCPI discovers and captures a public supplier offer that passes the
comparability policy.

The 20-item cohort is deliberately bounded at two items per line. This provides useful parser and
market diversity without activating all 100 items before source yield, provider cost and evidence
quality are measured. Its prepopulated watches remain paused while the configured EXA account
returns HTTP 402.

## Interpretation limits

- TED primarily covers procurement above EU publication thresholds, while many routine municipal purchases appear only in national or regional systems.
- Frequency measures how often a division appears in this sample, not expenditure, contract value or supplier-market completeness.
- Broad works and social-service entries are catalogue concepts for tender benchmarking; they should not be treated as directly comparable web-price SKUs without scope-specific attributes.
- The next catalogue iteration should combine TED with national below-threshold data from the ten initial markets and observed FastCPI search success.
- Manufacturer sites may reject automated validation even when the human-clickable source is live;
  supplier-offer evidence therefore retains its own fetch status separately from catalogue identity.
