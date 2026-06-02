from __future__ import annotations

import asyncio
from datetime import datetime
import hashlib
import json
import os
import random
import re
from pathlib import Path
from urllib.parse import parse_qs, unquote, urljoin, urlparse

from apify import Actor, Request
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from .decision_makers import DECISION_MAKER_KEYWORDS


VIEWPORTS = [
    {"width": 1280, "height": 720, "device_scale_factor": 1},
    {"width": 1366, "height": 768, "device_scale_factor": 1},
    {"width": 1440, "height": 900, "device_scale_factor": 1},
    {"width": 1536, "height": 864, "device_scale_factor": 1},
    {"width": 1920, "height": 1080, "device_scale_factor": 1},
]

FINGERPRINTS = [
    {
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "platform": "Win32",
        "timezone_id": "America/New_York",
        "locale": "en-US",
        "languages": ["en-US", "en"],
        "webgl_vendor": "Google Inc. (Intel)",
        "webgl_renderer": "ANGLE (Intel, Intel(R) UHD Graphics 620 Direct3D11, D3D11)",
        "hardware_concurrency": 8,
        "device_memory": 8,
    },
    {
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        ),
        "platform": "Win32",
        "timezone_id": "America/Chicago",
        "locale": "en-US",
        "languages": ["en-US", "en"],
        "webgl_vendor": "Google Inc. (NVIDIA)",
        "webgl_renderer": "ANGLE (NVIDIA, NVIDIA GeForce GTX 1650 Direct3D11, D3D11)",
        "hardware_concurrency": 12,
        "device_memory": 8,
    },
    {
        "user_agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "platform": "MacIntel",
        "timezone_id": "America/Los_Angeles",
        "locale": "en-US",
        "languages": ["en-US", "en"],
        "webgl_vendor": "Google Inc. (Apple)",
        "webgl_renderer": "ANGLE (Apple, Apple M1 Pro, OpenGL 4.1)",
        "hardware_concurrency": 10,
        "device_memory": 8,
    },
]

DEFAULT_COMPANY_URL = "https://in.linkedin.com/company/techforceglobal"
STORAGE_STATE_KEY = "LINKEDIN_STORAGE_STATE"
STORAGE_STATE_KEY_PREFIX = "LINKEDIN_STORAGE_STATE_"

# URL patterns that indicate LinkedIn is blocking / not logged in
AUTHWALL_PATTERNS = [
    "/authwall",
    "/checkpoint/",
    "/login",
    "/registration",
    "/uas/login",
    "linkedin.com/signup",
]

EXTERNAL_LOGIN_HOSTS = [
    "login.microsoftonline.com",
    "login.live.com",
    "account.microsoft.com",
    "office.com",
    "outlook.live.com",
]


DEFAULT_MIN_PROFILE_DELAY_SECONDS = 4.0
DEFAULT_MAX_PROFILE_DELAY_SECONDS = 9.0
DEFAULT_MANUAL_VERIFICATION_TIMEOUT_SECONDS = 600


def load_dotenv() -> None:
    for candidate in [Path(".env"), Path(__file__).resolve().parents[1] / ".env"]:
        if not candidate.exists():
            continue
        for raw_line in candidate.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def build_fingerprint(seed: str) -> dict:
    digest = hashlib.sha256(seed.encode()).hexdigest()
    base = dict(FINGERPRINTS[int(digest[:2], 16) % len(FINGERPRINTS)])
    viewport = dict(VIEWPORTS[int(digest[2:4], 16) % len(VIEWPORTS)])
    base["viewport"] = viewport
    base["screen"] = {"width": viewport["width"], "height": viewport["height"]}
    base["device_scale_factor"] = viewport["device_scale_factor"]
    return base


def sanitize_proxy_session_id(value: str, *, max_length: int = 50) -> str:
    cleaned = re.sub(r"[^\w._~]+", "_", value.strip().lower())
    cleaned = re.sub(r"_+", "_", cleaned).strip("._") or "li_session"
    digest = hashlib.sha1(value.encode()).hexdigest()[:8]
    prefix = cleaned[: max(1, max_length - len(digest) - 1)].rstrip("._")
    return f"{prefix}_{digest}"


def storage_state_key(session_id: str) -> str:
    return f"{STORAGE_STATE_KEY_PREFIX}{sanitize_proxy_session_id(session_id, max_length=60)}"


def proxy_to_playwright(proxy_info):
    if not proxy_info:
        return None
    return {"server": proxy_info.url, "username": proxy_info.username, "password": proxy_info.password}


def is_authwall_url(url: str) -> bool:
    """Return True if the current URL is a login/authwall/registration page."""
    return any(pattern in url for pattern in AUTHWALL_PATTERNS)


def is_security_challenge_url(url: str) -> bool:
    parsed = urlparse(str(url))
    return "/checkpoint/challenge" in parsed.path


def is_linkedin_url(url: str) -> bool:
    host = urlparse(str(url)).netloc.lower()
    return host == "linkedin.com" or host.endswith(".linkedin.com")


def is_external_login_url(url: str) -> bool:
    host = urlparse(str(url)).netloc.lower()
    return any(host == item or host.endswith(f".{item}") for item in EXTERNAL_LOGIN_HOSTS)


async def recover_from_external_login(page, target_url: str, fingerprint: dict) -> bool:
    if not is_external_login_url(page.url):
        return False
    Actor.log.warning(f"External login page detected after LinkedIn login: {page.url}")
    if not target_url:
        return True
    Actor.log.info(f"Returning to LinkedIn target page instead of external login: {target_url}")
    await page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
    await human_settle(page, fingerprint, 2.0, 3.5)
    return True


async def page_has_security_challenge(page) -> bool:
    if is_security_challenge_url(page.url):
        return True
    try:
        body_text = (await page.locator("body").inner_text(timeout=4000)).lower()
    except Exception:
        body_text = ""
    return any(
        token in body_text
        for token in ["security verification", "quick security check", "enter the code", "captcha"]
    )


async def wait_for_manual_security_verification(
    page,
    target_url: str,
    fingerprint: dict,
    timeout_seconds: int,
) -> bool:
    if timeout_seconds <= 0:
        return False

    Actor.log.warning(
        "LinkedIn requested security verification. "
        f"Complete it in the open browser within {timeout_seconds} seconds."
    )
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    last_log_at = 0.0

    while asyncio.get_running_loop().time() < deadline:
        if page.is_closed():
            return False
        current_url = page.url
        if is_linkedin_url(current_url) and not is_authwall_url(current_url):
            if target_url and not is_people_results_url(current_url):
                Actor.log.info(f"Verification completed; opening target page: {target_url}")
                await page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
                await human_settle(page, fingerprint, 2.0, 3.5)
            return not is_authwall_url(page.url)

        now = asyncio.get_running_loop().time()
        if now - last_log_at >= 30:
            remaining = int(deadline - now)
            Actor.log.info(f"Waiting for manual LinkedIn verification; {remaining} seconds remaining. Current URL: {current_url}")
            last_log_at = now
        await asyncio.sleep(3)

    return False


def is_people_results_url(url: str) -> bool:
    parsed = urlparse(url)
    return (
        "/people" in parsed.path
        or ("/search/results/people" in parsed.path and "facetCurrentCompany" in parsed.query)
    )


def session_redirect_target(url: str) -> str | None:
    parsed = urlparse(url)
    redirect = parse_qs(parsed.query).get("session_redirect", [None])[0]
    if not redirect:
        return None
    target = unquote(redirect)
    if target.startswith("/"):
        return urljoin("https://www.linkedin.com", target)
    if target.startswith("https://www.linkedin.com/"):
        return target
    return None


async def human_delay(min_s: float = 1.0, max_s: float = 2.5) -> None:
    await asyncio.sleep(random.uniform(min_s, max_s))


