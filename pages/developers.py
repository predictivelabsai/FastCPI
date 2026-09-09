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
    ("Item price variance", "Compare latest supplier offers within one country, with EU ranges as secondary context.", "GET", "/api/v1/items/{item_id}/price-variance", "prices:read"),
    ("Market overview", "Retrieve observation, source and median coverage for one market.", "GET", "/api/v1/markets/{country}/overview", "prices:read"),
    ("Price indices", "Read base-100 web-observed price-index series and their coverage.", "GET", "/api/v1/indices", "prices:read"),
    ("Watchlists", "Create and manage user-scoped daily price monitors and events.", "POST", "/api/v1/watchlists", "signed-in user"),
    ("Observation jobs", "Queue quota-controlled live discovery and poll its durable result.", "POST", "/api/v1/observation-jobs", "prices:observe"),
    ("MCP server", "Let LLM clients discover read-only catalogue, CPV, variance and monitoring tools.", "POST", "/mcp/", "Bearer fcpi_… · prices:read"),
)


FR_RESOURCES = (
    ("Rechercher des observations", "Recherchez les observations enregistrées et sourcées sans lancer une collecte.", "GET", "/api/v1/prices/search", "prices:read"),
    ("Observer les prix", "Lancez la découverte Exa, analysez les pages candidates et conservez les preuves attribuables.", "POST", "/api/v1/prices/observe", "prices:observe"),
    ("Hiérarchie CPV", "Recherchez le CPV version 2008 ou développez un code général vers ses descendants.", "GET", "/api/v1/cpv/{code}/overview", "prices:read"),
    ("Écart de prix par article", "Comparez les dernières offres fournisseurs dans un pays, avec le contexte UE en second niveau.", "GET", "/api/v1/items/{item_id}/price-variance", "prices:read"),
    ("Vue d’un marché", "Consultez la couverture des observations, sources et prix médian pour un marché.", "GET", "/api/v1/markets/{country}/overview", "prices:read"),
    ("Indices de prix", "Consultez les séries d’indices web base 100 et leur couverture.", "GET", "/api/v1/indices", "prices:read"),
    ("Listes de suivi", "Créez et gérez les suivis quotidiens et événements propres à l’utilisateur.", "POST", "/api/v1/watchlists", "utilisateur connecté"),
    ("Tâches d’observation", "Mettez en file une découverte avec quota et consultez son résultat durable.", "POST", "/api/v1/observation-jobs", "prices:observe"),
    ("Serveur MCP", "Permettez aux LLM de découvrir les outils de catalogue, CPV, écarts et suivi en lecture seule.", "POST", "/mcp/", "Bearer fcpi_… · prices:read"),
)


def developers_page(lang="en"):
    fr = lang == "fr"
    resources = FR_RESOURCES if fr else RESOURCES
    cards = [Article(
        H3(title), P(description),
        Code(Span(method, cls="dev-method"), f" {path}", cls="dev-route"),
        P(f"{'Accès' if fr else 'Access'}: {scope}", cls="dev-small"), cls="dev-card",
    ) for title, description, method, path, scope in resources]
    return Div(
        Style(DEVELOPER_CSS),
        Div(
            Span("Plateforme développeurs · API v1" if fr else "Developer platform · API v1", cls="dev-eyebrow"),
            H1("Construisez avec des observations de marché sourcées." if fr else "Build with source-backed market observations."),
            P("Interrogez les biens et services par description, code CPV, SKU, MPN ou GTIN. Chaque prix observé conserve l’heure de capture, la preuve d’extraction et l’URL publique de sa source." if fr else "Query goods and services by description, CPV code, SKU, MPN or GTIN. Every observed price retains capture time, extraction evidence and its public source URL.", cls="dev-lede"),
            Div(
                A("Guide", href="/developers#overview", cls="dev-tab primary"),
                A("Swagger UI", href="/api/docs", cls="dev-tab"),
                A("ReDoc", href="/api/redoc", cls="dev-tab"),
                A("OpenAPI v1", href="/api/openapi/v1.json", cls="dev-tab"),
                A("OpenAPI d’exécution" if fr else "Runtime OpenAPI", href="/api/openapi.json", cls="dev-tab"),
                A("Schéma de compatibilité" if fr else "Compatibility schema", href="/swagger.json", cls="dev-tab"),
                cls="dev-tabs", role="tablist", aria_label="API documentation formats",
            ),
            Div(
                Span("Authentification. " if fr else "Authentication. ", cls="font-semibold"),
                ("Créez une clé limitée dans Compte et clés API, puis envoyez-la dans l’en-tête X-API-Key. Les droits de lecture et d’observation en direct sont révocables séparément." if fr else "Create a scoped key under Account & API Keys, then send it in the X-API-Key header. Read and live-observation scopes are independently revocable."),
                cls="dev-note", id="overview",
            ),
            H2("Ressources API" if fr else "API resources"), Div(*cards, cls="dev-grid"),
            H2("Démarrage rapide" if fr else "Quick start"),
            Pre(Code("""curl --get 'https://cpi.fastsme.com/api/v1/prices/search' \\
  --header 'X-API-Key: fcpi_…' \\
  --data-urlencode 'q=A4 recycled paper' \\
  --data-urlencode 'market=FR'

# Lowest always means lowest observed in the returned public-source sample.
"""), cls="dev-example"),
            Section(
                H2("Découverte LLM et MCP" if fr else "LLM and MCP discovery"),
                P("Connectez un client MCP Streamable HTTP à https://cpi.fastsme.com/mcp/ avec Authorization: Bearer fcpi_…. L’alpha expose en lecture seule la recherche catalogue et CPV, l’écart de prix dans un pays, la couverture marché, les listes de suivi, l’état des analyses et la méthodologie FastCPI. L’autorisation OAuth reste prévue ; les clés limitées actuelles sont révocables séparément." if fr else "Connect a Streamable HTTP MCP client to https://cpi.fastsme.com/mcp/ and pass Authorization: Bearer fcpi_…. The alpha exposes read-only catalogue search, CPV lookup, same-country price variance, market coverage, watchlists, scan status and the FastCPI methodology resource. OAuth authorization-server support remains on the roadmap; current scoped keys are independently revocable.", cls="dev-small"),
                id="mcp",
            ),
            cls="dev-wrap",
        ), cls="dev",
    )
