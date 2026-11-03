# Browser API docs

Browser API docs is the static HTML page at `GET /docs`. An operator reads the health example and can follow the OpenAPI link without a separate frontend.

## Sub-features

- `docs-open` serves `text/html` with title and `h1` `Bedtime Lights API Docs`.
- `docs-health-section` shows `h2` `GET /health` and the JSON example in `pre`.
- `docs-openapi-link` exposes `a[href="/openapi.json"]` with link text `/openapi.json`.

## How to get to it (user POV)

- Open `$base_url/docs` in a browser.
- Request `GET /docs` with HTTP and read the HTML.
- Follow the `/openapi.json` link on that page, or request that same URL with HTTP.

## Driving it with verify-bedtime

Preconditions:

- Doctor reports `ok: true` for this run's instance.
- The helper found a Chrome binary using the lookup in `SKILL.md`.

- **Browser open.** Load the docs page as a user would. Run `./.venv/bin/python .cursor/skills/verify-bedtime/scripts/verify_bedtime.py drive --feature docs`. Chrome loads `$base_url/docs`. `html.parser` on `docs.dom.html` finds `h1` text `Bedtime Lights API Docs`. `docs.screenshot.png` is visual evidence for the runner to inspect.
- **Health section.** Confirm the health heading and example. The same parser result must include `h2` text `GET /health` and `pre` text `{"service": "bedtime", "status": "ok"}`. Those strings come from `bedtime_lights/health.py`.
- **OpenAPI link.** Confirm the machine-readable link. The same parser result must include `a[href="/openapi.json"]` with text `/openapi.json`. The helper does not click it. `GET $base_url/openapi.json` is the resolved target.
- **HTTP twin.** Keep `docs.response.txt` from the same drive. Status `200`, content type `text/html`, same parser checks as the DOM dump.
- **Proof.** `docs.screenshot.png` plus `docs.ui.txt`. The runner inspects the screenshot. A curl body without a browser load does not finish this feature.

## Gotchas

- The page is static HTML. There is no Swagger UI and no `unpkg.com` script. Wait for the `h1`, not a network idle from a CDN.
- Use the parsed `h1`, `h2`, href, and `pre` body. Do not click by coordinates.
- If Chrome is missing, finish the HTTP half, write the blocker, and leave `docs.screenshot.blocked.txt` with the helper's lookup command. Lookup order is `/opt/google/chrome/google-chrome`, `/usr/bin/google-chrome-stable`, `/usr/bin/chromium-browser`, `/usr/bin/chromium`, then `PATH` for `chromium` and `chromium-browser`. A PATH `google-chrome` wrapper that forces `--remote-debugging-port` is skipped because it can write the PNG and then hang.

```bash
/opt/google/chrome/google-chrome --headless --disable-gpu --no-sandbox --disable-dev-shm-usage --hide-scrollbars --window-size=1280,900 --screenshot=docs.screenshot.png "$base_url/docs"
/opt/google/chrome/google-chrome --headless --disable-gpu --no-sandbox --disable-dev-shm-usage --dump-dom "$base_url/docs"
```

- Following `/openapi.json` in a real browser leaves `/docs`. Re-open `/docs` before proving the heading again.