async def human_mouse_wander(page, fingerprint: dict) -> None:
    vp = fingerprint["viewport"]
    try:
        for _ in range(random.randint(3, 6)):
            if page.is_closed():
                return
            await page.mouse.move(
                random.randint(40, max(80, vp["width"] - 80)),
                random.randint(60, max(100, vp["height"] - 80)),
                steps=random.randint(10, 25),
            )
            await asyncio.sleep(random.uniform(0.08, 0.25))
    except Exception as exc:
        Actor.log.debug(f"Mouse wander skipped: {exc}")


async def random_scroll(page, *, rounds_min: int = 2, rounds_max: int = 5) -> None:
    try:
        for index in range(random.randint(rounds_min, rounds_max)):
            if page.is_closed():
                return
            distance = random.randint(260, 720)
            if index and random.random() < 0.2:
                distance = -random.randint(80, 240)
            await page.mouse.wheel(0, distance)
            await asyncio.sleep(random.uniform(0.45, 1.25))
    except Exception as exc:
        Actor.log.debug(f"Scroll skipped: {exc}")


async def human_settle(page, fingerprint: dict, min_s: float = 0.8, max_s: float = 1.8) -> None:
    await human_delay(min_s, max_s)
    if random.random() < 0.85:
        await human_mouse_wander(page, fingerprint)
    if random.random() < 0.65:
        await random_scroll(page)


async def type_like_human(page, selector: str, text: str) -> None:
    parts = [item.strip() for item in selector.split(",") if item.strip()]
    field = None

    for part in parts:
        try:
            locator = page.locator(part)
            await locator.first.wait_for(state="attached", timeout=15000)
            count = await locator.count()
            for index in range(count):
                candidate = locator.nth(index)
                if await candidate.is_visible(timeout=1000) and await candidate.is_enabled(timeout=1000):
                    field = candidate
                    break
            if field is not None:
                break
        except Exception:
            continue

    if field is None:
        raise RuntimeError(f"Could not find visible input field for selector: {selector}")

    try:
        await field.scroll_into_view_if_needed(timeout=5000)
        await field.click(timeout=5000)
        await human_delay(0.3, 0.7)
        await page.keyboard.press("Control+A")
        await asyncio.sleep(random.uniform(0.05, 0.15))
        await page.keyboard.press("Delete")
        await human_delay(0.2, 0.5)
        for char in text:
            await field.type(char, delay=random.randint(55, 175))
    except Exception as exc:
        Actor.log.warning(f"Normal typing failed for '{selector}', using DOM fill: {exc}")
        await field.evaluate(
            """(input, value) => {
                input.focus();
                input.value = value;
                input.dispatchEvent(new Event('input', { bubbles: true }));
                input.dispatchEvent(new Event('change', { bubbles: true }));
            }""",
            text,
        )
    await human_delay(0.4, 0.9)


def stealth_init_script(fingerprint: dict) -> str:
    return f"""
(() => {{
  const fp = {json.dumps(fingerprint)};
  const def = (obj, prop, val) => {{
    try {{ Object.defineProperty(obj, prop, {{ get: () => val, configurable: true }}); }} catch(e) {{}}
  }};
  def(Navigator.prototype, 'webdriver', undefined);
  def(Navigator.prototype, 'platform', fp.platform);
  def(Navigator.prototype, 'languages', fp.languages);
  def(Navigator.prototype, 'hardwareConcurrency', fp.hardware_concurrency);
  def(Navigator.prototype, 'deviceMemory', fp.device_memory);
  def(Navigator.prototype, 'plugins', [1,2,3,4,5]);
  def(Navigator.prototype, 'mimeTypes', [1,2,3]);
  window.chrome = window.chrome || {{}};
  window.chrome.runtime = window.chrome.runtime || {{}};
  const origQuery = window.navigator.permissions && window.navigator.permissions.query;
  if (origQuery) {{
    window.navigator.permissions.query = (p) =>
      p && p.name === 'notifications'
        ? Promise.resolve({{ state: Notification.permission }})
        : origQuery.call(window.navigator.permissions, p);
  }}
  const gp = WebGLRenderingContext.prototype.getParameter;
  WebGLRenderingContext.prototype.getParameter = function(p) {{
    if (p === 37445) return fp.webgl_vendor;
    if (p === 37446) return fp.webgl_renderer;
    return gp.call(this, p);
  }};
  if (window.WebGL2RenderingContext) {{
    const gp2 = WebGL2RenderingContext.prototype.getParameter;
    WebGL2RenderingContext.prototype.getParameter = function(p) {{
      if (p === 37445) return fp.webgl_vendor;
      if (p === 37446) return fp.webgl_renderer;
      return gp2.call(this, p);
    }};
  }}
  def(screen, 'width', fp.screen.width);
  def(screen, 'height', fp.screen.height);
  def(screen, 'availWidth', fp.screen.width);
  def(screen, 'availHeight', fp.screen.height - 40);
}})();
"""


async def launch_browser(playwright, *, headless: bool, proxy_info=None):
    args = [
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
        "--disable-blink-features=AutomationControlled",
        "--window-size=1366,768",
    ]
    opts = {"headless": headless, "args": args}
    proxy = proxy_to_playwright(proxy_info)
    if proxy:
        opts["proxy"] = proxy
    try:
        Actor.log.info(f"Launching installed Google Chrome headless={headless}")
        return await playwright.chromium.launch(channel="chrome", **opts)
    except Exception as exc:
        Actor.log.warning(f"Chrome channel failed, using bundled Chromium: {exc}")
        return await playwright.chromium.launch(**opts)


async def make_context(browser, fingerprint: dict, storage_state=None):
    opts = {
        "viewport": {"width": fingerprint["viewport"]["width"], "height": fingerprint["viewport"]["height"]},
        "screen": fingerprint["screen"],
        "user_agent": fingerprint["user_agent"],
        "locale": fingerprint["locale"],
        "timezone_id": fingerprint["timezone_id"],
        "color_scheme": "light",
        "java_script_enabled": True,
        "accept_downloads": False,
        "extra_http_headers": {
            "Accept-Language": ",".join(fingerprint["languages"]),
            "DNT": "1",
        },
    }
    if storage_state:
        opts["storage_state"] = storage_state
    context = await browser.new_context(**opts)
    await context.add_init_script(stealth_init_script(fingerprint))
    return context


async def close_login_popup(page) -> None:
    selector = "button.modal__dismiss svg"
    try:
        button = page.locator(selector).first
        if await button.count() and await button.is_visible(timeout=1200):
            await button.click()
            await human_delay(0.6, 1.2)
            return
    except Exception:
        Actor.log.info("close button didnt clicked")


async def click_first_visible(page, selectors: list[str], timeout_ms: int = 2500) -> bool:
    external_auth_words = re.compile(r"\b(microsoft|google|apple|sso|single sign-on|single sign on)\b", re.IGNORECASE)
    for selector in selectors:
        try:
            locator = page.locator(selector)
            count = await locator.count()
            for index in range(min(count, 10)):
                candidate = locator.nth(index)
                if not await candidate.is_visible(timeout=timeout_ms):
                    continue
                if not await candidate.is_enabled(timeout=timeout_ms):
                    continue
                try:
                    candidate_text = await candidate.inner_text(timeout=800)
                except Exception:
                    candidate_text = ""
                try:
                    candidate_href = await candidate.get_attribute("href") or ""
                except Exception:
                    candidate_href = ""
                if external_auth_words.search(f"{candidate_text} {candidate_href}"):
                    Actor.log.info(f"Skipping external auth control while clicking '{selector}': {candidate_text}")
                    continue
                box = await candidate.bounding_box()
                if box:
                    await page.mouse.move(
                        box["x"] + box["width"] / 2 + random.uniform(-5, 5),
                        box["y"] + box["height"] / 2 + random.uniform(-3, 3),
                        steps=random.randint(8, 18),
                    )
                    await human_delay(0.2, 0.5)
                await candidate.click()
                await human_delay(1.0, 2.0)
                return True
        except Exception:
            continue
    return False


