# SKILLS.md

Comprehensive guide for developing, testing, deploying, and managing CarHero.

---

## 1. Local Development

### Environment setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in secrets (see §7 for the full list).

### Run the server

```bash
python main.py                  # starts on PORT (default 5011)
PORT=5010 python main.py        # override port for local dev
```

Health check:
```bash
curl http://localhost:5010/health   # {"status": "ok"}
```

### Key URLs (local, port 5010)

| URL | What |
|-----|------|
| `/` | Landing page |
| `/app` | Chat advisor (main product) |
| `/app/market-map` | Market analytics |
| `/api/v1/docs` | Swagger UI (FastAPI, auto-generated) |
| `/api/v1/health` | API health check |

---

## 2. Unit / Integration Tests (pytest)

### Run all tests

```bash
source .venv/bin/activate
pytest tests/ -v
```

### Run a specific test file

```bash
pytest tests/test_api.py -v              # 24 API integration tests
pytest tests/test_deals_tool.py -v       # deals tool tests
pytest tests/test_deals_scanner.py -v    # scraper/scanner tests
pytest tests/test_daily_deals_cli.py -v  # daily digest CLI tests
pytest tests/test_email.py -v            # email delivery tests
```

### Integration tests (hit real APIs)

Some tests require `--run-integration` to run. These hit live services (Postmark, DB, etc.):

```bash
pytest tests/ --run-integration -v
```

### API test details (`tests/test_api.py`)

Requires the server running on `localhost:5010`. Tests cover:
- Health endpoint
- Auth: register, login, token validation, duplicate email, bad credentials
- Agents: list all, verify structure
- Sessions: list, create via chat, get detail, share, delete lifecycle
- Chat SSE streaming: car_search, market_analyst, valuator, car_compare, advisor

The tests use `httpx.Client` with streaming for SSE chat endpoints. Each chat test sends a domain-specific query and verifies SSE events arrive correctly.

### Writing new tests

- Place in `tests/` directory
- `conftest.py` adds project root to `sys.path` and loads `.env`
- Use `--run-integration` flag for tests that hit external services
- API tests assume server is running — start it first

---

## 3. Playwright MCP Regression Tests

Browser-based UI regression tests using Playwright MCP. Every UI change MUST be verified before reporting complete.

### When to test

After any change to:
- `chat/components.py` — left pane, center pane, right pane, welcome hero, sign-in overlay
- `chat/layout.py` — page wrapper, head, overlays, toggle buttons
- `chat/routes.py` — chat API, session endpoints, share routes
- `chat/market_map.py` — market map page, tabs, charts
- `static/app.css` — layout, responsive breakpoints, component styles
- `static/chat.js` — chat interaction, SSE, share/copy, artifact pane, toggles
- `auth/routes.py` — login, register, forgot password, profile
- `main.py` — `/app` or `/` route changes

### Pre-flight

1. Start the server:
   ```bash
   python main.py &
   ```
2. Verify it responds:
   ```bash
   curl -s -o /dev/null -w '%{http_code}' http://localhost:5010/app
   ```
3. Load Playwright MCP tools via ToolSearch:
   ```
   select:mcp__plugin_playwright_playwright__browser_navigate,mcp__plugin_playwright_playwright__browser_snapshot,mcp__plugin_playwright_playwright__browser_take_screenshot,mcp__plugin_playwright_playwright__browser_resize,mcp__plugin_playwright_playwright__browser_click,mcp__plugin_playwright_playwright__browser_evaluate,mcp__plugin_playwright_playwright__browser_hover,mcp__plugin_playwright_playwright__browser_type,mcp__plugin_playwright_playwright__browser_close
   ```

### Viewport matrix

| Viewport | Width | Height | Represents |
|----------|-------|--------|------------|
| Desktop | 1280 | 800 | Laptop / monitor |
| Mobile | 375 | 812 | iPhone 14 / similar |

Use `browser_resize` to switch between them.

### Desktop checklist (1280x800)

