from fasthtml.common import *
from fasthtml.common import NotStr
from utils.i18n import t, agent_t, get_lang
from utils.config import get_all_brands
from chat.components import signin_overlay


def _stat(value, label):
    return Div(
        Span(value, cls='text-xl md:text-2xl font-semibold text-black'),
        Span(label, cls='text-[11px] tracking-[0.12em] uppercase text-gray-400 mt-1'),
        cls='flex flex-col items-center md:items-start',
    )


def home_page(sess=None):
    lang = get_lang(sess or {})

    agents = ["car_search", "market_analyst", "valuator", "car_compare", "advisor"]

    hero = Section(
        Div(
            H1(t('hero_h1', lang),
               cls='text-[36px] sm:text-5xl md:text-7xl font-medium tracking-tight text-black leading-[1.08] max-w-4xl'),
            P(t('hero_h2', lang),
              cls='mt-3 text-xl md:text-2xl text-gray-400 max-w-2xl'),
            P(t('hero_body', lang),
              cls='mt-5 text-base text-gray-500 max-w-xl leading-relaxed'),
            Div(
                A(t('hero_cta_start', lang), href='#', onclick='showSignIn();return false',
                  cls='inline-flex items-center gap-2 px-6 py-3 rounded-full text-sm font-medium no-underline bg-black text-white hover:bg-gray-800 transition-colors cursor-pointer'),
                A(t('hero_cta_explore', lang), href='/app/market-map',
                  cls='inline-flex items-center gap-2 px-6 py-3 rounded-full text-sm font-medium no-underline bg-transparent text-black border border-gray-200 hover:border-black transition-colors'),
                cls='mt-8 flex items-center gap-3 flex-wrap',
            ),
            cls='max-w-7xl mx-auto px-5 md:px-6 py-20 md:py-28',
        ),
    )

    stats = Div(
        Div(
            _stat('50,000+', t('stat_listings', lang)),
            _stat('12', t('stat_brands', lang)),
            _stat('5+', t('stat_countries', lang)),
            _stat('8', t('stat_sources', lang)),
            cls='max-w-7xl mx-auto px-5 md:px-6 py-5 grid grid-cols-2 md:grid-cols-4 gap-6',
        ),
        cls='border-y border-gray-100 bg-gray-50/60',
    )

    features = Section(
        Div(
            Div(
                *[Article(
                    H3(title, cls='text-black text-lg font-medium mb-2'),
                    P(body, cls='text-gray-500 text-sm leading-relaxed'),
                    A(link, href=href, cls='inline-block mt-3 text-sm font-medium text-black no-underline hover:underline'),
                    cls='p-6 rounded-xl bg-white border border-gray-100',
                ) for title, body, link, href in [
                    (t('feat_advisory', lang), t('feat_advisory_body', lang), t('feat_advisory_link', lang), '/app'),
                    (t('feat_market', lang), t('feat_market_body', lang), t('feat_market_link', lang), '/app/market-map'),
                    (t('feat_valuation', lang), t('feat_valuation_body', lang), t('feat_valuation_link', lang), '/app'),
                ]],
                cls='grid md:grid-cols-3 gap-4',
            ),
            cls='max-w-7xl mx-auto px-5 md:px-6',
        ),
        cls='py-14 md:py-20 border-t border-gray-100',
    )

    how = Section(
        Div(
            Span('How it works', cls='text-[11px] tracking-[0.18em] uppercase text-gray-400'),
            H2(t('how_title', lang), cls='mt-3 text-2xl md:text-3xl font-medium text-black max-w-2xl mb-10'),
            Div(
                *[Article(
                    P(num, cls='text-[11px] tracking-widest uppercase text-gray-300 mb-3'),
                    H3(title, cls='text-black text-lg font-medium mb-2'),
                    P(body, cls='text-gray-500 text-sm leading-relaxed'),
                    cls='p-6 rounded-xl bg-white border border-gray-100',
                ) for num, title, body in [
                    ('01', t('how_01_title', lang), t('how_01_body', lang)),
                    ('02', t('how_02_title', lang), t('how_02_body', lang)),
                    ('03', t('how_03_title', lang), t('how_03_body', lang)),
                ]],
                cls='grid md:grid-cols-3 gap-4',
            ),
            cls='max-w-7xl mx-auto px-5 md:px-6',
        ),
        cls='py-14 md:py-20 border-t border-gray-100 bg-gray-50',
    )

    agent_cards = [
        Div(
            H4(agent_t(slug, 'name', lang), cls='text-sm font-medium text-black mb-1'),
            P(agent_t(slug, 'one_liner', lang), cls='text-xs text-gray-500 leading-relaxed'),
            cls='p-4 rounded-xl border border-gray-100',
        )
        for slug in agents
    ]

    agents_section = Section(
        Div(
            Span(t('agents_title', lang), cls='text-[11px] tracking-[0.18em] uppercase text-gray-400'),
            H2(t('agents_subtitle', lang), cls='mt-3 text-2xl md:text-3xl font-medium text-black max-w-2xl mb-10'),
            Div(*agent_cards, cls='grid grid-cols-2 md:grid-cols-5 gap-3'),
            cls='max-w-7xl mx-auto px-5 md:px-6',
        ),
        cls='py-14 md:py-20 border-t border-gray-100',
    )

    brands_section = Section(
        Div(
            Span('Brands we cover', cls='text-[11px] tracking-[0.18em] uppercase text-gray-400'),
            Div(
                *[Span(brand, cls='px-4 py-2 rounded-full border border-gray-100 text-sm text-gray-600')
                  for brand in get_all_brands()],
                cls='mt-4 flex flex-wrap gap-2 justify-center',
            ),
            cls='max-w-7xl mx-auto px-5 md:px-6 text-center',
        ),
        cls='py-10 border-t border-gray-100',
    )

    cta = Section(
        Div(
            H2(t('cta_headline', lang), cls='text-2xl md:text-3xl font-medium text-black mb-4'),
            P(t('cta_body', lang), cls='text-gray-500 text-sm max-w-xl mx-auto mb-8 leading-relaxed'),
            A(t('hero_cta_start', lang), href='#', onclick='showSignIn();return false',
              cls='inline-flex items-center px-6 py-3 rounded-full text-sm font-medium no-underline bg-black text-white hover:bg-gray-800 transition-colors cursor-pointer'),
            cls='max-w-7xl mx-auto px-5 md:px-6 text-center',
        ),
        cls='py-14 md:py-20 border-t border-gray-100 bg-gray-50',
    )

    sources = Div(
        Div(
            P('Data from', cls='text-[11px] tracking-[0.12em] uppercase text-gray-400 mb-2'),
            Div(
                *[Span(src, cls='text-sm text-gray-500 font-medium')
                  for src in ['AutoTrader UK', 'mobile.de', 'AutoScout24', 'Autohero']],
                cls='flex items-center gap-4 flex-wrap justify-center',
            ),
            cls='max-w-7xl mx-auto px-5 md:px-6 text-center',
        ),
        cls='py-6 border-t border-gray-100',
    )

    auth_modal = signin_overlay(lang)

    auth_js = Script(NotStr("""
function switchAuthTab(tab) {
    document.getElementById('auth-form-login').style.display = tab === 'login' ? '' : 'none';
    document.getElementById('auth-form-register').style.display = tab === 'register' ? '' : 'none';
    document.getElementById('auth-form-forgot').style.display = tab === 'forgot' ? '' : 'none';
    document.querySelectorAll('.auth-tab').forEach(function(t) { t.classList.remove('active'); });
    var tabEl = document.getElementById('auth-tab-' + tab);
    if (tabEl) tabEl.classList.add('active');
}
function showForgotPassword(e) { e && e.preventDefault(); switchAuthTab('forgot'); }
function showSignIn() {
    document.getElementById('signin-overlay').classList.add('visible');
    switchAuthTab('login');
}
async function doLogin() {
    var email = document.getElementById('login-email').value.trim();
    var password = document.getElementById('login-password').value;
    var errEl = document.getElementById('login-error');
    errEl.textContent = '';
    if (!email || !password) { errEl.textContent = 'Email and password required'; return; }
    var resp = await fetch('/auth/login', { method: 'POST', body: new URLSearchParams({ email: email, password: password }) });
    var data = await resp.json();
    if (data.ok) { window.location.href = '/app'; }
    else if (data.error === 'no_password') {
        errEl.innerHTML = 'No password set. <a href="#" onclick="showSetPassword(\\'' + email + '\\');return false" style="color:#000;font-weight:600;">Set one now</a>';
    } else { errEl.textContent = data.error || 'Login failed'; }
}
async function doRegister() {
    var name = document.getElementById('reg-name').value.trim();
    var email = document.getElementById('reg-email').value.trim();
    var password = document.getElementById('reg-password').value;
    var errEl = document.getElementById('reg-error');
    var okEl = document.getElementById('reg-success');
    errEl.textContent = ''; okEl.textContent = '';
    if (!email || !password) { errEl.textContent = 'Email and password required'; return; }
    var resp = await fetch('/auth/register', { method: 'POST', body: new URLSearchParams({ email: email, password: password, name: name }) });
    var data = await resp.json();
    if (data.ok) { okEl.textContent = data.message || 'Check your email to verify'; }
    else { errEl.textContent = data.error || 'Registration failed'; }
}
async function doForgot() {
    var email = document.getElementById('forgot-email').value.trim();
    var msgEl = document.getElementById('forgot-msg');
    msgEl.textContent = '';
    if (!email) { msgEl.textContent = 'Enter your email'; msgEl.style.color = '#DC2626'; return; }
    var resp = await fetch('/auth/forgot', { method: 'POST', body: new URLSearchParams({ email: email }) });
    var data = await resp.json();
    msgEl.style.color = '#16A34A';
    msgEl.textContent = data.message || 'Reset link sent if account exists';
}
function showSetPassword(email) {
    var form = document.getElementById('auth-form-login');
    form.innerHTML = '<p style="font-size:13px;color:#4B5563;margin-bottom:12px;">Set a password for <strong>' + email + '</strong></p>'
        + '<input type="password" id="set-pw-input" placeholder="New password (min 6 chars)" style="width:100%;padding:8px 12px;border:1px solid #E5E7EB;border-radius:6px;font-size:14px;margin-bottom:12px;">'
        + '<div id="set-pw-error" style="color:#DC2626;font-size:12px;margin-bottom:8px;"></div>'
        + '<button onclick="doSetPassword(\\'' + email + '\\')" style="padding:8px 16px;background:#000;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:13px;">Set Password</button>';
}
async function doSetPassword(email) {
    var password = document.getElementById('set-pw-input').value;
    var errEl = document.getElementById('set-pw-error');
    if (!password || password.length < 6) { errEl.textContent = 'Min 6 characters'; return; }
    var resp = await fetch('/auth/set-password', { method: 'POST', body: new URLSearchParams({ email: email, password: password }) });
    var data = await resp.json();
    if (data.ok) window.location.href = '/app';
    else errEl.textContent = data.error || 'Failed';
}
document.addEventListener('click', function(e) {
    var overlay = document.getElementById('signin-overlay');
    if (e.target === overlay) overlay.classList.remove('visible');
});
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        var overlay = document.getElementById('signin-overlay');
        if (overlay) overlay.classList.remove('visible');
    }
});
"""))

    auth_css = Style("""
.signin-overlay { position:fixed; inset:0; background:rgba(0,0,0,0.3); display:none; align-items:center; justify-content:center; z-index:100; }
.signin-overlay.visible { display:flex; }
.auth-tab { padding:8px 16px; font-size:13px; font-weight:500; background:transparent; border:none; border-bottom:2px solid transparent; color:#6B7280; cursor:pointer; }
.auth-tab.active { color:#1A1A1A; border-bottom-color:#1A1A1A; }
.google-btn { display:flex; align-items:center; justify-content:center; gap:10px; width:100%; padding:10px 16px; border:1px solid #dadce0; border-radius:6px; background:#fff; font-size:14px; font-weight:500; color:#3c4043; text-decoration:none; cursor:pointer; transition:background 0.15s, box-shadow 0.15s; }
.google-btn:hover { background:#f7f8f8; box-shadow:0 1px 3px rgba(0,0,0,0.08); }
.google-btn-icon { display:flex; align-items:center; }
.google-btn-text { font-family:'Inter',sans-serif; }
.google-divider { display:flex; align-items:center; gap:12px; margin:14px 0; }
.google-divider-line { flex:1; height:1px; background:#e5e7eb; }
.google-divider-text { font-size:12px; color:#9ca3af; }
""")

    return Div(
        hero, stats, features, how, agents_section, brands_section, cta, sources,
        auth_modal, auth_css, auth_js,
        style='overflow-x:hidden',
    )