def candidate_company_urls(base_url: str) -> list[str]:
    parsed = urlparse(base_url)
    slug = parsed.path.rstrip("/").split("/")[-1] or "techforceglobal"
    candidates = [base_url.rstrip("/")]
    slug_candidates = [
        slug,
        slug.replace("-", ""),
        re.sub(r"global$", "-global", slug),
        "techforceglobal",
        "techforce-global",
        "techforce-glboal",
    ]
    for item in slug_candidates:
        if not item:
            continue
        candidates.append(f"https://in.linkedin.com/company/{item}")
        candidates.append(f"https://www.linkedin.com/company/{item}")
    return list(dict.fromkeys(candidates))


async def page_is_unavailable(page) -> bool:
    text = ""
    title = ""
    try:
        title = (await page.title()).lower()
        text = (await page.locator("body").inner_text(timeout=5000)).lower()
    except Exception:
        pass
    signatures = [
        "page not found",
        "this page doesn't exist",
        "this page does not exist",
        "this page is unavailable",
        "profile not found",
        "404",
        "This LinkedIn Page isn't available",
    ]
    return any(signature in title or signature in text for signature in signatures)


async def resolve_company_url(page, base_url: str, fingerprint: dict) -> str:
    for url in candidate_company_urls(base_url):
        Actor.log.info(f"Trying company URL: {url}")
        try:
            response = await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await human_settle(page, fingerprint, 1.2, 2.6)
            await close_login_popup(page)
            if response and response.status >= 400:
                if is_authwall_url(page.url):
                    Actor.log.info(f"Company URL redirected to login wall despite HTTP {response.status}: {page.url}")
                    return page.url
                Actor.log.warning(f"Company URL returned HTTP {response.status}: {url}")
                continue
            if await page_is_unavailable(page):
                Actor.log.warning(f"Company page unavailable: {url}")
                continue
            return page.url
        except Exception as exc:
            Actor.log.warning(f"Company URL failed {url}: {exc}")
    raise RuntimeError("Could not find an available LinkedIn company page.")


async def go_to_people_page(page, company_url: str, fingerprint: dict) -> None:
    await close_login_popup(page)
    clicked = await click_first_visible(
        page,
        [
            "a[href*='/people/']:has-text('See all')",
            "a[href*='/people/']:has-text('employees')",
            "a:has-text('See all employees')",
            "a:has-text('See all')",
        ],
    )
    if not clicked:
        people_url = urljoin(company_url.rstrip("/") + "/", "people/")
        Actor.log.info(f"Opening people URL directly: {people_url}")
        await page.goto(people_url, wait_until="domcontentloaded", timeout=60000)
    await human_settle(page, fingerprint, 1.5, 3.0)


async def ensure_logged_in(
    page,
    email: str,
    password: str,
    fingerprint: dict,
    target_url: str,
    manual_verification_timeout_seconds: int,
) -> None:
    """
    FIX 1: After login LinkedIn often redirects to /authwall, /checkpoint, or /registration.
    This function detects that and re-navigates to the intended target_url after login.
    """
    current_url = page.url
    if not is_authwall_url(current_url):
        Actor.log.info(f"Already on a valid page: {current_url}")
        return

    Actor.log.info(f"Detected redirect to wall page: {current_url}. Performing login.")
    await login_if_needed(
        page,
        email,
        password,
        fingerprint,
        target_url=target_url,
        manual_verification_timeout_seconds=manual_verification_timeout_seconds,
    )

    # After login, LinkedIn may land on feed or another page — re-navigate to where we wanted
    post_login_url = page.url
    Actor.log.info(f"Post-login URL: {post_login_url}")

    if await recover_from_external_login(page, target_url, fingerprint):
        post_login_url = page.url
        Actor.log.info(f"Post-external-login recovery URL: {post_login_url}")

    if is_authwall_url(post_login_url):
        raise RuntimeError(
            f"Still on wall page after login attempt: {post_login_url}. "
            "Credentials may be wrong or a CAPTCHA was triggered."
        )

    # Re-navigate to the intended target only if LinkedIn did not already land
    # on an equivalent company people search page.
    if target_url and (not is_linkedin_url(post_login_url) or (target_url not in post_login_url and not is_people_results_url(post_login_url))):
        Actor.log.info(f"Re-navigating to intended target after login: {target_url}")
        await page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
        await human_settle(page, fingerprint, 2.0, 3.5)

    # Final check
    final_url = page.url
    if await recover_from_external_login(page, target_url, fingerprint):
        final_url = page.url
    if is_authwall_url(final_url):
        raise RuntimeError(f"Redirected to wall page even after re-navigation: {final_url}")
    if not is_linkedin_url(final_url):
        raise RuntimeError(f"LinkedIn login navigated to an external page: {final_url}")

    Actor.log.info(f"Successfully on target page: {final_url}")


async def login_if_needed(
    page,
    email: str,
    password: str,
    fingerprint: dict,
    target_url: str = "",
    manual_verification_timeout_seconds: int = DEFAULT_MANUAL_VERIFICATION_TIMEOUT_SECONDS,
) -> None:
    if not email or not password:
        raise RuntimeError(
            "LinkedIn credentials are required. "
            "Add LINKEDIN_EMAIL and LINKEDIN_PASSWORD to .env or Actor input."
        )

    login_start_url = page.url
    redirect_target = session_redirect_target(login_start_url)
    await close_login_popup(page)
    user_selector = (
        "input[type='email'], "
        "input#username, "
        "input[name='session_key'], "
        "input[name='email-or-phone'], "
        "input[autocomplete*='username']"
    )
    pass_selector = (
        "input[type='password'], "
        "input#password, "
        "input[name='session_password'], "
        "input[name='password'], "
        "input[autocomplete='current-password']"
    )

    sign_in_clicked = await click_first_visible(
        page,
        [
            "a[href*='/login']:has-text('Sign in')",
            "a[href*='/uas/login']",
        ],
        timeout_ms=2500,
    )
    if sign_in_clicked:
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=30000)
        except PlaywrightTimeoutError:
            pass
        await human_settle(page, fingerprint, 1.0, 2.2)
        redirect_target = redirect_target or session_redirect_target(page.url)

    Actor.log.info("Signing in to LinkedIn.")
    await type_like_human(page, user_selector, email)
    await type_like_human(page, pass_selector, password)
    submit_clicked = await click_first_visible(
        page,
        [
            "button[type='submit']",
            "button:has-text('Sign in')",
            "input[type='submit']",
            "button[aria-label*='Sign in']",
            "button:has-text('Agree & Join')",
        ],
        timeout_ms=5000,
    )
    if not submit_clicked:
        Actor.log.warning("Could not click the LinkedIn submit button; submitting with Enter.")
        await page.keyboard.press("Enter")
        await human_delay(1.0, 2.0)

    try:
        await page.wait_for_url(lambda url: is_linkedin_url(str(url)) and not is_authwall_url(str(url)), timeout=60000)
    except PlaywrightTimeoutError:
        Actor.log.warning(f"Login did not reach a valid LinkedIn URL within timeout: {page.url}")

    await recover_from_external_login(page, target_url or redirect_target or login_start_url, fingerprint)

    try:
        await page.wait_for_load_state("domcontentloaded", timeout=30000)
    except PlaywrightTimeoutError:
        pass
    await human_settle(page, fingerprint, 3.0, 5.5)

    body_text = ""
    try:
        body_text = (await page.locator("body").inner_text(timeout=4000)).lower()
    except Exception:
        pass
    if await page_has_security_challenge(page):
        if await wait_for_manual_security_verification(
            page,
            target_url or redirect_target or login_start_url,
            fingerprint,
            manual_verification_timeout_seconds,
        ):
            return
        raise RuntimeError(
            "LinkedIn requested security verification and it was not completed before the timeout. "
            "On Apify, run with headless=false, open the browser/live view, complete the LinkedIn challenge, "
            "then rerun with the same session_id so the saved login state can be reused."
        )
    if is_authwall_url(page.url):
        if any(token in body_text for token in ["wrong", "incorrect", "try again", "invalid"]):
            raise RuntimeError("LinkedIn rejected the login credentials.")
        try:
            password_visible = await page.locator(pass_selector).first.is_visible(timeout=1500)
        except Exception:
            password_visible = False
        if password_visible:
            raise RuntimeError(
                f"LinkedIn login form is still visible after submit: {page.url}. "
                "Complete any account prompt in the headful browser, then rerun."
            )

    if await recover_from_external_login(page, target_url or redirect_target or login_start_url, fingerprint):
        return

    if redirect_target and is_linkedin_url(redirect_target) and not is_authwall_url(page.url) and not is_people_results_url(page.url):
        Actor.log.info(f"Following LinkedIn session_redirect after login: {redirect_target}")
        await page.goto(redirect_target, wait_until="domcontentloaded", timeout=60000)
        await human_settle(page, fingerprint, 1.5, 3.0)