- [ ] 3-pane layout: left pane (280px), center pane, right pane (closed)
- [ ] Left pane: CarHero logo, "+ New chat", History, Agents (3 categories), Workspace links
- [ ] Workspace links: Market Map, Favorites, Saved Searches, My Garage, Profile & Preferences
- [ ] Center pane: header with "Car Advisor", language dropdown, Share/Copy/Canvas icons
- [ ] Welcome hero with 5 sample prompt cards
- [ ] Chat input + send button at bottom
- [ ] Hamburger menu NOT visible
- [ ] Send search query → right pane auto-opens with listing cards
- [ ] Right pane scrollable
- [ ] Canvas button toggles right pane open/closed
- [ ] Share button shows green checkmark flash
- [ ] Copy button shows green checkmark flash
- [ ] "+ New chat" resets to clean state
- [ ] Session history clickable, loads messages
- [ ] Session share hover shows chain-link icon

### Mobile checklist (375x812)

- [ ] Left pane hidden (off-screen at x=-280)
- [ ] Right pane hidden (off-screen)
- [ ] Hamburger menu visible, 40x40 tap target
- [ ] Hamburger → left pane slides in, overlay visible behind it
- [ ] Tap overlay → left pane closes
- [ ] Welcome hero and sample cards render
- [ ] Chat input + send button within viewport
- [ ] Send query → chat response visible, right pane stays CLOSED
- [ ] "Results" FAB appears (black pill, bottom-right) after artifacts arrive
- [ ] Tap Results FAB → right pane slides in, overlay behind it
- [ ] Results pane scrollable (all listing cards reachable)
- [ ] ✕ close button closes right pane, FAB reappears
- [ ] Tap overlay behind right pane → closes it
- [ ] Hamburger still works after query

### Sign-in overlay (both viewports)

- [ ] "Sign In" button → overlay appears
- [ ] Tab switching: Sign In / Register
- [ ] Login: email + password, "Forgot password?" link
- [ ] Register: name, email, password
- [ ] Google SSO button present
- [ ] Cancel or backdrop click closes overlay

### Market Map (`/app/market-map`)

- [ ] Page loads with tab navigation
- [ ] Charts render (Plotly)
- [ ] Responsive on both viewports

### Architecture reference (mobile)

**Z-index hierarchy:**
- 40: `.left-overlay`
- 50: `.left-pane`
- 55: `.right-overlay`
- 60: `.right-pane`
- 65: `.mobile-menu-btn` (position: fixed, always above right pane)
- 100: `.signin-overlay`

**Critical CSS:**
- `.artifact-body` needs `min-height: 0` for flex overflow scrolling
- `.artifact-header` needs `flex-shrink: 0`
- Right pane mobile: `position: fixed; right: -100%` → `right: 0`
- Left pane mobile: `position: fixed; left: -280px` → `left: 0`
- Hamburger: `display: none` on desktop, `display: flex` + `position: fixed` + `z-index: 65` on mobile (40x40, always above right pane)

**JS behavior:**
- `showArtifact()`: Desktop auto-opens right pane; mobile shows Results FAB only
- `toggleArtifactPane()`: On mobile also toggles `#right-overlay`
- `toggleLeftPane()`: Toggles `.left-pane.open` and `.left-overlay.visible`; also closes right pane if open

### Verification approach

- `browser_snapshot` — primary tool for element presence, text, structure
- `browser_evaluate` — DOM state checks (classList, getBoundingClientRect, computed styles)
- `browser_take_screenshot` — visual layout, overflow, alignment, spacing
- `browser_click` / `browser_hover` — interactive element testing
- Snapshot tips: `depth: 2-3` for page structure, `depth: 4-5` for section detail, `boxes: true` for position

### Cleanup

```bash
# Close Playwright browser
browser_close

# Kill dev server
kill $(lsof -ti:5010) 2>/dev/null
```

---

## 4. Docker

### Build and run locally

```bash
docker build -t carhero .
docker run -p 5011:5011 --env-file .env carhero
```

### Docker Compose

```bash
docker compose up --build        # foreground
docker compose up --build -d     # detached
docker compose logs -f web       # tail logs
docker compose down              # stop
```

The Compose file passes all env vars through from the host environment or `.env` file.

### Health check

Built into both Dockerfile and docker-compose.yaml:
```
python -c "import urllib.request; urllib.request.urlopen('http://localhost:5011/health').read()"
```

