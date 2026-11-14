"""Railway-hosted, user-authorized Google Flow browser controller.

Uses Playwright's async API because FastAPI endpoints run on an asyncio loop.
Only the visible Google Flow website UI is controlled; no private APIs or
account-security bypasses are used.
"""
import os
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

_LOCK = asyncio.Lock()
_STATE = {"running": False, "url": None, "title": None, "last_error": None, "verification_required": False}
_PLAY = None
_CONTEXT = None
_PAGE = None


def _env(name, default=""):
    return os.getenv(name, default).strip()


def _telegram(message):
    token = _env("TELEGRAM_BOT_TOKEN")
    chat = _env("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return
    try:
        import requests
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      json={"chat_id": chat, "text": message}, timeout=12)
    except Exception:
        pass


async def _check_verification():
    global _PAGE
    if not _PAGE:
        return False
    try:
        body = (_PAGE.locator("body").inner_text(timeout=2500) or "").lower()
        title = (_PAGE.title() or "").lower()
        signals = ["verify it's you", "verify it’s you", "captcha", "2-step verification",
                   "two-step verification", "confirm it's you", "unusual traffic",
                   "verify your account", "account verification"]
        required = any(s in body or s in title for s in signals)
        if required and not _STATE.get("verification_required"):
            _STATE["verification_required"] = True
            _telegram("Google Flow ko Google account verification chahiye. Railway Flow browser mein manually verification complete karo; CAPTCHA bypass nahi kiya jayega.")
        elif not required:
            _STATE["verification_required"] = False
        return required
    except Exception:
        return False


async def start_browser():
    global _PLAY, _CONTEXT, _PAGE
    async with _LOCK:
        if _PAGE and not _PAGE.is_closed():
            return await _status_unlocked()
        profile = Path(_env("FLOW_PROFILE_DIR", "/data/flow-profile"))
        profile.mkdir(parents=True, exist_ok=True)

        # Wait for Xvfb to create its display socket before launching headed Chromium.
        display_socket = Path("/tmp/.X11-unix/X99")
        for _ in range(40):
            if display_socket.exists():
                break
            await asyncio.sleep(0.5)
        if not display_socket.exists():
            raise RuntimeError("Virtual display :99 is not ready. Check the Railway Xvfb service logs.")

        # Remove stale Chromium singleton markers left by an unclean container restart.
        for marker in ("SingletonLock", "SingletonSocket", "SingletonCookie"):
            try:
                (profile / marker).unlink(missing_ok=True)
            except OSError:
                pass

        _PLAY = await async_playwright().start()
        try:
            _CONTEXT = await _PLAY.chromium.launch_persistent_context(
                user_data_dir=str(profile),
                headless=False,
                timeout=120000,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--disable-blink-features=AutomationControlled",
                ],
                viewport={"width": 1365, "height": 900},
                accept_downloads=True,
            )
            _PAGE = _CONTEXT.pages[0] if _CONTEXT.pages else await _CONTEXT.new_page()
            await _PAGE.goto("https://flow.google.com/", wait_until="domcontentloaded", timeout=90000)
            _STATE.update({"running": True, "url": _PAGE.url, "title": await _PAGE.title(), "last_error": None})
            await _check_verification()
            return dict(_STATE)
        except Exception:
            if _CONTEXT:
                try:
                    await _CONTEXT.close()
                except Exception:
                    pass
            _CONTEXT = _PAGE = None
            if _PLAY:
                try:
                    await _PLAY.stop()
                except Exception:
                    pass
            _PLAY = None
            raise


async def _status_unlocked():
    if _PAGE and not _PAGE.is_closed():
        try:
            _STATE.update({"running": True, "url": _PAGE.url, "title": await _PAGE.title()})
            await _check_verification()
        except Exception as exc:
            _STATE["last_error"] = str(exc)[:500]
    else:
        _STATE["running"] = False
    return dict(_STATE)


async def status():
    async with _LOCK:
        return await _status_unlocked()


async def screenshot(path):
    async with _LOCK:
        if not _PAGE or _PAGE.is_closed():
            raise RuntimeError("Flow browser is not running. Call POST /flow/start first.")
        await _check_verification()
        await _PAGE.screenshot(path=str(path), full_page=False)
        return str(path)


async def click(x, y):
    async with _LOCK:
        if not _PAGE or _PAGE.is_closed():
            raise RuntimeError("Flow browser is not running.")
        await _PAGE.mouse.click(int(x), int(y))
        await asyncio.sleep(1)
        await _check_verification()
        return await _status_unlocked()


async def type_text(value):
    async with _LOCK:
        if not _PAGE or _PAGE.is_closed():
            raise RuntimeError("Flow browser is not running.")
        await _PAGE.keyboard.type(value, delay=15)
        await _check_verification()
        return await _status_unlocked()


async def press_key(key):
    async with _LOCK:
        if not _PAGE or _PAGE.is_closed():
            raise RuntimeError("Flow browser is not running.")
        await _PAGE.keyboard.press(key)
        await asyncio.sleep(1)
        await _check_verification()
        return await _status_unlocked()


async def fill_prompt(prompt):
    async with _LOCK:
        if not _PAGE or _PAGE.is_closed():
            raise RuntimeError("Flow browser is not running.")
        candidates = _PAGE.locator("textarea, [contenteditable='true'], input[type='text']")
        count = await candidates.count()
        if count == 0:
            raise RuntimeError("Flow prompt box not found. Open a Flow project/create screen, then retry.")
        target = None
        for i in range(count - 1, -1, -1):
            el = candidates.nth(i)
            try:
                if await el.is_visible() and await el.is_enabled():
                    target = el
                    break
            except Exception:
                continue
        if target is None:
            raise RuntimeError("No visible editable prompt field found.")
        await target.fill(prompt)
        await _check_verification()
        return {**(await _status_unlocked()), "prompt_filled": True,
                "generation_submitted": False,
                "message": "Prompt filled. Review it in Flow and press Generate manually for this first integration test."}


async def close_browser():
    global _PLAY, _CONTEXT, _PAGE
    async with _LOCK:
        try:
            if _CONTEXT:
                await _CONTEXT.close()
            if _PLAY:
                await _PLAY.stop()
        finally:
            _PLAY = _CONTEXT = _PAGE = None
            _STATE.update({"running": False, "url": None, "title": None})
        return dict(_STATE)
