"""Public Google, email and password account access."""

import json

from fasthtml.common import A, Button, Div, Form, H1, Input, P, Script, Span

from utils.fastcpi_i18n import app_tr


def access_page(lang: str = "en", mode: str = "login"):
    labels = {key: app_tr(key, lang) for key in (
        "sign_in", "create_account", "signin_body", "continue_google", "signup_body",
        "signup_google", "or", "name", "email", "password", "password_hint",
        "forgot_password", "login_failed", "verify_email", "registration_failed",
    )}
    signup = mode == "signup"
    endpoint = "/auth/register" if signup else "/auth/login"
    success_js = (
        "msg.className='text-xs min-h-5 text-emerald-700';"
        f"msg.textContent=d.message||{json.dumps(labels['verify_email'])}"
        if signup else "location.href='/app'"
    )
    failure = labels["registration_failed"] if signup else labels["login_failed"]
    name_input = (
        Input(name="name", placeholder=labels["name"],
              cls="w-full px-3 py-2.5 border border-gray-200 rounded-lg text-sm")
        if signup else None
    )
    return Div(
        Div(
            Span("Accès sécurisé" if lang == "fr" else "Secure account access",
                 cls="text-xs uppercase tracking-[.16em] text-emerald-700"),
            H1("Fast", Span("CPI", cls="text-emerald-700"),
               cls="font-display text-4xl mt-3 mb-2"),
            P(labels["signup_body"] if signup else labels["signin_body"],
              cls="text-sm text-gray-500 mb-6"),
            Div(
                A(labels["sign_in"], href="/login",
                  cls=f"px-4 py-2 text-sm no-underline border-b-2 {'border-transparent text-gray-400' if signup else 'border-emerald-700 text-black'}"),
                A(labels["create_account"], href="/signup",
                  cls=f"px-4 py-2 text-sm no-underline border-b-2 {'border-emerald-700 text-black' if signup else 'border-transparent text-gray-400'}"),
                cls="flex border-b border-gray-100 mb-5",
            ),
            A(labels["signup_google"] if signup else labels["continue_google"],
              href="/auth/google",
              cls="flex justify-center w-full px-4 py-3 rounded-lg border border-gray-200 text-sm font-medium text-black no-underline hover:bg-gray-50"),
            Div(Span(cls="h-px bg-gray-200 flex-1"),
                Span(labels["or"], cls="text-xs text-gray-400"),
                Span(cls="h-px bg-gray-200 flex-1"),
                cls="flex items-center gap-3 my-5"),
            Form(
                name_input,
                Input(name="email", type="email", placeholder=labels["email"],
                      required=True, cls="w-full px-3 py-2.5 border border-gray-200 rounded-lg text-sm"),
                Input(name="password", type="password",
                      placeholder=labels["password_hint"] if signup else labels["password"],
                      required=True, cls="w-full px-3 py-2.5 border border-gray-200 rounded-lg text-sm"),
                Div(id="access-message", cls="text-xs min-h-5"),
                Button(labels["create_account"] if signup else labels["sign_in"],
                       type="submit",
                       cls="w-full px-4 py-2.5 rounded-lg bg-black text-white text-sm border-none cursor-pointer"),
                id="access-form", cls="space-y-3",
            ),
            cls="w-full max-w-md border border-gray-100 rounded-2xl bg-white shadow-sm p-7",
        ),
        Script(f"""
        document.getElementById('access-form').addEventListener('submit', async function(e) {{
          e.preventDefault(); const msg=document.getElementById('access-message'); msg.textContent='';
          const r=await fetch('{endpoint}', {{method:'POST',body:new FormData(this)}});
          const d=await r.json();
          if(r.ok && d.ok) {{ {success_js}; }}
          else {{ msg.className='text-xs min-h-5 text-red-600'; msg.textContent=d.error||{json.dumps(failure)}; }}
        }});
        """),
        cls="min-h-[calc(100vh-4rem)] bg-gray-50 flex items-center justify-center px-5 py-12",
    )