Runs every 30s, 10s timeout, 20s start period, 3 retries.

---

## 5. Deployment (Coolify)

### How it works

- **Auto-deploy**: push to `main` on GitHub → Coolify detects, builds Docker image, deploys
- **Port**: 5011 in production (set in Dockerfile and Coolify labels)
- **Secrets**: all env vars configured in Coolify dashboard (not in code)

### Deploy steps

```bash
git add <files>
git commit -m "description"
git push origin main
```

Coolify picks up the push automatically. Monitor the build in the Coolify dashboard.

### Post-deploy verification

```bash
curl https://carhero.eu/health             # {"status": "ok"}
curl https://carhero.eu/api/v1/health      # {"status": "ok"}
```

### Rollback

If a deploy breaks, revert the commit and push:
```bash
git revert HEAD
git push origin main
```

---

## 6. Scraper Management

### Providers

18 scrapers configured in `main.py`:
```
autoscout24, autotrader, autohero, mobile_de, theparking,
auto24_ee, auto24_lt, auto24_lv, blocket,
otomoto, coches, marktplaats, nettiauto, bilbasen,
donedeal, finn, standvirtual, autovit
```

### Nightly pipeline

The app runs a background daemon thread (when `DIGEST_ENABLED=1`) with a 4-step nightly pipeline:

1. **Scrape** all providers sequentially at `SCRAPE_HOUR` (default: 02:00 UTC, ~2-3h)
2. **Load** checkpoint JSONs into DB (new inserts + price updates with history)
3. **Cleanup** mark listings not refreshed in 7 days as `stale`
4. **Digest** send daily deals email to all opted-in users

The digest draws from freshly scraped data (last 36h by default via `DIGEST_FRESHNESS_HOURS`). If fewer than 1000 fresh listings exist, it falls back to the full catalog.

### Run scrapers manually

```bash
source .venv/bin/activate
python -m scripts.scrape_cars --provider autoscout24 --headless --limit 100
python -m scripts.scrape_cars --provider otomoto --headless --brand BMW
python -m scripts.scrape_cars --all --headless              # all providers
python -m scripts.scrape_cars --load --all                  # load checkpoints to DB only
```

### Run daily digest manually

```bash
python -m scripts.daily_deals --dry-run                     # preview HTML, don't send
python -m scripts.daily_deals --to julian@predictivelabs.co.uk  # send to one recipient
python -m scripts.daily_deals --all                         # send to all opted-in users
python -m scripts.daily_deals --deals 15 --drops 5          # custom counts
```

### Digest sections

| Section | Source | Shows when |
|---------|--------|------------|
| Price Drops | `price_history` + current price comparison | Prices decreased since last scrape |
| Best Price Arbitrage | Same make/model with spread across sources | Always (falls back to full catalog) |

The email uses **stacked cards** (not tables) for mobile-friendly rendering. Each comparison card shows cheapest/expensive prices side-by-side using inline-block divs that wrap naturally on narrow screens. No emojis in headings.

### Scraper best practices

- Use Firefox for bot bypass (Playwright Firefox, not Chromium)
- Add inter-brand delays to avoid rate limiting
- Use checkpoint patterns — scrapers save progress to JSON so they can resume
- Test scraper changes with `--limit 5` before full runs

---

## 7. Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DB_URL` | Yes | PostgreSQL connection string |
| `APP_SECRET` | Yes | Session signing / JWT fallback secret |
| `XAI_API_KEY` | Yes | xAI (Grok) API key for LLM agents |
| `XAI_BASE_URL` | No | xAI base URL override |
| `GROK_MODEL` | No | Grok model name override |
| `LLM_PROVIDER` | No | LLM provider selector |
| `EXA_API_KEY` | No | Exa search API key |
| `GOOGLE_CLIENT_ID` | Yes | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | Yes | Google OAuth client secret |
| `POSTMARK_API_TOKEN` | Yes | Postmark email API token |
| `FROM_EMAIL` | Yes | Sender email for digest/notifications |
| `FROM_NAME` | No | Sender display name |
| `TO_EMAIL` | No | Default recipient for contact form |
| `JWT_SECRET` | No | API JWT secret (falls back to APP_SECRET) |
| `LOGIN` | No | Enable/disable login feature |
| `PORT` | No | Server port (default: 5011) |
| `DIGEST_ENABLED` | No | Enable nightly scrape + digest pipeline (default: 1) |
| `SCRAPE_HOUR` | No | UTC hour to start nightly scrape (default: 2, digest follows after) |
| `DIGEST_FRESHNESS_HOURS` | No | Window for "fresh" data in digest (default: 36) |

