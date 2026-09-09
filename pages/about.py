from fasthtml.common import Div, H1, H2, P


def about_page():
    return Div(
        H1("About FastCPI", cls="font-display text-4xl font-extrabold text-black mb-4"),
        P("Evidence-led B2B web-market price intelligence.", cls="text-xl text-gray-500 mb-10"),
        H2("What FastCPI measures", cls="text-2xl font-semibold mb-3"),
        P("FastCPI observes public asking prices for goods and services, keeps source provenance, and normalises comparable commercial terms. It is not an official CPI and does not represent completed transactions or complete market coverage.", cls="text-gray-600 leading-relaxed mb-7"),
        H2("Built for procurement", cls="text-2xl font-semibold mb-3"),
        P("Procurement teams can search in plain language, by product identifier, or by CPV Version 2008 division and its descendants. Daily watchlists track changes across ten initial European markets.", cls="text-gray-600 leading-relaxed"),
        cls="max-w-3xl mx-auto px-5 py-16",
    )
