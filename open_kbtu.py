import os
import sys
import json
import asyncio
import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from dotenv import load_dotenv
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
import aiohttp

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
REFRESH_INTERVAL = 35
LOGIN_URL = "https://wsp.kbtu.kz/RegistrationOnline"
RETRY_DELAY = 30
LOGIN_MAX_ATTEMPTS = 3


class LoginFailed(Exception):
    """Raised when all login attempts are exhausted for a user."""

BASE_DIR = Path(__file__).parent
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)


def setup_logging():
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(name)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    root.addHandler(console)

    file_handler = RotatingFileHandler(
        LOG_DIR / "autoscraper.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)


def load_users() -> list[dict]:
    with open(BASE_DIR / "users.json", "r") as f:
        return json.load(f)


async def send_telegram(chat_id: str, message: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not chat_id:
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                data={"chat_id": chat_id, "text": message},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                return resp.status == 200
    except Exception as e:
        logging.warning("Telegram send failed: %s", e)
        return False


async def do_login(page, username: str, password: str, log: logging.Logger):
    log.info("Navigating to login page...")
    await page.goto(LOGIN_URL, wait_until="networkidle", timeout=30_000)

    log.info("Filling credentials...")
    username_input = page.locator("input.v-filterselect-input").first
    await username_input.wait_for(state="visible", timeout=15_000)
    await username_input.fill(username)
    await page.wait_for_timeout(500)

    password_input = page.locator("input[type='password']").first
    await password_input.fill(password)

    login_btn = page.locator("div.v-button.primary").first
    await login_btn.click()
    await page.wait_for_timeout(5000)

    buttons = await page.locator("span.v-button-caption").all_text_contents()
    if any(b in buttons for b in ("Кіру", "Войти", "Login")):
        log.warning("Login may have failed — login button still visible")
        return False

    log.info("Login successful")
    return True


async def login_with_retries(page, username: str, password: str, chat_id: str, log: logging.Logger):
    """Try to login up to LOGIN_MAX_ATTEMPTS times. Raises LoginFailed if all fail."""
    for attempt in range(1, LOGIN_MAX_ATTEMPTS + 1):
        try:
            success = await do_login(page, username, password, log)
            if success:
                return
        except Exception as e:
            log.warning("Login attempt %d/%d error: %s", attempt, LOGIN_MAX_ATTEMPTS, e)
            success = False

        if attempt < LOGIN_MAX_ATTEMPTS:
            log.info("Login failed, retrying (%d/%d)...", attempt, LOGIN_MAX_ATTEMPTS)
            await asyncio.sleep(5)

    msg = f"[{username}] Login failed after {LOGIN_MAX_ATTEMPTS} attempts. Check your credentials. Stopping."
    log.error(msg)
    await send_telegram(chat_id, msg)
    raise LoginFailed(msg)


async def is_session_expired(page) -> bool:
    try:
        buttons = await page.locator("span.v-button-caption").all_text_contents()
        if any(b in buttons for b in ("Кіру", "Войти", "Login")):
            return True
        return await page.locator("input[type='password']").count() > 0
    except Exception:
        return False


async def run_for_user(user: dict, browser):
    username = user["username"]
    password = user["password"]
    chat_id = user.get("telegram_chat_id")
    log = logging.getLogger(username)

    context = await browser.new_context(
        viewport={"width": 1920, "height": 1080},
        ignore_https_errors=True,
    )
    page = await context.new_page()

    try:
        await login_with_retries(page, username, password, chat_id, log)

        refresh_count = 0
        while True:
            refresh_count += 1
            log.info("Refresh #%d", refresh_count)

            try:
                await page.goto(LOGIN_URL, wait_until="networkidle", timeout=30_000)
            except PlaywrightTimeout:
                log.warning("Page load timed out, will retry next cycle")
                await asyncio.sleep(REFRESH_INTERVAL)
                continue

            await page.wait_for_timeout(2000)

            if await is_session_expired(page):
                log.info("Session expired, re-logging in...")
                await login_with_retries(page, username, password, chat_id, log)
                await page.wait_for_timeout(3000)

            try:
                btn_locator = page.locator(
                    "div.v-button",
                    has=page.locator("span.v-button-caption", has_text="Отметиться"),
                ).first
                await btn_locator.wait_for(state="visible", timeout=5000)
                await btn_locator.click()
                log.info("CLICKED 'Отметиться'!")
                await send_telegram(
                    chat_id,
                    f"[{username}] ATTENDANCE MARKED at {datetime.now():%H:%M:%S}",
                )
                await page.wait_for_timeout(2000)
            except PlaywrightTimeout:
                visible = [
                    b
                    for b in await page.locator("span.v-button-caption").all_text_contents()
                    if b.strip()
                ]
                log.info("'Отметиться' not found. Buttons: %s", visible)

            await asyncio.sleep(REFRESH_INTERVAL)

    except asyncio.CancelledError:
        log.info("Task cancelled")
    except Exception as e:
        log.exception("Error: %s", e)
        await send_telegram(chat_id, f"[{username}] SCRAPER ERROR: {e}")
        raise
    finally:
        await context.close()


async def run_user_forever(user: dict, browser):
    """Never gives up — restarts with increasing delay on failure, then resets on success."""
    username = user["username"]
    chat_id = user.get("telegram_chat_id")
    log = logging.getLogger(username)
    attempt = 0

    while True:
        attempt += 1
        try:
            await run_for_user(user, browser)
            attempt = 0
        except asyncio.CancelledError:
            break
        except LoginFailed:
            log.info("Stopped due to login failure")
            break
        except Exception as e:
            delay = min(RETRY_DELAY * attempt, 300)
            log.error("Attempt #%d crashed: %s. Restarting in %ds...", attempt, e, delay)
            await send_telegram(
                chat_id,
                f"[{username}] Crashed (attempt #{attempt}): {e}\nRestarting in {delay}s...",
            )
            await asyncio.sleep(delay)


async def main():
    setup_logging()
    users = load_users()
    logging.info("Loaded %d user(s) from users.json", len(users))

    while True:
        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
                )
                logging.info("Browser launched")

                tasks = [
                    asyncio.create_task(run_user_forever(user, browser))
                    for user in users
                ]

                try:
                    await asyncio.gather(*tasks)
                except KeyboardInterrupt:
                    logging.info("Stopping...")
                    for t in tasks:
                        t.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
                    return
                finally:
                    await browser.close()

        except KeyboardInterrupt:
            logging.info("Stopped by user")
            return
        except Exception as e:
            logging.exception("Browser crashed: %s. Restarting in 30s...", e)
            await asyncio.sleep(30)


if __name__ == "__main__":
    asyncio.run(main())