async def save_storage_state(context, key: str) -> None:
    try:
        await Actor.set_value(key, await context.storage_state())
    except Exception as exc:
        Actor.log.warning(f"Could not save LinkedIn storage state: {exc}")


# ---------------------------------------------------------------------------
# FIX 2: Python-native employee extraction (replaces page.evaluate JS blob)
# ---------------------------------------------------------------------------

def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _lower_words(text: str) -> str:
    return re.sub(r"[^a-z0-9+#]+", " ", (text or "").lower()).strip()


def matched_decision_keywords(text: str) -> list[str]:
    haystack = f" {_lower_words(text)} "
    matches: list[str] = []
    seen_keys: set[str] = set()
    for keyword in DECISION_MAKER_KEYWORDS:
        needle = f" {_lower_words(keyword)} "
        normalized_keyword = _lower_words(keyword)
        if needle in haystack and normalized_keyword not in seen_keys:
            matches.append(keyword)
            seen_keys.add(normalized_keyword)
    return matches


def is_likely_decision_maker(headline: str) -> bool:
    return bool(matched_decision_keywords(headline))


def normalize_role_title(title: str) -> str:
    value = _clean(title)
    lowered = _lower_words(value)
    if not value:
        return ""
    if "chief technology officer" in lowered or re.search(r"\bcto\b", lowered):
        return "CTO"
    if "chief executive officer" in lowered or re.search(r"\bceo\b", lowered):
        return "CEO"
    if "chief operating officer" in lowered or re.search(r"\bcoo\b", lowered):
        return "COO"
    if "chief financial officer" in lowered or re.search(r"\bcfo\b", lowered):
        return "CFO"
    if "co founder" in lowered and "cto" in lowered:
        return "CTO"
    if "founder" in lowered and "ceo" in lowered:
        return "CEO"
    if "vice president" in lowered:
        return re.sub(r"\b[Vv]ice [Pp]resident\b", "VP", value)
    if re.search(r"\bvp\b", lowered):
        return value
    if "head of technology" in lowered or "head technology" in lowered:
        return "Head of Engineering"
    if "engineering manager" in lowered:
        return "Engineering Manager"
    if "product manager" in lowered:
        return "Product Manager"
    if "team leader" in lowered:
        return "Team Lead"
    if "project leader" in lowered:
        return "Project Lead"
    if "technical lead" in lowered or "tech lead" in lowered:
        return "Tech Lead"
    return value


def classify_department(title: str) -> str:
    text = _lower_words(title)
    if any(word in text for word in ["engineer", "engineering", "technology", "technical", "tech", "cto", "architect", "developer", "software", "scrum"]):
        return "Engineering"
    if "product" in text:
        return "Product"
    if any(word in text for word in ["hr", "human resources", "recruit", "talent", "people"]):
        return "HR"
    if any(word in text for word in ["sales", "business development", "revenue", "account executive"]):
        return "Sales"
    if "marketing" in text or "growth" in text:
        return "Marketing"
    if any(word in text for word in ["operations", "ops", "delivery", "project"]):
        return "Operations"
    return "Business"


def classify_seniority(title: str) -> str:
    text = _lower_words(title)
    if "founder" in text or "owner" in text or "partner" in text:
        return "Founder"
    if re.search(r"\b(ceo|cto|coo|cfo|chief|president)\b", text):
        return "C-Level"
    if "vice president" in text or re.search(r"\bvp\b", text):
        return "VP"
    if "director" in text:
        return "Director"
    if "manager" in text or "recruiter lead" in text:
        return "Manager"
    if any(word in text for word in ["talent acquisition", "recruitment strategy", "hr operations", "workforce development"]):
        return "Manager"
    if "lead" in text or "leader" in text or "head" in text:
        return "Lead"
    return "Individual Contributor"


def classify_decision_maker_type(title: str, department: str, seniority: str) -> str:
    text = _lower_words(title)
    if department == "Engineering" or any(word in text for word in ["cto", "architect", "technology", "technical", "tech"]):
        return "Technical"
    if department == "Product":
        return "Product"
    if department == "HR" or any(word in text for word in ["recruit", "talent", "hiring"]):
        return "Hiring"
    if seniority in {"Founder", "C-Level", "VP", "Director"}:
        return "Business"
    return ""


def priority_score(title: str, matched_keywords: list[str]) -> int:
    text = _lower_words(title)
    score = 0
    if "founder" in text or re.search(r"\bceo\b|chief executive officer", text):
        score = 98
    elif re.search(r"\bcto\b|chief technology officer", text):
        score = 94
    elif re.search(r"\b(coo|cfo|chief|president)\b|chief operating officer|chief financial officer", text):
        score = 90
    elif "vice president" in text or re.search(r"\bvp\b", text):
        score = 86
    elif "director" in text:
        score = 82
    elif "head" in text:
        score = 78
    elif "manager" in text:
        score = 70
    elif "lead" in text or "leader" in text or "principal" in text or "architect" in text:
        score = 66
    elif any(word in text for word in ["talent acquisition", "recruitment strategy", "hr operations", "workforce development"]):
        score = 68
    elif any(keyword in {"hr", "human resources", "talent", "recruiter", "recruitment", "talent acquisition"} for keyword in matched_keywords):
        score = 64
    elif matched_keywords:
        score = 55
    elif any(word in text for word in ["engineer", "developer"]):
        score = 25
    return max(0, min(100, score))


def classify_role(title: str, *, headline_matches: list[str] | None = None) -> dict:
    normalized = normalize_role_title(title)
    matched = matched_decision_keywords(f"{title} {normalized}")
    for keyword in headline_matches or []:
        if keyword not in matched:
            matched.append(keyword)
    department = classify_department(normalized or title)
    seniority = classify_seniority(normalized or title)
    score = priority_score(normalized or title, matched)
    is_decision_maker = score >= 60 or seniority in {"Founder", "C-Level", "VP", "Director"}
    return {
        "title": _clean(title),
        "normalized_title": normalized,
        "department": department,
        "seniority_level": seniority,
        "is_decision_maker": is_decision_maker,
        "decision_maker_type": classify_decision_maker_type(normalized or title, department, seniority),
        "priority_score": score,
        "matched_keywords": matched,
        "confidence_score": 0,
    }


def parse_years_from_text(text: str) -> float | None:
    if not text:
        return None
    total_months = sum(
        int(match.group(1)) * 12 for match in re.finditer(r"\b(\d+)\s*yrs?\b", text, flags=re.IGNORECASE)
    )
    total_months += sum(
        int(match.group(1)) for match in re.finditer(r"\b(\d+)\s*mos?\b", text, flags=re.IGNORECASE)
    )
    if not total_months:
        return None
    return round(total_months / 12, 1)


def company_name_from_url(company_url: str) -> str:
    slug = urlparse(company_url).path.rstrip("/").split("/")[-1]
    return " ".join(part.capitalize() for part in re.split(r"[-_]+", slug) if part)


def company_tokens(company_name: str) -> set[str]:
    ignored = {
        "global",
        "technologies",
        "technology",
        "tech",
        "inc",
        "ltd",
        "limited",
        "pvt",
        "private",
        "llc",
        "llp",
        "solutions",
        "services",
    }
    return {
        token
        for token in re.findall(r"[a-z0-9]+", _lower_words(company_name))
        if len(token) > 2 and token not in ignored
    }