**Security**: Never commit `.env` or secrets to git. `.env` is in `.gitignore`. All production secrets live in Coolify env vars.

---

## 8. Database

### Connection

PostgreSQL via SQLAlchemy. Connection string in `DB_URL` env var.

### Init

`init_db()` runs on app startup — creates tables if they don't exist.

### Manual access

```bash
source .venv/bin/activate
python -c "from db import engine; print(engine.url)"
```

---

## 9. Mobile API (FastAPI)

### Overview

Optional FastAPI layer mounted at `/api/v1`. Provides JWT-authenticated REST endpoints for the mobile app. The monolith works without it — if `fastapi` is not installed, the mount is skipped.

### Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/v1/health` | No | Health check |
| POST | `/api/v1/auth/register` | No | Register new user |
| POST | `/api/v1/auth/login` | No | Login, get JWT token |
| GET | `/api/v1/auth/me` | Yes | Current user info |
| GET | `/api/v1/agents` | No | List available agents |
| GET | `/api/v1/sessions` | Yes | List user's chat sessions |
| GET | `/api/v1/sessions/{id}` | Yes | Get session with messages |
| DELETE | `/api/v1/sessions/{id}` | Yes | Delete a session |
| POST | `/api/v1/sessions/{id}/share` | Yes | Generate share link |
| POST | `/api/v1/chat` | Yes | SSE streaming chat |
| GET | `/api/v1/favorites` | Yes | List favorites |
| POST | `/api/v1/favorites` | Yes | Add favorite |
| DELETE | `/api/v1/favorites/{id}` | Yes | Remove favorite |
| PATCH | `/api/v1/favorites/{id}/note` | Yes | Update favorite note |
| GET | `/api/v1/saved-searches` | Yes | List saved searches |
| POST | `/api/v1/saved-searches` | Yes | Create saved search |
| DELETE | `/api/v1/saved-searches/{id}` | Yes | Delete saved search |
| GET | `/api/v1/garage` | Yes | List garage cars |
| POST | `/api/v1/garage` | Yes | Add car to garage |
| DELETE | `/api/v1/garage/{id}` | Yes | Remove car from garage |
| GET | `/api/v1/garage/{id}/valuation` | Yes | Get car valuation |
| GET | `/api/v1/garage/{id}/tco` | Yes | Get TCO breakdown |
| GET | `/api/v1/profile` | Yes | Get user profile |
| PATCH | `/api/v1/profile` | Yes | Update profile |
| GET | `/api/v1/listings` | Opt | Search listings |
| POST | `/api/v1/analytics` | Yes | Run analytics query |
| POST | `/api/v1/contact` | No | Submit contact form |

### Swagger docs

Available at `/api/v1/docs` when the server is running. Static spec at `api/swagger.json`.

### JWT auth

- Token format: HMAC-SHA256, 72h expiry
- Header: `Authorization: Bearer <token>`
- Secret: `JWT_SECRET` env var (falls back to `APP_SECRET`)

### Standalone mode

For separate API deployment:
```bash
python api/app.py    # runs on port 5012
```

---

## 10. Daily Deals Digest — Testing & Monitoring

### How the digest works

The nightly pipeline (when `DIGEST_ENABLED=1`) runs at `SCRAPE_HOUR` (default 02:00 UTC):
1. Scrape all 18 providers (~2-3h)
2. Load checkpoint JSONs to DB (new inserts + price history)
3. Mark listings not seen in 7 days as `stale`
4. Send daily deals digest to all opted-in users

The digest has 2 sections drawing from fresh data (last 36h):
- **Price Drops**: listings with reduced prices vs previous scrape (from `price_history`)
- **Best Price Arbitrage**: same make/model with biggest spread across sources (stacked cards with cheapest/expensive side-by-side)

