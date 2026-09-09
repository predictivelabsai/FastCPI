"""FastCPI public landing page."""

from fasthtml.common import A, Article, Div, H1, H2, H3, P, Section, Span

from pricing.markets import MARKETS
from utils.fastcpi_i18n import tr
from utils.i18n import get_lang


def _feature(title: str, body: str):
    return Article(H3(title, cls="text-lg font-medium text-black mb-2"),
                   P(body, cls="text-sm leading-relaxed text-gray-500"),
                   cls="p-6 rounded-xl bg-white border border-gray-100")


def home_page(sess=None):
    lang = get_lang(sess or {})
    markets = ", ".join(MARKETS)
    return Div(
        Section(Div(
            Span(tr("eyebrow", lang), cls="text-xs tracking-[.18em] uppercase text-emerald-700"),
            H1(tr("headline", lang), cls="mt-4 text-[40px] sm:text-5xl md:text-7xl font-medium tracking-tight text-black leading-[1.06] max-w-4xl"),
            P(tr("hero", lang),
              cls="mt-5 text-lg md:text-xl text-gray-500 max-w-2xl leading-relaxed"),
            P(tr("query_modes", lang),
              cls="mt-3 text-sm text-gray-500 max-w-xl leading-relaxed"),
            Div(A(tr("google", lang), href="/auth/google",
                  cls="inline-flex px-6 py-3 rounded-full text-sm font-medium no-underline bg-black text-white hover:bg-gray-800"),
                A("API documentation", href="/api/v1/docs",
                  cls="inline-flex px-6 py-3 rounded-full text-sm font-medium no-underline border border-gray-200 text-black hover:border-black"),
                cls="mt-8 flex gap-3 flex-wrap"),
            P(tr("invite", lang), cls="mt-3 text-xs text-gray-400"),
            cls="max-w-7xl mx-auto px-5 md:px-6 py-20 md:py-28")),
        Div(Div(
            Div(Span("10", cls="text-2xl font-semibold"), Span("initial markets", cls="text-xs uppercase tracking-wider text-gray-400"), cls="flex flex-col"),
            Div(Span("CPV 2008", cls="text-2xl font-semibold"), Span("official vocabulary", cls="text-xs uppercase tracking-wider text-gray-400"), cls="flex flex-col"),
            Div(Span("Daily", cls="text-2xl font-semibold"), Span("watchlist scans", cls="text-xs uppercase tracking-wider text-gray-400"), cls="flex flex-col"),
            Div(Span("Source-first", cls="text-2xl font-semibold"), Span("provenance", cls="text-xs uppercase tracking-wider text-gray-400"), cls="flex flex-col"),
            cls="max-w-7xl mx-auto px-5 md:px-6 py-6 grid grid-cols-2 md:grid-cols-4 gap-7"),
            cls="border-y border-gray-100 bg-gray-50/60"),
        Section(Div(
            H2("Procurement evidence, not an official CPI.", cls="text-2xl md:text-3xl font-medium mb-9"),
            Div(
                _feature("Observed prices", "FastCPI separates fetched and extracted prices from discovery-only candidate pages."),
                _feature("Comparable terms", "Unit, quantity, currency, VAT, delivery, MOQ and service period stay visible."),
                _feature("Market monitoring", "Watch a specification, identifier or CPV category and review its daily movement."),
                cls="grid md:grid-cols-3 gap-4"),
            cls="max-w-7xl mx-auto px-5 md:px-6"), cls="py-16 md:py-20"),
        Section(Div(
            H2("Initial coverage", cls="text-2xl font-medium mb-3"),
            P(markets, cls="text-sm text-gray-500"),
            P("Coverage describes the public sources observed by FastCPI; it is never presented as the complete market.",
              cls="mt-3 text-xs text-gray-400"),
            cls="max-w-7xl mx-auto px-5 md:px-6"), cls="py-12 border-t border-gray-100 bg-gray-50"),
        style="overflow-x:hidden",
    )
