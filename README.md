# Kids Wild Animal Stories — Railway + Flow Browser Controller

This build adds a **user-authorized Chromium controller** for the Google Flow website. It uses the visible website UI only; it does not call private Google endpoints, bypass CAPTCHA, or automate account-security challenges.

## Railway setup

1. Replace the repository contents with this ZIP and deploy using the included Dockerfile.
2. Attach a Railway Volume to the `Automation` service and set its mount path to `/data`.
3. Set Railway Variables:
   - `RUN_TOKEN` — your existing API bearer token (keep it secret)
   - `GEMINI_API_KEY` — existing Gemini key
   - `FLOW_AUTOMATION_ENABLED=true`
   - `FLOW_PROFILE_DIR=/data/flow-profile`
   - `OUTPUT_DIR=/data/insta-reels`
   - `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` — optional; verification alerts are sent if configured
4. Redeploy and open `/docs`.

## First login

All `/flow/*` endpoints require `Authorization: Bearer <RUN_TOKEN>`.

1. `POST /flow/start` — starts Chromium in the Railway container and opens `https://flow.google.com/`.
2. `GET /flow/screenshot` — view the current browser screen. If Google login is shown, use `/flow/click`, `/flow/type`, and `/flow/press` to interact with the visible page. Never send your password, cookies, or one-time codes to anyone; enter them only into Google's page.
3. If Google requests CAPTCHA, 2-step verification, or account confirmation, complete it yourself in the visible browser UI. The controller attempts to detect verification screens and sends a Telegram alert when configured. Detection is best-effort; check `/flow/screenshot` too.
4. `GET /flow/status` — check browser status.

## Prompt workflow (initial integration stage)

Open a Flow project/create screen yourself, then call `POST /flow/fill-prompt` with `{ "prompt": "..." }`. It fills a visible editable prompt field but deliberately does **not** press Generate. Review the prompt and click Generate yourself for the first test. Flow's UI changes frequently, so generation submission and automatic clip download are not claimed as implemented until verified against the current UI.

## Security and limitations

- The browser profile is stored in `/data/flow-profile`; keep the Railway Volume private and do not expose its files.
- Protect `RUN_TOKEN`; do not publish it or include it in screenshots.
- Do not use this controller to bypass CAPTCHA, 2-step verification, rate limits, or other account protections.
- Google Flow does not provide a supported public API for using Flow credits from Railway. This is browser UI automation and may break if Google changes the interface or restricts automated use.
- A Railway cloud browser is not a normal interactive desktop. Screenshot + authenticated click/type endpoints provide limited remote interaction, not a full live desktop. Google may still require manual intervention and some login flows may not work in a hosted browser.
- The existing free Wikimedia + FFmpeg Reel renderer remains available. This first browser integration does not yet automatically download Flow clips or replace the free renderer.


## Private mobile browser link (noVNC)

This upgrade exposes the Railway Chromium desktop through noVNC behind HTTP Basic Authentication.
It is intended for manual Google login and verification only; do not share the link or credentials.

Add these Railway Variables:
- `PUBLIC_BASE_URL=https://YOUR-RAILWAY-DOMAIN`
- `BROWSER_ACCESS_USER=flow` (or your own username)
- `BROWSER_ACCESS_PASSWORD` — create a long, unique password
- Keep `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` configured
- Keep `FLOW_AUTOMATION_ENABLED=true` and `FLOW_PROFILE_DIR=/data/flow-profile`

After deploy, call authenticated `POST /flow/start`. The app starts Chromium and sends the private browser URL to your Telegram chat. Open the link on your phone; the browser asks for the Basic Auth username/password, then shows the remote desktop. Sign into Google yourself. Never send Google passwords, OTPs, cookies, or session files through Telegram.

The noVNC page and WebSocket are protected by HTTP Basic Auth. Keep the password private and rotate it if exposed. The browser is still subject to Google's normal verification and product restrictions. This does not create a supported Google Flow API and does not guarantee automated video generation/download; it only provides a private remote desktop for the user-authorized browser.


## Troubleshooting note (VNC HTTP 500)

The startup script sets `/etc/nginx/.htpasswd` to `root:www-data` with mode `0640`,
so Debian Nginx workers can read the Basic Auth hash. Nginx access and error logs
are sent to Railway stdout/stderr. Use the public domain mapped to port 8080 for
`/vnc/vnc.html`; port 5900 is the raw VNC service and is not the browser URL.
