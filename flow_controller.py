"""Railway-hosted, user-authorized Google Flow browser controller.

This controls the visible Flow web UI only. It does not call private Google APIs,
solve CAPTCHAs, or bypass Google account verification.
"""
import os, re, threading, time
from pathlib import Path
from playwright.sync_api import sync_playwright

_LOCK = threading.RLock()
_STATE = {"running": False, "url": None, "title": None, "last_error": None, "verification_required": False}
_PLAY = None
_BROWSER = None
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


def _check_verification():
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


def start_browser():
    global _PLAY, _BROWSER, _CONTEXT, _PAGE
    with _LOCK:
        if _PAGE and not _PAGE.is_closed():
            return status()
        profile = Path(_env("FLOW_PROFILE_DIR", "/data/flow-profile"))
        profile.mkdir(parents=True, exist_ok=True)
        _PLAY = sync_playwright().start()
        # Headed Chromium runs inside Xvfb in the Railway container. Screenshots
        # and limited controls are exposed through authenticated app endpoints.
        _CONTEXT = _PLAY.chromium.launch_persistent_context(
            user_data_dir=str(profile), headless=False,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"],
            viewport={"width": 1365, "height": 900}, accept_downloads=True
        )
        _PAGE = _CONTEXT.pages[0] if _CONTEXT.pages else _CONTEXT.new_page()
        _PAGE.goto("https://flow.google.com/", wait_until="domcontentloaded", timeout=90000)
        _STATE.update({"running": True, "url": _PAGE.url, "title": _PAGE.title(), "last_error": None})
        _check_verification()
        return status()


def status():
    with _LOCK:
        if _PAGE and not _PAGE.is_closed():
            try:
                _STATE.update({"running": True, "url": _PAGE.url, "title": _PAGE.title()})
                _check_verification()
            except Exception as e:
                _STATE["last_error"] = str(e)[:500]
        else:
            _STATE["running"] = False
        return dict(_STATE)


def screenshot(path):
    with _LOCK:
        if not _PAGE or _PAGE.is_closed():
            raise RuntimeError("Flow browser is not running. Call POST /flow/start first.")
        _check_verification()
        _PAGE.screenshot(path=str(path), full_page=False)
        return str(path)


def click(x, y):
    with _LOCK:
        if not _PAGE or _PAGE.is_closed(): raise RuntimeError("Flow browser is not running.")
        _PAGE.mouse.click(int(x), int(y))
        time.sleep(1)
        _check_verification()
        return status()


def type_text(value):
    with _LOCK:
        if not _PAGE or _PAGE.is_closed(): raise RuntimeError("Flow browser is not running.")
        _PAGE.keyboard.type(value, delay=15)
        _check_verification()
        return status()


def press_key(key):
    with _LOCK:
        if not _PAGE or _PAGE.is_closed(): raise RuntimeError("Flow browser is not running.")
        _PAGE.keyboard.press(key)
        time.sleep(1)
        _check_verification()
        return status()


def fill_prompt(prompt):
    with _LOCK:
        if not _PAGE or _PAGE.is_closed(): raise RuntimeError("Flow browser is not running.")
        # Fill only an editable prompt field; user must review and press Generate.
        candidates = _PAGE.locator("textarea, [contenteditable='true'], input[type='text']")
        count = candidates.count()
        if count == 0:
            raise RuntimeError("Flow prompt box not found. Open a Flow project/create screen, then retry.")
        target = None
        for i in range(count - 1, -1, -1):
            el = candidates.nth(i)
            try:
                if el.is_visible() and el.is_enabled():
                    target = el
                    break
            except Exception:
                continue
        if target is None: raise RuntimeError("No visible editable prompt field found.")
        target.fill(prompt)
        _check_verification()
        return {**status(), "prompt_filled": True, "generation_submitted": False,
                "message": "Prompt filled. Review it in Flow and press Generate manually for this first integration test."}


def close_browser():
    global _PLAY, _BROWSER, _CONTEXT, _PAGE
    with _LOCK:
        try:
            if _CONTEXT: _CONTEXT.close()
            if _PLAY: _PLAY.stop()
        finally:
            _PLAY = _BROWSER = _CONTEXT = _PAGE = None
            _STATE.update({"running": False, "url": None, "title": None})
        return status()