def company_names_match(expected: str, found: str) -> bool:
    expected_clean = _lower_words(expected)
    found_clean = _lower_words(found)
    if not expected_clean or not found_clean:
        return False
    if expected_clean in found_clean or found_clean in expected_clean:
        return True
    expected_tokens = company_tokens(expected)
    found_tokens = company_tokens(found)
    return bool(expected_tokens and found_tokens and expected_tokens.intersection(found_tokens))


def experience_details_url(profile_url: str) -> str:
    parsed = urlparse(profile_url)
    path = parsed.path.rstrip("/")
    if not path.endswith("/details/experience"):
        path = f"{path}/details/experience"
    return parsed._replace(path=path + "/", query="", fragment="").geturl()


def build_output_item(
    item: dict,
    *,
    company_name: str,
    company_url: str,
    role_title: str,
    role_info: dict,
    current_company_years: float | None,
    total_years: float | None,
    about_available: bool,
    scraped_at: str,
) -> dict:
    return {
        "name": item.get("name", ""),
        "linkedin_url": item.get("url", ""),
        "location": item.get("location", ""),
        "company": {
            "name": company_name,
            "linkedin_url": company_url,
        },
        "current_role": {
            "title": role_title,
            "normalized_title": role_info["normalized_title"],
            "department": role_info["department"],
            "seniority_level": role_info["seniority_level"],
            "is_decision_maker": role_info["is_decision_maker"],
            "decision_maker_type": role_info["decision_maker_type"],
            "priority_score": role_info["priority_score"],
            "matched_keywords": role_info["matched_keywords"],
            "confidence_score": role_info["confidence_score"],
        },
        "experience": {
            "total_years": total_years,
            "current_company_years": current_company_years,
        },
        "profile_data": {
            "headline": item.get("role") or item.get("designation") or "",
            "about_available": about_available,
        },
        "scraping_metadata": {
            "page_number": item.get("page_number", 0),
            "position_on_page": item.get("position_on_page", 0),
            "scraped_at": scraped_at,
            "profile_enriched": bool(item.get("profile_enriched")),
            "keyword_match_debug": item.get("headline_matches", []),
        },
    }


def _strip_noise(line: str, name: str) -> str:
    """Remove connection-degree noise, the person's own name, and 'Verified' badges."""
    value = _clean(line).replace("Verified", "").strip()
    # Remove leading name
    escaped = re.escape(name)
    value = re.sub(rf"^{escaped}\s*[•\u2022]\s*\d+(st|nd|rd|th)\+?", "", value, flags=re.IGNORECASE).strip()
    # Remove leading bullet + degree
    value = re.sub(r"^\s*[•\u2022â€¢]\s*\d+(st|nd|rd|th)\+?\s*", "", value, flags=re.IGNORECASE).strip()
    # Remove bare leading degree (e.g. "2nd+")
    value = re.sub(rf"^{escaped}\s*\?\s*\d+(st|nd|rd|th)\+?", "", value, flags=re.IGNORECASE).strip()
    value = re.sub(r"^\s*\?\s*\d+(st|nd|rd|th)\+?\s*", "", value, flags=re.IGNORECASE).strip()
    value = re.sub(r"^\d+(st|nd|rd|th)\+?\s*", "", value, flags=re.IGNORECASE).strip()
    return _clean(value)


_NOISE_WORDS = re.compile(
    r"\b(connect|message|follow|invite|verified|status is offline|view profile)\b",
    re.IGNORECASE,
)
_INVITE_PATTERN = re.compile(r"^invite .* to connect$", re.IGNORECASE)
_PROFILE_URL_RE = re.compile(r"linkedin\.com/in/", re.IGNORECASE)


async def extract_employees_legacy(page, company_url: str) -> list[dict]:
    """
    FIX 2: Pure Python/Playwright extraction — no page.evaluate JS blob.

    Strategy:
      1. Find all <a href*="/in/"> anchors in the page.
      2. Walk up to find the card container (has >= 2 text lines).
      3. Extract name from the anchor text or nearby img[alt].
      4. Extract designation and location from sibling <p> tags.
    """
    results: list[dict] = []
    seen_urls: set[str] = set()

    # Grab all profile anchors
    anchors = page.locator('a[href*="/in/"]')
    count = await anchors.count()
    Actor.log.debug(f"Found {count} profile anchors on page.")

    for i in range(count):
        anchor = anchors.nth(i)

        try:
            href = await anchor.get_attribute("href") or ""
        except Exception:
            continue

        # Filter out non-profile or unwanted links
        if "/in/" not in href:
            continue
        if any(bad in href for bad in ["/learning/", "/sales/"]):
            continue

        # Normalise URL — strip query params
        try:
            profile_url = re.sub(r"\?.*$", "", urljoin("https://www.linkedin.com", href))
        except Exception:
            continue

        if profile_url in seen_urls:
            continue

        # --- Extract name ---
        name = ""
        try:
            # Prefer direct text nodes of the anchor
            anchor_text = _clean(await anchor.inner_text())
            name = re.sub(r"\s*[•\u2022]\s*\d+(st|nd|rd|th)\+?.*$", "", anchor_text, flags=re.IGNORECASE).strip()
        except Exception:
            pass

        if not name:
            # Fallback: aria-hidden span inside anchor
            try:
                span = anchor.locator('span[aria-hidden="true"]').first
                if await span.count():
                    name = _clean(await span.inner_text())
            except Exception:
                pass

        if not name:
            # Fallback: img alt inside card area
            try:
                img = anchor.locator("xpath=ancestor::li//img[@alt]").first
                if not await img.count():
                    img = anchor.locator("xpath=ancestor::div//img[@alt]").first
                if await img.count():
                    alt = await img.get_attribute("alt") or ""
                    name = re.sub(r"^View\s+", "", _clean(alt))
            except Exception:
                pass

        if not name:
            continue
        if re.search(r"status is offline|^connect$|^message$|^follow$", name, re.IGNORECASE):
            continue

        # --- Find card container: walk up until we have >= 2 <p> tags ---
        designation = ""
        location = ""

        # Try paragraph siblings first (most reliable)
        try:
            # The name anchor is usually inside a <p>; sibling <p> tags hold designation/location
            name_p = anchor.locator("xpath=ancestor::p[1]").first
            if await name_p.count():
                parent = name_p.locator("xpath=..").first
                if await parent.count():
                    paras = parent.locator("p")
                    para_count = await paras.count()
                    info_lines: list[str] = []
                    for j in range(para_count):
                        para = paras.nth(j)
                        # Skip the name paragraph itself
                        para_text = _clean(await para.inner_text())
                        if para_text == name:
                            continue
                        cleaned = _strip_noise(para_text, name)
                        if not cleaned:
                            continue
                        if re.fullmatch(r"(connect|message|follow)", cleaned, re.IGNORECASE):
                            continue
                        if _INVITE_PATTERN.match(cleaned):
                            continue
                        if _NOISE_WORDS.search(cleaned):
                            continue
                        if len(cleaned) > 220:
                            continue
                        if cleaned not in info_lines:
                            info_lines.append(cleaned)
                    if info_lines:
                        designation = info_lines[0]
                    if len(info_lines) > 1:
                        location = info_lines[1]
        except Exception as exc:
            Actor.log.debug(f"Paragraph extraction failed for {profile_url}: {exc}")

        # Fallback: use card inner text lines if designation still empty
        if not designation:
            try:
                # Walk up max 10 levels to find a card-like container
                card_locator = anchor.locator(
                    "xpath=ancestor::li[1] | ancestor::*[contains(@class,'org-people-profile-card')][1] "
                    "| ancestor::*[contains(@class,'reusable-search__result-container')][1]"
                ).first
                if not await card_locator.count():
                    # generic fallback: 3 levels up
                    card_locator = anchor.locator("xpath=ancestor::div[3]").first

                if await card_locator.count():
                    card_text = _clean(await card_locator.inner_text())
                    lines = [l for l in card_text.split("\n") if _clean(l)]
                    info_lines = []
                    for raw_line in lines:
                        line = _strip_noise(raw_line, name)
                        if not line or line == name:
                            continue
                        if re.fullmatch(r"(connect|message|follow)", line, re.IGNORECASE):
                            continue
                        if _INVITE_PATTERN.match(line):
                            continue
                        if _NOISE_WORDS.search(line):
                            continue
                        if len(line) > 220:
                            continue
                        if line not in info_lines:
                            info_lines.append(line)
                    if info_lines:
                        designation = info_lines[0]
                    if len(info_lines) > 1:
                        location = info_lines[1]
            except Exception as exc:
                Actor.log.debug(f"Card fallback extraction failed for {profile_url}: {exc}")

        # Skip cards with literally no info at all
        if not designation and not location:
            continue

        seen_urls.add(profile_url)
        results.append(
            {
                "name": name,
                "designation": designation,
                "location": location,
                "url": profile_url,
                "company_url": company_url,
            }
        )

    Actor.log.debug(f"Extracted {len(results)} employees from current page.")
    return results