Falls back to full catalog when fresh data is sparse (< 1000 listings).
Emails sent from `info@carhero.chat` via Postmark, tagged `car-deals`.

### Credentials (`.secrets/`)

Credentials for testing digest delivery are in `.secrets/*.yaml` (gitignored):

| File | Contents |
|------|----------|
| `.secrets/ionos.yaml` | IONOS IMAP/SMTP login for `julian@predictivelabs.co.uk` |
| `.secrets/postmark.yaml` | Postmark sender configs for carhero, kanvas, liquidround |
| `.secrets/services.yaml` | Service URLs and digest schedules across all plai projects |

### Verify digest delivery via IMAP

Check if today's digest arrived at `julian@predictivelabs.co.uk`:

```python
import imaplib, yaml
from datetime import datetime

creds = yaml.safe_load(open('.secrets/ionos.yaml'))
acct = creds['accounts']['julian']

m = imaplib.IMAP4_SSL(creds['imap']['host'])
m.login(acct['email'], acct['password'])
m.select('INBOX')

today = datetime.now().strftime('%d-%b-%Y')
status, msgs = m.search(None, f'(SINCE {today} FROM "carhero")')
ids = msgs[0].split() if msgs[0] else []
print(f"CarHero emails today: {len(ids)}")

for mid in ids:
    _, data = m.fetch(mid, '(BODY[HEADER.FIELDS (FROM SUBJECT DATE)])')
    print(data[0][1].decode())

m.logout()
```

### Cross-project digest monitoring

All three plai projects use the same pattern (Postmark + background scheduler):

| Project | Sender | Default recipient | Digest hour |
|---------|--------|-------------------|-------------|
| CarHero | `info@carhero.chat` | `carhero@predictivelabs.co.uk` | 07:00 UTC |
| Kanvas | `info@kanvas.ai` | `kanvas@predictivelabs.co.uk` | 07:00 UTC |
| LiquidRound | `info@liquidround.com` | `liquidround@predictivelabs.co.uk` | 07:00 UTC |

Check all three at once:

```python
import imaplib, yaml
from datetime import datetime

creds = yaml.safe_load(open('.secrets/ionos.yaml'))
acct = creds['accounts']['julian']

m = imaplib.IMAP4_SSL(creds['imap']['host'])
m.login(acct['email'], acct['password'])
m.select('INBOX')

today = datetime.now().strftime('%d-%b-%Y')
for sender in ['carhero', 'kanvas', 'liquidround']:
    _, msgs = m.search(None, f'(SINCE {today} FROM "{sender}")')
    count = len(msgs[0].split()) if msgs[0] else 0
    status = "OK" if count > 0 else "MISSING"
    print(f"  {sender}: {count} emails [{status}]")

m.logout()
```

### Troubleshooting digest failures

1. **Check if scheduler is running**: Look for `[scheduler] Next scrape:` in server logs
2. **Check Postmark**: Login to Postmark dashboard, check Activity tab for bounces/errors
3. **Check DB has data**: Digest needs listings in DB — if scrapers failed, no deals to send
4. **Manual test send**:
   ```bash
   python -m scripts.daily_deals --to julian@predictivelabs.co.uk
   ```
5. **Dry run** (no email, just HTML output):
   ```bash
   python -m scripts.daily_deals --dry-run
   ```

### Digest content structure (all plai projects)

| Project | Section 1 | Section 2 | Section 3 | Section 4 |
|---------|-----------|-----------|-----------|-----------|
| CarHero | Price drops | Price arbitrage (stacked cards) | -- | -- |
| Kanvas | Bidding wars | Value finds | Market movers | Art news |
| LiquidRound | 10 companies (Tavily + LLM) | Investment theses | Featured deep dive | — |

CarHero's digest is freshness-driven (DB-only, no LLM, 36h window). Kanvas uses date-seeded shuffling for variety. LiquidRound uses Tavily + LLM to generate fresh research each day.

---

## 11. Mobile App (Flutter)

### Overview

Flutter mobile app at `../carhero-mobile/`. Replicates the CarHero web app for Android (iOS deferred). Connects to the same FastAPI backend at `/api/v1`.

