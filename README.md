# Kids Wild Animal Stories — FREE media edition

This build removes fal.ai and all paid image/video API calls. It creates a Hindi story pack with Gemini, fetches animal photographs from Wikimedia Commons (no API key; each file has its own licence), turns them into vertical motion scenes with FFmpeg, adds Hindi gTTS narration, original synthesized boom-boom percussion, and a Like / Share / Follow / Next Part end card.

## Important limitation
This is a **free image-based animated Reel**, not text-to-video generation. Animal photos are animated with zoom/pan transitions. It will not create realistic moving 3D characters like the reference video. Wikimedia Commons results vary by animal and search availability. Review the `image_credits_file` in the job status and comply with each image's licence/attribution requirements before publishing.

## Railway deployment
1. Replace the old project files with the files in this ZIP and redeploy.
2. Keep `GEMINI_API_KEY` and `RUN_TOKEN` in Railway Variables. No `FAL_KEY`, fal.ai balance, or video API deposit is needed.
3. Set `OUTPUT_DIR=/data/insta-reels`. Attach a Railway Volume mounted at `/data` so generated videos and story packs persist across redeploys.
4. Ensure the Railway image has FFmpeg installed (the included Dockerfile installs it).
5. In `/docs`, authorize with your RUN_TOKEN and call `POST /run`.
6. Poll `GET /status/{job_id}` until `video_status` is `completed`, then open the returned `video_url`.
7. Configure Telegram using the steps below and test it with `POST /telegram/test`.

## Required variables
- `GEMINI_API_KEY`: Google AI Studio API key for story generation. Free-tier quota and model availability depend on Google's current account/project limits.
- `GEMINI_MODEL`: defaults to `gemini-2.5-flash`.
- `RUN_TOKEN`: private bearer token for `/run` and `/generate-video/{job_id}`.
- `OUTPUT_DIR`: recommended `/data/insta-reels`.
- `TELEGRAM_BOT_TOKEN`: token from Telegram's official `@BotFather` (keep private).
- `TELEGRAM_CHAT_ID`: your personal chat ID with the bot.
- `PUBLIC_BASE_URL`: optional Railway public URL, used to create clickable final-video links in Telegram.

## Telegram notifications
1. In Telegram, open `@BotFather`, create a bot with `/newbot`, and copy its token.
2. Open your new bot and press **Start** (the bot cannot message you until you start it).
3. Get your numeric chat ID using a trusted Telegram chat-ID bot/service, or call `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` after sending a message to your bot. Keep the token private; do not paste it into chat.
4. Add `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, and optionally `PUBLIC_BASE_URL` in Railway Variables, then redeploy.
5. In `/docs`, authorize with RUN_TOKEN and call `POST /telegram/test`. A successful response confirms delivery.

The app sends Telegram alerts when a Reel starts, completes, or fails. `POST /telegram/verification-needed` is an authenticated notification hook for a future Flow browser worker to alert you when it detects a verification step; this ZIP does not yet include Google Flow browser automation or detect CAPTCHA/login screens by itself.

## Costs
- fal.ai: removed; no calls are made.
- Wikimedia Commons: no API payment, but check individual image licences.
- gTTS: no API key; requires outbound internet.
- Gemini API and Railway hosting may still have quotas or charges. A Gemini app subscription does not automatically include API usage.

## Notes
- Scheduled GitHub Actions workflow targets three story packs per day; scheduled execution can be delayed.
- Instagram auto-publishing is not included.
- Keep API keys and RUN_TOKEN private. If exposed in a screenshot, rotate them.