async def extract_employees(page, company_url: str) -> list[dict]:
    """Extract one employee per card to keep name/profile/role/location paired."""
    results: list[dict] = []
    seen_urls: set[str] = set()

    anchors = page.locator('a[href*="/in/"]')
    count = await anchors.count()
    Actor.log.debug(f"Found {count} profile anchors on page.")

    for index in range(count):
        anchor = anchors.nth(index)
        try:
            data = await anchor.evaluate(
                """
(anchor) => {
  const card = anchor.closest(
    'li.reusable-search__result-container, .entity-result, .org-people-profile-card, li'
  ) || anchor.closest('div') || anchor;
  const links = Array.from(card.querySelectorAll('a[href*="/in/"]'))
    .map((link) => ({
      href: link.href || link.getAttribute('href') || '',
      text: (link.innerText || '').replace(/\\s+/g, ' ').trim(),
      aria: link.getAttribute('aria-label') || '',
    }))
    .filter((link) => link.href.includes('/in/'));
  const names = Array.from(card.querySelectorAll('span[aria-hidden="true"], img[alt]'))
    .map((node) => node.getAttribute('alt') || node.innerText || '')
    .map((text) => text.replace(/\\s+/g, ' ').trim())
    .filter(Boolean);
  const lines = (card.innerText || '')
    .split(/\\n+/)
    .map((line) => line.replace(/\\s+/g, ' ').trim())
    .filter(Boolean);
  return { links, names, lines };
}
"""
            )
        except Exception as exc:
            Actor.log.debug(f"Card snapshot failed: {exc}")
            continue

        links = data.get("links") or []
        if not links:
            continue

        raw_href = links[0].get("href") or ""
        if any(bad in raw_href for bad in ["/learning/", "/sales/"]):
            continue
        profile_url = re.sub(r"\?.*$", "", urljoin("https://www.linkedin.com", raw_href))
        if profile_url in seen_urls:
            continue

        lines = [_clean(line) for line in data.get("lines", []) if _clean(line)]
        name_candidates: list[str] = []
        for link in links:
            name_candidates.extend([link.get("text") or "", link.get("aria") or ""])
        name_candidates.extend(data.get("names") or [])
        name_candidates.extend(lines[:3])

        name = ""
        for candidate in name_candidates:
            candidate = re.sub(r"^View\s+", "", _clean(candidate), flags=re.IGNORECASE)
            candidate = re.sub(r"\s+profile$", "", candidate, flags=re.IGNORECASE)
            candidate = re.sub(r"\s*[â€¢\u2022?]\s*\d+(st|nd|rd|th)\+?.*$", "", candidate, flags=re.IGNORECASE)
            if not candidate or len(candidate) > 80:
                continue
            if _NOISE_WORDS.search(candidate):
                continue
            name = candidate
            break

        if not name or re.search(r"status is offline|^connect$|^message$|^follow$", name, re.IGNORECASE):
            continue

        info_lines: list[str] = []
        for raw_line in lines:
            line = _strip_noise(raw_line, name)
            if not line or line == name:
                continue
            if re.fullmatch(r"(connect|message|follow)", line, re.IGNORECASE):
                continue
            if _INVITE_PATTERN.match(line):
                continue
            if _NOISE_WORDS.search(line):
                continue
            if len(line) > 220:
                continue
            if line not in info_lines:
                info_lines.append(line)

        designation = info_lines[0] if info_lines else ""
        location = info_lines[1] if len(info_lines) > 1 else ""
        if not designation and not location:
            continue

        seen_urls.add(profile_url)
        results.append(
            {
                "name": name,
                "role": designation,
                "designation": designation,
                "location": location,
                "url": profile_url,
                "company_url": company_url,
            }
        )

    Actor.log.debug(f"Extracted {len(results)} employees from current page.")
    return results


async def page_extract_debug(page) -> dict:
    try:
        return await page.evaluate(
            """
() => ({
  url: location.href,
  title: document.title,
  profile_links: document.querySelectorAll('a[href*="/in/"]').length,
  people_cards: document.querySelectorAll('li, .org-people-profile-card, .reusable-search__result-container').length,
  body_sample: (document.body?.innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 450)
})
"""
        )
    except Exception as exc:
        return {"error": str(exc), "url": page.url}


async def click_next_page(page) -> bool:
    current_url = page.url
    first_profile_url = ""
    try:
        first_profile_url = await page.locator('a[href*="/in/"]').first.get_attribute("href") or ""
    except Exception:
        pass

    clicked = await click_first_visible(
        page,
        [
            "button[aria-label='Next']:not([disabled])",
            "button[aria-label*='Next']:not([disabled])",
            ".artdeco-pagination__button--next:not([disabled])",
            "li.artdeco-pagination__indicator--number.active + li button:not([disabled])",
        ],
        timeout_ms=2000,
    )
    if not clicked:
        return False

    try:
        await page.wait_for_function(
            """
({ previousUrl, previousProfileUrl }) => {
  const firstProfile = document.querySelector('a[href*="/in/"]')?.href || '';
  return location.href !== previousUrl || firstProfile !== previousProfileUrl;
}
""",
            arg={"previousUrl": current_url, "previousProfileUrl": first_profile_url},
            timeout=15000,
        )
    except PlaywrightTimeoutError:
        Actor.log.warning("Next button clicked, but pagination content did not change.")
        return False
    return True


async def retry_async(action, *, attempts: int = 3, base_delay: float = 1.5, label: str = "operation"):
    last_exc = None
    for attempt in range(1, attempts + 1):
        try:
            return await action()
        except Exception as exc:
            last_exc = exc
            if attempt >= attempts:
                break
            sleep_for = base_delay * attempt + random.uniform(0.4, 1.4)
            Actor.log.warning(f"{label} failed on attempt {attempt}/{attempts}: {exc}. Retrying in {sleep_for:.1f}s.")
            await asyncio.sleep(sleep_for)
    raise last_exc


async def extract_company_name(page, company_url: str) -> str:
    for selector in ["h1", ".org-top-card-summary__title", "main h1"]:
        try:
            text = _clean(await page.locator(selector).first.inner_text(timeout=2500))
            if text and len(text) <= 120:
                return text
        except Exception:
            continue
    try:
        title = _clean(await page.title())
        title = re.sub(r"\s*\|\s*LinkedIn.*$", "", title, flags=re.IGNORECASE)
        if title:
            return title
    except Exception:
        pass
    return company_name_from_url(company_url)


def choose_current_experience(experiences: list[dict], company_name: str) -> dict:
    current_items = []
    for exp in experiences:
        full_text = _lower_words(" ".join(str(value) for value in exp.values()))
        found_company = exp.get("company") or full_text
        is_current = "present" in full_text or "current" in full_text
        company_matches = company_names_match(company_name, found_company)
        if is_current and company_matches:
            return exp
        if is_current:
            current_items.append(exp)
    if current_items:
        return current_items[0]
    return experiences[0] if experiences else {}