### Tech stack

| Layer | Choice |
|-------|--------|
| Framework | Flutter 3.44+ / Dart 3.12+ |
| State management | Riverpod 3 |
| Routing | GoRouter 17 |
| HTTP | Dio (REST) + http (SSE streaming) |
| Charts | fl_chart |
| Auth | JWT Bearer + Google Sign-In v7 |
| i18n | Flutter Localizations (ARB, 12 languages) |
| CI/CD | GitHub Actions + Firebase App Distribution |

### GCP / Firebase setup

| Resource | Value |
|----------|-------|
| GCP Project | `carhero-mobile` (project number: 698790728504) |
| Firebase App ID | `1:698790728504:android:9dfa8be9906dacc8b9a7cd` |
| Package name | `chat.carhero.carhero` |
| Google OAuth Web Client ID | `76656799510-2996ug4uc4743ht74g4hsopn61g71ien.apps.googleusercontent.com` |
| Google OAuth Android Client ID | `76656799510-99q9f28jc0494atvgmjirppeuk2mfe8l.apps.googleusercontent.com` |
| OAuth project | `finespresso` (shared with web app) |
| Firebase service account | `firebase-app-dist@carhero-mobile.iam.gserviceaccount.com` |

### CI/CD pipeline

GitHub Actions (`.github/workflows/ci.yml`) on every push to `main`:
1. **Analyze** — `dart format --set-exit-if-changed` + `flutter analyze`
2. **Test** — `flutter test --coverage` (294 tests)
3. **Build** — `flutter build apk --release` + `flutter build appbundle --release`
4. **Distribute** — APK uploaded to Firebase App Distribution (testers group)

### GitHub secrets (carhero-mobile repo)

| Secret | Purpose |
|--------|---------|
| `FIREBASE_SERVICE_ACCOUNT` | Service account JSON for Firebase uploads |
| `FIREBASE_APP_ID` | `1:698790728504:android:9dfa8be9906dacc8b9a7cd` |
| `KEYSTORE_BASE64` | Base64-encoded release keystore (optional) |
| `KEY_ALIAS` | Keystore key alias |
| `KEY_PASSWORD` | Keystore key password |
| `STORE_PASSWORD` | Keystore store password |

### Install test builds

1. Install **Firebase App Tester** from Google Play Store
2. Sign in with Google account (must be in `testers` group)
3. Download latest build

### Build commands (local dev)

```bash
cd ../carhero-mobile
flutter pub get
dart run build_runner build --delete-conflicting-outputs
flutter run
flutter test
```

### Test → Fix → Redeploy workflow

1. **Test on device** — install via Firebase App Tester, check all screens
2. **Fix bugs locally** — edit Flutter code in `../carhero-mobile/`, backend in `api/app.py`
3. **Bump version** — increment `version:` in `../carhero-mobile/pubspec.yaml` (e.g. `1.0.1+2` → `1.0.2+3`). Format: `major.minor.patch+buildNumber`. Always increment both patch and buildNumber on each redeploy.
4. **Run tests** — `flutter test` (294 tests), verify `flutter analyze` passes
5. **Push backend** — `git push` in carhero repo triggers Coolify deploy via `.github/workflows/deploy.yml`
6. **Verify API** — `curl https://carhero.chat/api-status` should return `{"mounted": true}`
7. **Push Flutter** — `git push` in carhero-mobile triggers CI: analyze → test → build APK → Firebase App Distribution
8. **Verify CI** — `gh run list --repo predictivelabsai/carhero-mobile --limit 1`
9. **Test on device** — email arrives from Firebase, install updated APK, repeat from step 1

Backend deploy uses GitHub Actions + Coolify (secrets: `COOLIFY_TOKEN`, `COOLIFY_WEBHOOK_URL`). Flutter deploy uses GitHub Actions + Firebase App Distribution (secrets: `FIREBASE_SERVICE_ACCOUNT`, `FIREBASE_APP_ID`).

### Shared session endpoint

The API exposes `GET /shared/{token}` (public, no auth) for viewing shared chat sessions in the mobile app. Added to `api/app.py` alongside existing endpoints.
