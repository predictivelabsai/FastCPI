from fasthtml.common import A, Div, H1, H2, Li, P, Ul


def privacy_page():
    return Div(
        H1("FastCPI Privacy Policy", cls="font-display text-4xl font-extrabold mb-3"),
        P("Last updated: 9 September 2026", cls="text-sm text-gray-400 mb-9"),
        H2("About FastCPI", cls="text-xl font-semibold mt-7 mb-2"),
        P("FastCPI is operated by Predictive Labs Ltd. Contact info@fastsme.com for privacy requests.", cls="text-gray-600 leading-relaxed"),
        H2("Information we process", cls="text-xl font-semibold mt-7 mb-2"),
        Ul(Li("Account, invitation and authentication details."), Li("AI chat prompts, chat history, watchlists and API usage."), Li("Public supplier-page observations, URLs and extraction evidence."), Li("Operational logs used for security and reliability."), cls="list-disc ml-6 text-gray-600 space-y-1"),
        H2("Why we process it", cls="text-xl font-semibold mt-7 mb-2"),
        P("We use this information to provide price discovery, comparisons, market dashboards, daily monitoring, authentication and support, and to prevent abuse.", cls="text-gray-600 leading-relaxed"),
        H2("Service providers", cls="text-xl font-semibold mt-7 mb-2"),
        P("Configured infrastructure, Postmark email, Google Sign-In, Exa discovery and AI model providers including OpenAI or xAI may process the minimum information needed to deliver their function.", cls="text-gray-600 leading-relaxed"),
        H2("Your choices", cls="text-xl font-semibold mt-7 mb-2"),
        P("You may request access, correction, export or deletion, subject to applicable law. You can also delete your account from the product."),
        A("Delete account", href="/delete-account", cls="inline-block mt-2 text-black font-semibold"),
        cls="max-w-3xl mx-auto px-5 py-16",
    )


def delete_account_page():
    return Div(
        H1("Delete your FastCPI account", cls="font-display text-4xl font-extrabold mb-4"),
        H2("Delete in the app", cls="text-xl font-semibold mt-6 mb-2"),
        P("Signed-in users can delete their account and user-owned sessions, watchlists and API keys from the account area."),
        H2("Request deletion without the app", cls="text-xl font-semibold mt-6 mb-2"),
        P("Email us from your registered address so we can verify the request."),
        A("Email deletion request", href="mailto:info@fastsme.com?subject=FastCPI%20account%20deletion%20request", cls="inline-block mt-6 text-black font-semibold"),
        cls="max-w-3xl mx-auto px-5 py-16",
    )