def infer_title_from_experience(exp: dict, fallback: str) -> str:
    title = _clean(exp.get("title") or "")
    if title and not re.search(r"\bpresent\b|\b\d+\s*(yrs?|mos?)\b", title, re.IGNORECASE):
        return title
    lines = [_clean(line) for line in exp.get("lines", []) if _clean(line)]
    noise = re.compile(r"\b(experience|present|yrs?|mos?|followers?|connections?)\b", re.IGNORECASE)
    for line in lines[:8]:
        if line == exp.get("company"):
            continue
        if len(line) > 120 or noise.search(line):
            continue
        return line
    return fallback


async def read_experience_snapshot(profile_page) -> dict:
    return await profile_page.evaluate(
        """
() => {
  const clean = (value) => (value || '').replace(/\\s+/g, ' ').trim();
  const isDateLine = (value) =>
    /present|\\b\\d+\\s*(yr|yrs|mo|mos)\\b|\\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\\b|\\b\\d{4}\\b/i.test(value || '');
  const headline =
    clean(document.querySelector('.text-body-medium.break-words')?.innerText) ||
    clean(document.querySelector('main section div.text-body-medium')?.innerText) ||
    '';
  const about = Array.from(document.querySelectorAll('section'))
    .some((section) => /^About$/i.test(clean(section.querySelector('h2, span[aria-hidden="true"]')?.innerText || '')));
  const sections = Array.from(document.querySelectorAll('section, main'));
  const experienceRoot = sections.find((section) => {
    const text = clean(section.innerText);
    const heading = clean(section.querySelector('h2, span[aria-hidden="true"]')?.innerText || '');
    return /^Experience$/i.test(heading) || text.startsWith('Experience ') || location.pathname.includes('/details/experience');
  }) || document.querySelector('main') || document.body;

  const cards = Array.from(experienceRoot.querySelectorAll(
    '[componentkey^="entity-collection-item"], li.artdeco-list__item, li.pvs-list__paged-list-item'
  ));
  const uniqueCards = cards.filter((card, index) => {
    return !cards.some((other, otherIndex) => otherIndex !== index && other.contains(card));
  });

  const experiences = uniqueCards.map((row) => {
    const lines = (row.innerText || '').split(/\\n+/).map(clean).filter(Boolean);
    const paragraphs = Array.from(row.querySelectorAll('p')).map((p) => clean(p.innerText)).filter(Boolean);
    const title =
      paragraphs[0] ||
      clean(row.querySelector('.mr1.t-bold span[aria-hidden="true"]')?.innerText) ||
      clean(row.querySelector('span[aria-hidden="true"]')?.innerText) ||
      lines[0] ||
      '';
    const company =
      paragraphs.find((line, index) => index > 0 && !isDateLine(line) && !/^\\s*(Full-time|Part-time|Contract|Freelance|Internship)\\s*$/i.test(line)) ||
      lines.find((line, index) => index > 0 && !isDateLine(line) && !/^\\s*(Full-time|Part-time|Contract|Freelance|Internship)\\s*$/i.test(line)) ||
      '';
    const duration =
      paragraphs.find((line) => isDateLine(line)) ||
      lines.find((line) => isDateLine(line)) ||
      '';
    return { title, company, duration, lines, paragraphs };
  }).filter((item) => item.title && item.lines.length && !/^Experience$/i.test(item.title));

  return { headline, about_available: about, experiences };
}
"""
    )


async def extract_profile_experience(profile_page, profile_url: str, company_name: str, fingerprint: dict) -> dict:
    async def open_profile():
        response = await profile_page.goto(profile_url, wait_until="domcontentloaded", timeout=60000)
        if response and response.status >= 500:
            raise RuntimeError(f"Profile returned HTTP {response.status}")
        return response

    await retry_async(open_profile, attempts=3, base_delay=2.0, label=f"profile load {profile_url}")
    await human_settle(profile_page, fingerprint, 1.8, 3.5)
    if is_authwall_url(profile_page.url):
        raise RuntimeError(f"Profile redirected to LinkedIn wall: {profile_page.url}")
    await random_scroll(profile_page, rounds_min=2, rounds_max=4)

    raw = await read_experience_snapshot(profile_page)
    if not raw.get("experiences"):
        details_url = experience_details_url(profile_url)
        Actor.log.info(f"Opening profile experience details: {details_url}")
        await retry_async(
            lambda: profile_page.goto(details_url, wait_until="domcontentloaded", timeout=60000),
            attempts=2,
            base_delay=2.0,
            label=f"profile experience details {profile_url}",
        )
        await human_settle(profile_page, fingerprint, 1.5, 3.0)
        await random_scroll(profile_page, rounds_min=2, rounds_max=4)
        details_raw = await read_experience_snapshot(profile_page)
        if details_raw.get("experiences"):
            raw = {
                "headline": raw.get("headline") or details_raw.get("headline") or "",
                "about_available": bool(raw.get("about_available") or details_raw.get("about_available")),
                "experiences": details_raw.get("experiences") or [],
            }

    experiences = raw.get("experiences") or []
    current = choose_current_experience(experiences, company_name)
    duration_text = current.get("duration") or " ".join(current.get("lines", []))
    all_duration_text = " ".join(
        exp.get("duration") or " ".join(exp.get("lines", [])) for exp in experiences
    )
    return {
        "headline": raw.get("headline") or "",
        "about_available": bool(raw.get("about_available")),
        "current_title": infer_title_from_experience(current, raw.get("headline") or ""),
        "current_company_years": parse_years_from_text(duration_text),
        "total_years": parse_years_from_text(all_duration_text),
    }


async def queue_profile_for_enrichment(request_queue, item: dict) -> None:
    await request_queue.add_request(
        Request.from_url(
            item["url"],
            unique_key=f"profile:{item['url']}",
            user_data={"label": "decision_maker_profile", "employee": item},
        )
    )


async def push_listing_record(
    item: dict,
    *,
    company_name: str,
    company_url: str,
    decision_makers_only: bool,
    scraped_at: str,
) -> int:
    role_title = item.get("role") or item.get("designation") or ""
    role_info = classify_role(role_title, headline_matches=item.get("headline_matches", []))
    role_info["confidence_score"] = 35 if item.get("headline_matches") else 20
    if decision_makers_only and not role_info["is_decision_maker"]:
        return 0
    await Actor.push_data(
        build_output_item(
            item,
            company_name=company_name,
            company_url=company_url,
            role_title=role_title,
            role_info=role_info,
            current_company_years=None,
            total_years=None,
            about_available=False,
            scraped_at=scraped_at,
        )
    )
    return 1


async def enrich_queued_profiles(
    page,
    request_queue,
    *,
    company_name: str,
    company_url: str,
    fingerprint: dict,
    decision_makers_only: bool,
    profile_delay_min: float,
    profile_delay_max: float,
) -> int:
    saved = 0
    handled = 0
    skipped_non_decision_makers = 0
    failed_enrichments = 0

    while request := await request_queue.fetch_next_request():
        item = dict(request.user_data.get("employee") or {})
        scraped_at = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
        headline_matches = item.get("headline_matches", [])
        role_title = item.get("role") or item.get("designation") or ""
        role_info = classify_role(role_title, headline_matches=headline_matches)
        current_company_years = None
        total_years = None
        about_available = False

        try:
            await human_delay(profile_delay_min, profile_delay_max)
            # Reuse the same tab for profile enrichment; this avoids simultaneous LinkedIn tabs.
            profile_data = await extract_profile_experience(page, request.url, company_name, fingerprint)
            if profile_data["current_title"]:
                role_title = profile_data["current_title"]
            role_info = classify_role(role_title, headline_matches=headline_matches)
            role_info["confidence_score"] = 90 if profile_data["current_title"] else 65
            current_company_years = profile_data["current_company_years"]
            total_years = profile_data["total_years"]
            about_available = profile_data["about_available"]
            item["profile_enriched"] = True
        except Exception as exc:
            Actor.log.warning(f"Could not enrich queued profile {request.url}: {exc}")
            role_info["confidence_score"] = 45
            failed_enrichments += 1

        if not decision_makers_only or role_info["is_decision_maker"]:
            await Actor.push_data(
                build_output_item(
                    item,
                    company_name=company_name,
                    company_url=company_url,
                    role_title=role_title,
                    role_info=role_info,
                    current_company_years=current_company_years,
                    total_years=total_years,
                    about_available=about_available,
                    scraped_at=scraped_at,
                )
            )
            saved += 1
        else:
            skipped_non_decision_makers += 1
            Actor.log.info(
                "Skipped queued profile after enrichment because current role was not classified "
                f"as decision maker: {item.get('name', '')} | {role_title}"
            )

        await request_queue.mark_request_as_handled(request)
        handled += 1

    Actor.log.info(
        f"Handled {handled} queued profile requests: saved={saved}, "
        f"skipped_non_decision_makers={skipped_non_decision_makers}, failed_enrichments={failed_enrichments}."
    )
    return saved


