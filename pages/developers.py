"""Public FastCPI developer platform overview."""

from fasthtml.common import A, Article, Code, Div, H1, H2, H3, P, Pre, Section, Span, Style


DEVELOPER_CSS = """
.dev{--a:#147d64;--t:#edf8f4;--i:#17201c;--m:#66736d;--l:#dfe8e4;color:var(--i)}
.dev-wrap{max-width:1120px;margin:auto;padding:64px 24px 88px}.dev-eyebrow{font-size:12px;font-weight:700;letter-spacing:.16em;text-transform:uppercase;color:var(--a)}
.dev h1{font-size:clamp(42px,6vw,68px);line-height:1.02;letter-spacing:-.05em;max-width:850px;margin:18px 0}.dev-lede{font-size:19px;line-height:1.65;color:var(--m);max-width:780px}
.dev-tabs{display:flex;gap:8px;flex-wrap:wrap;margin:30px 0 42px}.dev-tab{padding:10px 15px;border:1px solid var(--l);border-radius:999px;color:var(--i);text-decoration:none;font-size:13px;font-weight:650;background:#fff}.dev-tab:hover,.dev-tab.primary{background:var(--a);border-color:var(--a);color:#fff}
.dev-note{padding:20px 22px;border:1px solid #cfe9df;border-radius:18px;background:var(--t);line-height:1.6;margin-bottom:42px}.dev-note strong{color:var(--a)}
.dev-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;margin:18px 0 44px}.dev-card{border:1px solid var(--l);border-radius:18px;padding:22px;background:#fff;box-shadow:0 8px 24px rgba(23,32,28,.04)}.dev-card h3{font-size:18px;margin:0 0 8px}.dev-card p{color:var(--m);line-height:1.55;min-height:48px}.dev-route{display:block;background:#17201c;color:#f5faf8;padding:9px 11px;border-radius:8px;margin-top:8px;font:12px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace;overflow:auto}.dev-method{color:#86efac;font-weight:800}.dev h2{font-size:28px;margin:46px 0 14px}.dev-example{background:#17201c;color:#e7f1ed;border-radius:16px;padding:22px;overflow:auto;font:13px/1.65 ui-monospace,SFMono-Regular,Menlo,monospace}.dev-small{color:var(--m);font-size:13px;line-height:1.65}
@media(max-width:720px){.dev-grid{grid-template-columns:1fr}.dev-wrap{padding-top:42px}.dev h1{font-size:42px}}
"""


RESOURCES = (
    ("Search observations", "Search persisted, source-backed observations without starting a crawl.", "GET", "/api/v1/prices/search", "prices:read"),
    ("Observe prices", "Run Exa discovery, fetch candidate pages and persist attributable evidence.", "POST", "/api/v1/prices/observe", "prices:observe"),
    ("CPV hierarchy", "Search CPV Version 2008 or expand a broad code into descendants.", "GET", "/api/v1/cpv/{code}/overview", "prices:read"),
    ("Market overview", "Retrieve observation, source and median coverage for one market.", "GET", "/api/v1/markets/{country}/overview", "prices:read"),
    ("Price indices", "Read base-100 web-observed price-index series and their coverage.", "GET", "/api/v1/indices", "prices:read"),
    ("Watchlists", "Create and manage user-scoped daily price monitors and events.", "POST", "/api/v1/watchlists", "signed-in user"),
)


def developers_page():
    cards = [Article(
        H3(title), P(description),
        Code(Span(method, cls="dev-method"), f" {path}", cls="dev-route"),
        P(f"Access: {scope}", cls="dev-small"), cls="dev-card",
    ) for title, description, method, path, scope in RESOURCES]
    return Div(
        Style(DEVELOPER_CSS),
        Div(
            Span("Developer platform · API v1", cls="dev-eyebrow"),
            H1("Build with source-backed market observations."),
            P("Query goods and services by description, CPV code, SKU, MPN or GTIN. Every observed price retains capture time, extraction evidence and its public source URL.", cls="dev-lede"),
            Div(
                A("Guide", href="/developers#overview", cls="dev-tab primary"),
                A("Swagger UI", href="/api/docs", cls="dev-tab"),
                A("ReDoc", href="/api/redoc", cls="dev-tab"),
                A("OpenAPI v1", href="/api/openapi/v1.json", cls="dev-tab"),
                A("Runtime OpenAPI", href="/api/openapi.json", cls="dev-tab"),
                A("Compatibility schema", href="/swagger.json", cls="dev-tab"),
                cls="dev-tabs", role="tablist", aria_label="API documentation formats",
            ),
            Div(
                Span("Authentication. ", cls="font-semibold"),
                "Create a scoped key under Account & API Keys, then send it in the X-API-Key header. Read and live-observation scopes are independently revocable.",
                cls="dev-note", id="overview",
            ),
            H2("API resources"), Div(*cards, cls="dev-grid"),
            H2("Quick start"),
            Pre(Code("""curl --get 'https://cpi.fastsme.com/api/v1/prices/search' \\
  --header 'X-API-Key: fcpi_…' \\
  --data-urlencode 'q=A4 recycled paper' \\
  --data-urlencode 'market=FR'

# Lowest always means lowest observed in the returned public-source sample.
"""), cls="dev-example"),
            Section(
                H2("LLM and MCP discovery"),
                P("A read-only MCP server is the next integration slice. It will expose price search, CPV lookup, market coverage, index series and methodology resources before live crawl or watchlist writes are enabled.", cls="dev-small"),
                id="mcp",
            ),
            cls="dev-wrap",
        ), cls="dev",
    )
