# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Big picture
- The current product flow is: import account credentials -> run Codex OAuth login verification -> save OAuth tokens -> upload to Sub2Api. The old registration / Plus / Team flows still exist for compatibility, but the web console now centers on the login/upload flow.
- The top-level entrypoints ([server.py](server.py), [main.py](main.py), [codex_login_tool.py](codex_login_tool.py)) are thin wrappers around the modules under [app/](app/).

## Common commands
- Install or refresh dependencies: `pip install uv && uv sync`
- Run the web console: `uv run server.py`
- Run the web console on another port: `uv run server.py --port 5006`
- Select a different `activation_api.base_url` index: `uv run server.py --api 1`
- Run the batch login/upload entrypoint: `uv run main.py`
- Run the Codex login CLI: `uv run codex_login_tool.py --email ... --password ... --otp-mode auto`
- Run all tests: `uv run python -m unittest discover -s tests`
- Run one test module: `uv run python -m unittest tests.test_login_sub2api`
- Run one test method: `uv run python -m unittest tests.test_web_server_login_sub2api.WebServerLoginSub2ApiTests.test_login_endpoint_passes_otp_mode_and_upload_targets`
- Test files are mostly `unittest` modules. `tests/test_browser_container_compat.py` uses pytest-style fixtures, but pytest is not declared in the repo, so that file needs pytest installed locally if you want to run it directly.
- Build the container image: `docker compose build`
- Start the container stack: `docker compose up -d`
- Lint/format: no repo-defined tool is configured. For a quick syntax check, use `uv run python -m compileall app tests`.

## Architecture
- [app/web_server.py](app/web_server.py) is the Flask app and current UI/API surface. It serves [app/static/](app/static/), enforces the optional `web.admin_password` gate, keeps in-memory runtime state, handles the manual OTP broker, exposes `/api/*`, and starts under Waitress.
- [app/login_sub2api.py](app/login_sub2api.py) is the main orchestration layer for the current flow. It imports accounts, runs OAuth login, persists tokens, decides whether to upload to Sub2Api and/or Team management, and handles batch processing.
- [app/account_store.py](app/account_store.py) owns the SQLite schema, migration from the legacy TXT account file, derived state normalization, filtered queries, exports, and dashboard stats. The normalized account record shape here is the source of truth for the web UI and API payloads.
- [app/account_actions.py](app/account_actions.py) contains the legacy/manual account actions: status edits, deletion, delivery mail, Plus/Team retry paths, and Sub2Api re-upload helpers. It still depends on browser automation and Codex runtime helpers.
- [app/codex/](app/codex/) holds the OAuth and token/upload plumbing. `runtime.py` re-exports the CLI/auth/token helpers, `auth.py` handles the HTTP OAuth flow, `tokens.py` handles token persistence and Sub2Api upload, and `otp.py` handles mailbox-context OTP helpers.
- [app/email_service.py](app/email_service.py) dispatches between the worker provider and Outlook provider; [app/outlook_email_service.py](app/outlook_email_service.py) is the Outlook Mail Station integration.
- [app/browser/](app/browser/) is Selenium-based automation for the older browser-driven registration/activation paths that still support some compatibility flows.
- The front-end is a static single-page console in [app/static/index.html](app/static/index.html), [app/static/script.js](app/static/script.js), and [app/static/style.css](app/static/style.css). Its payload shapes come from `sanitize_account_record_for_web()` and the dashboard stats builders in `app.account_store`.
- Tests are standard-library `unittest` modules under [tests/](tests/), not pytest-based.

## Config and data
- Runtime config is read from `config.yaml` or `config.local.yaml` in the repo root, with `config.example.yaml` as the template. `app/config.py` auto-loads the file and can persist some automation toggles back into it.
- Persistent runtime data lives in `data/accounts.db`, `output_tokens/`, and the legacy `registered_accounts.txt`.
- `web.admin_password` enables the login gate on the console; leaving it empty disables the gate.
- `sub2api.base_url` should be the final `https://` endpoint to avoid POST redirects.
- Proxy settings only affect the Codex OAuth login chain; email service calls, Sub2Api upload, and Team management import stay direct.
- The docs worth checking for deployment and integration details are [docs/docker-deploy.md](docs/docker-deploy.md) and [docs/API_INTEGRATION.md](docs/API_INTEGRATION.md).

## Working notes
- Treat the web console as the live surface. The older registration / Plus / Team routes are mostly compatibility shims and some now short-circuit with disabled responses.
- If you change account-state fields or normalization logic, keep the Flask payloads and dashboard stats in sync with the record shape in `app/account_store.py`.
- When debugging UI/API behavior, remember the web server keeps in-memory log and frame state in `AppState`; tests in `tests/test_web_server_login_sub2api.py` and `tests/test_account_store_*.py` cover the current response contracts.
