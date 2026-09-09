from fasthtml.common import *
from utils.i18n import t, LANGUAGES, get_lang, DEFAULT_LANG


def app_styles():
    return (
        Link(rel='icon', href='/static/favicon.svg', type='image/svg+xml'),
        Link(rel='stylesheet', href='https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=DM+Serif+Display:ital@0;1&display=swap'),
        Script(src='https://cdn.tailwindcss.com'),
        Script("""
        tailwind.config = {
          theme: {
            extend: {
              colors: {
                ink: { DEFAULT: '#1A1A1A', muted: '#6B7280', dim: '#9CA3AF' },
                surface: { DEFAULT: '#FFFFFF', alt: '#F5F5F5' },
                border: '#E5E5E5',
              },
              fontFamily: {
                display: ['DM Serif Display', 'Georgia', 'serif'],
                sans: ['Inter', 'system-ui', 'sans-serif'],
              },
            },
          },
        }
        """),
        Style("body { font-family: 'Inter', system-ui, sans-serif; }"),
    )


def _lang_switcher(lang: str = "en"):
    current = LANGUAGES.get(lang, LANGUAGES["en"])
    options = []
    for code, info in LANGUAGES.items():
        active_cls = ' font-semibold text-black' if code == lang else ''
        options.append(
            A(Span(info["flag"], cls='mr-2'), Span(info["native"], cls='text-xs'),
              href=f'/set-lang/{code}',
              cls=f'flex items-center gap-1 px-3 py-1.5 text-sm text-gray-500 hover:bg-gray-50 hover:text-black transition-colors no-underline{active_cls}')
        )
    return Div(
        Button(current["flag"],
               cls='text-base leading-none px-1.5 py-1 border border-transparent rounded hover:border-gray-200 transition-colors cursor-pointer bg-transparent',
               onclick="this.nextElementSibling.classList.toggle('hidden')"),
        Div(*options,
            cls='hidden absolute right-0 top-full mt-1 bg-white border border-gray-100 rounded-lg shadow-lg z-50 py-1 min-w-[130px] flex flex-col'),
        cls='relative',
    )


def NavBar(active='home', sess=None):
    from utils.config import settings
    login_enabled = settings().login_enabled
    lang = get_lang(sess or {})

    nav_items = [
        ('home', '/', t('nav_home', lang)),
        ('advisory', '/app', t('nav_advisory', lang)),
        ('about', '/about', t('nav_about', lang)),
        ('market-map', '/app/market-map', t('nav_market_map', lang)),
        ('contact', '/contact', t('nav_contact', lang)),
    ]

    def nav_link(key, href, label):
        if key == active:
            return A(label, href=href, cls='text-sm text-black hover:text-black transition-colors no-underline')
        return A(label, href=href, cls='text-sm text-gray-400 hover:text-black transition-colors no-underline')

    nav_links = [Li(nav_link(k, h, l)) for k, h, l in nav_items]

    cta = A(t('nav_open_app', lang), href='#', onclick='showSignIn();return false',
            cls='inline-flex items-center px-4 py-2 rounded-full text-xs font-medium bg-black text-white hover:bg-gray-800 transition-colors no-underline cursor-pointer')

    return Nav(
        Div(
            A('Car', Span('Hero', cls='text-gray-400'), href='/',
              cls='font-display text-xl font-bold text-black no-underline tracking-tight shrink-0'),
            Ul(*nav_links, cls='hidden lg:flex items-center gap-6 list-none m-0 p-0'),
            Div(
                _lang_switcher(lang),
                cta,
                cls='flex items-center gap-3',
            ),
            cls='max-w-7xl mx-auto px-5 flex items-center justify-between h-16 gap-4',
        ),
        Script("""document.addEventListener('click', function(e) {
            var dd = e.target.closest('.relative');
            document.querySelectorAll('.relative > div').forEach(function(d) {
                if (d.parentElement !== dd) d.classList.add('hidden');
            });
        });"""),
        cls='bg-white/80 backdrop-blur-md sticky top-0 z-50 border-b border-gray-100',
        style='display:block',
    )


def PageFooter(lang: str = "en"):
    from fasthtml.components import Footer as FooterTag
    return FooterTag(
        Div(
            Div(
                Div(
                    H3('Car', Span('Hero', cls='text-gray-500'),
                       cls='font-display text-black text-xl mb-4 tracking-wide'),
                    P(t('footer_desc', lang),
                      cls='text-sm leading-relaxed text-gray-500'),
                ),
                Div(
                    H4(t('footer_platform', lang), cls='text-black text-sm uppercase tracking-wider mb-4'),
                    Ul(
                        Li(A(t('nav_advisory', lang), href='/app', cls='text-gray-500 no-underline text-sm hover:text-black transition-colors'), cls='mb-2'),
                        Li(A(t('nav_market_map', lang), href='/app/market-map', cls='text-gray-500 no-underline text-sm hover:text-black transition-colors'), cls='mb-2'),
                        cls='list-none'
                    )
                ),
                Div(
                    H4(t('footer_resources', lang), cls='text-black text-sm uppercase tracking-wider mb-4'),
                    Ul(
                        Li(A(t('nav_about', lang), href='/about', cls='text-gray-500 no-underline text-sm hover:text-black transition-colors'), cls='mb-2'),
                        Li(A(t('nav_contact', lang), href='/contact', cls='text-gray-500 no-underline text-sm hover:text-black transition-colors'), cls='mb-2'),
                        cls='list-none'
                    )
                ),
                Div(
                    H4(t('footer_legal', lang), cls='text-black text-sm uppercase tracking-wider mb-4'),
                    Ul(
                        Li(A(t('footer_terms', lang), href='/terms', cls='text-gray-500 no-underline text-sm hover:text-black transition-colors'), cls='mb-2'),
                        Li(A(t('footer_privacy', lang), href='/privacy', cls='text-gray-500 no-underline text-sm hover:text-black transition-colors'), cls='mb-2'),
                        Li(A('Delete account', href='/delete-account', cls='text-gray-500 no-underline text-sm hover:text-black transition-colors'), cls='mb-2'),
                        cls='list-none'
                    )
                ),
                cls='max-w-7xl mx-auto grid grid-cols-1 md:grid-cols-4 gap-12'
            ),
            Div(
                P(t('footer_copyright', lang)),
                P(t('footer_disclaimer', lang)),
                cls='max-w-7xl mx-auto mt-12 pt-8 border-t border-gray-200 flex flex-col md:flex-row justify-between items-center text-sm gap-4'
            ),
        ),
        cls='bg-white text-gray-400 pt-16 pb-8 px-8 border-t border-gray-100'
    )


def Page(content, active='home', title='CarHero', sess=None):
    lang = get_lang(sess or {})
    return (
        Title(f'{title} — AI Car Advisory'),
        NavBar(active, sess=sess),
        Main(content),
        PageFooter(lang=lang)
    )