async def scrape_people(
    page,
    company_url: str,
    company_name: str,
    fingerprint: dict,
    max_pages: int,
    *,
    decision_makers_only: bool,
    max_profiles_to_enrich: int,
    profile_delay_min: float,
    profile_delay_max: float,
) -> int:
    request_queue = await Actor.open_request_queue(name=None)
    seen_urls: set[str] = set()
    total = 0
    queued_profiles = 0

    for page_number in range(1, max_pages + 1):
        Actor.log.info(f"Scraping employee page {page_number}.")
        await page.wait_for_load_state("domcontentloaded", timeout=30000)
        await human_settle(page, fingerprint, 1.4, 2.8)
        await random_scroll(page, rounds_min=3, rounds_max=6)
        await human_delay(0.8, 1.6)

        employees = await extract_employees(page, company_url)
        new_items = []
        for item in employees:
            dedupe_key = item["url"] or f"{item['name']}|{item['designation']}|{item['location']}"
            if dedupe_key in seen_urls:
                continue
            seen_urls.add(dedupe_key)
            new_items.append(item)

        if new_items:
            saved_on_page = 0
            queued_on_page = 0
            scraped_at = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
            for position_on_page, item in enumerate(new_items, start=1):
                headline = item.get("role") or item.get("designation") or ""
                item["role"] = headline
                item["page_number"] = page_number
                item["position_on_page"] = position_on_page
                item["headline_matches"] = matched_decision_keywords(headline)

                should_queue = bool(item["headline_matches"]) and queued_profiles < max_profiles_to_enrich
                if should_queue:
                    await queue_profile_for_enrichment(request_queue, item)
                    queued_profiles += 1
                    queued_on_page += 1
                    continue

                saved_on_page += await push_listing_record(
                    item,
                    company_name=company_name,
                    company_url=company_url,
                    decision_makers_only=decision_makers_only,
                    scraped_at=scraped_at,
                )

            total += saved_on_page
            Actor.log.info(
                f"Page {page_number}: saved {saved_on_page} listing-only records and "
                f"queued {queued_on_page} likely decision-maker profiles."
            )
        else:
            Actor.log.warning(f"No new employees found on page {page_number}.")
            debug = await page_extract_debug(page)
            Actor.log.warning(f"Extract debug: {debug}")

        if page_number >= max_pages:
            break
        if not await click_next_page(page):
            Actor.log.info("No next page button found; employee pagination finished.")
            break
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=30000)
        except PlaywrightTimeoutError:
            pass
        await human_delay(2.0, 4.0)

    Actor.log.info(f"Listing phase finished. Queued {queued_profiles} profile URLs for enrichment.")
    total += await enrich_queued_profiles(
        page,
        request_queue,
        company_name=company_name,
        company_url=company_url,
        fingerprint=fingerprint,
        decision_makers_only=decision_makers_only,
        profile_delay_min=profile_delay_min,
        profile_delay_max=profile_delay_max,
    )

    return total


async def main() -> None:
    async with Actor:
        load_dotenv()
        actor_input = await Actor.get_input() or {}

        base_url = actor_input.get("company_url") or DEFAULT_COMPANY_URL
        max_pages = int(actor_input.get("max_pages") or 50)
        session_id = str(actor_input.get("session_id") or "linkedin_company_employees")
        email = actor_input.get("linkedin_email") or os.getenv("LINKEDIN_EMAIL") or os.getenv("EMAIL")
        password = actor_input.get("linkedin_password") or os.getenv("LINKEDIN_PASSWORD") or os.getenv("PASSWORD")
        use_apify_proxy = bool(actor_input.get("use_apify_proxy", False))
        proxy_groups = actor_input.get("proxy_groups") or ["RESIDENTIAL"]
        proxy_country = actor_input.get("proxy_country") or "IN"
        headless = bool(actor_input.get("headless", Actor.configuration.headless))
        decision_makers_only = bool(actor_input.get("decision_makers_only", False))
        max_profiles_to_enrich = int(actor_input.get("max_profiles_to_enrich") or 50)
        profile_delay_min = float(actor_input.get("profile_delay_min_seconds") or DEFAULT_MIN_PROFILE_DELAY_SECONDS)
        profile_delay_max = float(actor_input.get("profile_delay_max_seconds") or DEFAULT_MAX_PROFILE_DELAY_SECONDS)
        manual_verification_timeout_seconds = int(
            actor_input.get("manual_verification_timeout_seconds")
            or DEFAULT_MANUAL_VERIFICATION_TIMEOUT_SECONDS
        )
        if profile_delay_max < profile_delay_min:
            profile_delay_max = profile_delay_min
        fingerprint = build_fingerprint(session_id)

        proxy_configuration = None
        if use_apify_proxy:
            try:
                proxy_configuration = await Actor.create_proxy_configuration(
                    groups=proxy_groups,
                    country_code=proxy_country,
                )
            except Exception as exc:
                Actor.log.warning(f"Apify Proxy unavailable: {exc}")

        storage_key = storage_state_key(session_id)
        storage_state = None
        try:
            storage_state = await Actor.get_value(storage_key)
            if not storage_state:
                storage_state = await Actor.get_value(STORAGE_STATE_KEY)
        except Exception:
            storage_state = None

        async with async_playwright() as playwright:
            proxy_info = None
            if proxy_configuration:
                proxy_info = await proxy_configuration.new_proxy_info(
                    session_id=sanitize_proxy_session_id(session_id)
                )
            browser = await launch_browser(playwright, headless=headless, proxy_info=proxy_info)
            context = await make_context(browser, fingerprint, storage_state=storage_state)
            page = await context.new_page()
            page.set_default_timeout(20000)

            try:
                company_url = await resolve_company_url(page, base_url, fingerprint)
                company_name = await extract_company_name(page, company_url)

                # Build the people URL we ultimately need to land on
                people_url = urljoin(company_url.rstrip("/") + "/", "people/")

                # FIX 1: Detect authwall/redirect BEFORE going to people page and handle login
                # Try to go to the people page; if redirected to auth wall, login then re-navigate
                await go_to_people_page(page, company_url, fingerprint)
                await ensure_logged_in(
                    page,
                    email,
                    password,
                    fingerprint,
                    people_url,
                    manual_verification_timeout_seconds,
                )

                # If we ended up somewhere other than the people page after login, go back
                if not is_people_results_url(page.url):
                    Actor.log.info(f"Not on people page ({page.url}), navigating to {people_url}")
                    await page.goto(people_url, wait_until="domcontentloaded", timeout=60000)
                    await human_settle(page, fingerprint, 1.5, 3.0)

                    # One more authwall check after re-navigation
                    if is_authwall_url(page.url):
                        raise RuntimeError(
                            f"Still on auth wall after second navigation attempt: {page.url}"
                        )

                await save_storage_state(context, storage_key)
                total = await scrape_people(
                    page,
                    company_url,
                    company_name,
                    fingerprint,
                    max_pages,
                    decision_makers_only=decision_makers_only,
                    max_profiles_to_enrich=max_profiles_to_enrich,
                    profile_delay_min=profile_delay_min,
                    profile_delay_max=profile_delay_max,
                )
                Actor.log.info(f"Finished. Total structured records saved: {total}")
            finally:
                await context.close()
                await browser.close()
