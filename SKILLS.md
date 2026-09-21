# FastCPI development guide

## Architecture

FastHTML owns the landing, authenticated workspace and SSE chat. FastAPI is mounted at `/api/v1`.
Domain logic belongs in `pricing/`, scheduled watch execution in `monitoring/`, agent tools in
`tools/`, and shared Plotly builders in `charts.py`.

Preserve the CarHero-derived three-pane and SSE contracts:

```text
session → agent_route → token/tool events → artifact_show/chart → done
```

## Verification

Run `python -m compileall -q .`, focused pytest modules, then the complete suite. UI changes must be
checked at 1280×800 and 375×812. Confirm the evidence pane distinguishes Observed and Discovery
only results, inline charts render, and both side panes remain usable on mobile.

Always verify every changed or specifically reported view against the candidate commit on a local
server in a real browser before reporting it complete or deployed. A commit SHA, successful CI run,
healthy deployment, source inspection or API response is not proof that the rendered view is
complete. Exercise the requested interaction, check the browser console, and retain a local
screenshot or equivalent evidence. If a deployment was already reported but its view was not
locally verified, treat the work as unconfirmed: reproduce it locally, implement anything missing,
rerun the browser check and only then report completion (and redeploy if application code changed).

Live discovery and evals require `EXA_API_KEY` plus an LLM provider credential. Never commit `.env`,
OAuth secrets, API keys, page snapshots containing personal data or generated evaluation reports.

## Authentication and deployment

Signup is open through Google or verified email/password registration. OAuth uses authorization-code OIDC at `/auth/google` and
`/auth/google/callback`, requests only `openid email profile`, and validates state, issuer, audience
and verified email. Production callback: `https://cpi.fastsme.com/auth/google/callback`.

Push-to-main deployment is handled by the existing Coolify workflow. Before deploying, verify the
exact callback in Google Auth Platform, complete the local rendered-view verification above, sync
only named runtime variables, and smoke-test TLS, `/health`, login, chat, source links and
`/api/v1/docs`.
