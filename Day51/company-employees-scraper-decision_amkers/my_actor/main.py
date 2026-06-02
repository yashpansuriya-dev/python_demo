from __future__ import annotations

import asyncio
from datetime import datetime
import hashlib
import json
import os
import random
import re
from pathlib import Path
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlparse

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

DEFAULT_COMPANY_NAME = "Techforce Global"
DEFAULT_ROLE_KEYWORDS = [
    "Founder",
    "CEO",
    "CTO",
    "Director",
    "HR",
    "Head",
    "VP",
    "Manager",
    "Talent Acquisition",
]
SERP_PROXY_GROUPS = {"GOOGLE_SERP"}

# How many top Google results to inspect per keyword query before
# deciding whether the keyword is producing decision-maker hits.
KEYWORD_QUERY_PREVIEW_COUNT = 5

# Minimum priority score to treat a SERP-preview result as a decision maker.
DECISION_MAKER_SCORE_THRESHOLD = 60

# URL patterns that indicate LinkedIn is blocking / not logged in
AUTHWALL_PATTERNS = [
    "/authwall",
    "/checkpoint/",
    "/login",
    "/registration",
    "/uas/login",
    "linkedin.com/signup",
]

DEFAULT_MIN_PROFILE_DELAY_SECONDS = 4.0
DEFAULT_MAX_PROFILE_DELAY_SECONDS = 9.0


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


async def get_current_companies_from_profile(li_page) -> list[str]:
    """Extract current company names from the profile's currentPositionsDetails section."""
    try:
        return await li_page.evaluate("""
() => {
  const section = document.querySelector('[data-section="currentPositionsDetails"]');
  if (!section) return [];
  return Array.from(section.querySelectorAll('a span, span'))
    .map(el => (el.innerText || '').replace(/\\s+/g, ' ').trim())
    .filter(Boolean);
}
""")
    except Exception:
        return []


def build_fingerprint(seed: str) -> dict:
    digest = hashlib.sha256(seed.encode()).hexdigest()
    base = dict(FINGERPRINTS[int(digest[:2], 16) % len(FINGERPRINTS)])
    viewport = dict(VIEWPORTS[int(digest[2:4], 16) % len(VIEWPORTS)])
    base["viewport"] = viewport
    base["screen"] = {"width": viewport["width"], "height": viewport["height"]}
    base["device_scale_factor"] = viewport["device_scale_factor"]
    return base


def score_decision_maker(title: str) -> int:
    text = _lower_words(title)
    if "founder" in text:
        return 100
    if "ceo" in text:
        return 100
    if "cto" in text:
        return 95
    if "coo" in text:
        return 95
    if "cfo" in text:
        return 95
    if "president" in text:
        return 90
    if "vp" in text:
        return 85
    if "director" in text:
        return 80
    if "head" in text:
        return 75
    return 0


def is_current_company_match(experiences, company_name):
    for exp in experiences:
        company = exp.get("company", "")
        duration = exp.get("duration", "")
        if (
            company_names_match(company_name, company)
            and "present" in duration.lower()
        ):
            return True
    return False


def sanitize_proxy_session_id(value: str, *, max_length: int = 50) -> str:
    cleaned = re.sub(r"[^\w._~]+", "_", value.strip().lower())
    cleaned = re.sub(r"_+", "_", cleaned).strip("._") or "li_session"
    digest = hashlib.sha1(value.encode()).hexdigest()[:8]
    prefix = cleaned[: max(1, max_length - len(digest) - 1)].rstrip("._")
    return f"{prefix}_{digest}"


def mask_secret(value: str | None, *, keep: int = 4) -> str:
    if not value:
        return ""
    if len(value) <= keep:
        return "*" * len(value)
    return f"{value[:keep]}...{len(value)} chars"


def proxy_info_value(proxy_info, key: str, default=None):
    if proxy_info is None:
        return default
    if isinstance(proxy_info, dict):
        return proxy_info.get(key, default)
    return getattr(proxy_info, key, default)


def strip_proxy_auth_from_server(proxy_url: str) -> str:
    parsed = urlparse(proxy_url)
    if not parsed.scheme or not parsed.hostname:
        return proxy_url
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme}://{parsed.hostname}{port}"


def validate_proxy_session_id(session_id: str | None) -> str | None:
    if session_id is None:
        return None
    if len(session_id) > 50 or not re.fullmatch(r"[0-9a-zA-Z._~]+", session_id):
        raise ValueError(
            "Invalid Apify proxy session_id. It must be <= 50 chars and contain only "
            "0-9, a-z, A-Z, '.', '_' and '~'."
        )
    return session_id


def proxy_to_playwright(proxy_info):
    if not proxy_info:
        return None
    proxy_url = proxy_info_value(proxy_info, "url", "")
    username = proxy_info_value(proxy_info, "username", "")
    password = proxy_info_value(proxy_info, "password", "")
    server = strip_proxy_auth_from_server(proxy_url)
    proxy = {"server": server}
    if username:
        proxy["username"] = username
    if password:
        proxy["password"] = password
    return proxy


def log_proxy_info(proxy_info, *, label: str) -> None:
    if not proxy_info:
        Actor.log.info(f"{label}: no ProxyInfo generated.")
        return
    Actor.log.info(
        f"{label}: url={proxy_info_value(proxy_info, 'url', '')}, "
        f"hostname={proxy_info_value(proxy_info, 'hostname', '')}, "
        f"port={proxy_info_value(proxy_info, 'port', '')}, "
        f"username={proxy_info_value(proxy_info, 'username', '')}, "
        f"password={mask_secret(proxy_info_value(proxy_info, 'password', ''))}, "
        f"groups={proxy_info_value(proxy_info, 'groups', [])}, "
        f"country={proxy_info_value(proxy_info, 'country_code', '')}, "
        f"session={proxy_info_value(proxy_info, 'session_id', '')}"
    )


def log_playwright_proxy(proxy: dict | None, *, label: str) -> None:
    if not proxy:
        Actor.log.info(f"{label}: Playwright will launch without proxy.")
        return
    Actor.log.info(
        f"{label}: Playwright proxy server={proxy.get('server', '')}, "
        f"username={proxy.get('username', '')}, "
        f"password={mask_secret(proxy.get('password', ''))}"
    )


def is_tunnel_failure(exc: Exception) -> bool:
    return "ERR_TUNNEL_CONNECTION_FAILED" in str(exc)


def is_authwall_url(url: str) -> bool:
    return any(pattern in url for pattern in AUTHWALL_PATTERNS)


def is_linkedin_url(url: str) -> bool:
    host = urlparse(str(url)).netloc.lower()
    return host == "linkedin.com" or host.endswith(".linkedin.com")


def is_external_login_url(url: str) -> bool:
    return False


async def recover_from_external_login(page, target_url: str, fingerprint: dict) -> bool:
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
    log_proxy_info(proxy_info, label="Browser launch ProxyInfo")
    log_playwright_proxy(proxy, label="Browser launch")
    try:
        Actor.log.info(f"Launching installed Google Chrome headless={headless}")
        return await playwright.chromium.launch(channel="chrome", **opts)
    except Exception as exc:
        Actor.log.warning(f"Chrome channel failed, using bundled Chromium: {exc}")
        return await playwright.chromium.launch(**opts)


async def make_context(browser, fingerprint: dict, storage_state=None, proxy=None):
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
    if proxy is not None:
        opts["proxy"] = proxy
    context = await browser.new_context(**opts)
    await context.add_init_script(stealth_init_script(fingerprint))
    return context


async def close_login_popup(page) -> None:
    selectors = [
        "button.modal__dismiss",
        "button[aria-label='Dismiss']",
        "button[aria-label='Close']",
        "button.contextual-sign-in-modal__modal-dismiss",
        ".modal__dismiss",
        "button:has-text('Dismiss')",
    ]
    for selector in selectors:
        try:
            button = page.locator(selector).first
            if await button.count() and await button.is_visible(timeout=1200):
                await button.click()
                await human_delay(0.6, 1.2)
                return
        except Exception:
            continue
    Actor.log.debug("No LinkedIn login popup close button was visible.")


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


async def ensure_logged_in(page, email: str, password: str, fingerprint: dict, target_url: str) -> None:
    current_url = page.url
    if not is_authwall_url(current_url):
        Actor.log.info(f"Already on a valid page: {current_url}")
        return

    Actor.log.info(f"Detected redirect to wall page: {current_url}. Performing login.")
    await login_if_needed(page, email, password, fingerprint, target_url=target_url)

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

    if target_url and (not is_linkedin_url(post_login_url) or (target_url not in post_login_url and not is_people_results_url(post_login_url))):
        Actor.log.info(f"Re-navigating to intended target after login: {target_url}")
        await page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
        await human_settle(page, fingerprint, 2.0, 3.5)

    final_url = page.url
    if await recover_from_external_login(page, target_url, fingerprint):
        final_url = page.url
    if is_authwall_url(final_url):
        raise RuntimeError(f"Redirected to wall page even after re-navigation: {final_url}")
    if not is_linkedin_url(final_url):
        raise RuntimeError(f"LinkedIn login navigated to an external page: {final_url}")

    Actor.log.info(f"Successfully on target page: {final_url}")


async def login_if_needed(page, email: str, password: str, fingerprint: dict, target_url: str = "") -> None:
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
    if any(token in body_text for token in ["security verification", "quick security check", "enter the code", "captcha"]):
        raise RuntimeError(
            "LinkedIn requested security verification. "
            "Run headful and complete the challenge manually, then rerun."
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


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _lower_words(text: str) -> str:
    return re.sub(r"[^a-z0-9+#]+", " ", (text or "").lower()).strip()


def matched_decision_keywords(text: str, keywords: list[str] | None = None) -> list[str]:
    haystack = f" {_lower_words(text)} "
    matches: list[str] = []
    seen_keys: set[str] = set()
    for keyword in keywords or DECISION_MAKER_KEYWORDS:
        needle = f" {_lower_words(keyword)} "
        normalized_keyword = _lower_words(keyword)
        if needle in haystack and normalized_keyword not in seen_keys:
            matches.append(keyword)
            seen_keys.add(normalized_keyword)
    return matches


def is_likely_decision_maker(headline: str, keywords: list[str] | None = None) -> bool:
    return bool(matched_decision_keywords(headline, keywords))


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
    keyword_scores = {
        "ceo": 98,
        "chief executive officer": 98,
        "cto": 94,
        "chief technology officer": 94,
        "cio": 90,
        "cfo": 90,
        "coo": 90,
        "chief": 90,
        "president": 90,
        "vice president": 86,
        "vp": 86,
        "director": 82,
        "head": 78,
        "manager": 70,
        "lead": 66,
        "principal": 66,
        "solution architect": 66,
        "enterprise architect": 66,
    }
    for keyword in matched_keywords:
        normalized_keyword = _lower_words(keyword)
        score = max(score, keyword_scores.get(normalized_keyword, 0))
    return max(0, min(100, score))


def classify_role(
    title: str,
    *,
    headline_matches: list[str] | None = None,
    decision_keywords: list[str] | None = None,
) -> dict:
    normalized = normalize_role_title(title)
    matched = matched_decision_keywords(f"{title} {normalized}", decision_keywords)
    for keyword in headline_matches or []:
        if keyword not in matched:
            matched.append(keyword)
    title_text = normalized or title
    role_keyword_text = " ".join(
        keyword
        for keyword in matched
        if _lower_words(keyword) not in {"partner", "founder", "co-founder", "co founder", "owner"}
    )
    classifier_text = " ".join(part for part in [title_text, role_keyword_text] if part)
    department = classify_department(classifier_text)
    seniority = classify_seniority(classifier_text)
    score = priority_score(classifier_text, matched)
    is_decision_maker = score >= DECISION_MAKER_SCORE_THRESHOLD or seniority in {"Founder", "C-Level", "VP", "Director"}
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
        "is_open_to_work": bool(item.get("is_open_to_work")),
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
            "source_query": item.get("source_query", ""),
            "google_title": item.get("google_title", ""),
            "google_snippet": item.get("google_snippet", ""),
        },
    }


def _strip_noise(line: str, name: str) -> str:
    value = _clean(line).replace("Verified", "").strip()
    escaped = re.escape(name)
    value = re.sub(rf"^{escaped}\s*[•\u2022]\s*\d+(st|nd|rd|th)\+?", "", value, flags=re.IGNORECASE).strip()
    value = re.sub(r"^\s*[•\u2022â€¢]\s*\d+(st|nd|rd|th)\+?\s*", "", value, flags=re.IGNORECASE).strip()
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
_OPEN_TO_WORK_RE = re.compile(r"\bis\s+open\s+to\s+work\b", re.IGNORECASE)


def _is_open_to_work_alt(value: str) -> bool:
    return bool(_OPEN_TO_WORK_RE.search(_clean(value)))


def _clean_profile_image_alt(value: str) -> str:
    value = re.sub(r"^View\s+", "", _clean(value), flags=re.IGNORECASE)
    value = _OPEN_TO_WORK_RE.sub("", value)
    return _clean(value)


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
  const imageAlts = Array.from(card.querySelectorAll('img[alt]'))
    .map((node) => node.getAttribute('alt') || '')
    .map((text) => text.replace(/\\s+/g, ' ').trim())
    .filter(Boolean);
  const lines = (card.innerText || '')
    .split(/\\n+/)
    .map((line) => line.replace(/\\s+/g, ' ').trim())
    .filter(Boolean);
  return { links, names, imageAlts, lines };
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
        image_alts = [_clean(alt) for alt in data.get("imageAlts", []) if _clean(alt)]
        is_open_to_work = any(_is_open_to_work_alt(alt) for alt in image_alts)
        name_candidates: list[str] = []
        for link in links:
            name_candidates.extend([link.get("text") or "", link.get("aria") or ""])
        name_candidates.extend(data.get("names") or [])
        name_candidates.extend(lines[:3])

        name = ""
        for candidate in name_candidates:
            candidate = _clean_profile_image_alt(candidate)
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
                "is_open_to_work": is_open_to_work,
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


def infer_title_from_experience(exp: dict, fallback: str, company_name: str = "") -> str:
    title = _clean(exp.get("title") or "")
    title_looks_like_company = bool(company_name and company_names_match(company_name, title))
    if (
        title
        and not title_looks_like_company
        and not re.search(r"\bpresent\b|\b\d+\s*(yrs?|mos?)\b", title, re.IGNORECASE)
    ):
        return title
    lines = [_clean(line) for line in exp.get("lines", []) if _clean(line)]
    noise = re.compile(r"\b(experience|present|yrs?|mos?|followers?|connections?)\b", re.IGNORECASE)
    for line in lines[:8]:
        if line == exp.get("company"):
            continue
        if company_name and company_names_match(company_name, line) and not matched_decision_keywords(line):
            continue
        if len(line) > 120 or noise.search(line):
            continue
        return line
    return fallback


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
        "current_title": infer_title_from_experience(current, raw.get("headline") or "", company_name),
        "current_company_years": parse_years_from_text(duration_text),
        "total_years": parse_years_from_text(all_duration_text),
        "experiences": experiences,
    }


def normalize_linkedin_profile_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.netloc:
        parsed = urlparse(urljoin("https://www.linkedin.com", url))
    if "google." in parsed.netloc.lower() and parsed.path.startswith("/url"):
        redirect_url = parse_qs(parsed.query).get("q", [""])[0] or parse_qs(parsed.query).get("url", [""])[0]
        if redirect_url:
            parsed = urlparse(unquote(redirect_url))
    host = parsed.netloc.lower()
    if "linkedin.com" not in host or not parsed.path.startswith("/in/"):
        return ""
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2 or parts[0] != "in":
        return ""
    slug = parts[1]
    if not slug:
        return ""
    return f"https://www.linkedin.com/in/{slug}"


def normalize_string_list(value, default: list[str] | None = None) -> list[str]:
    if value is None:
        return list(default or [])
    if isinstance(value, str):
        items = re.split(r"[\n,;]+", value)
    elif isinstance(value, list):
        items = value
    else:
        return list(default or [])
    cleaned = [_clean(str(item)) for item in items if _clean(str(item))]
    return list(dict.fromkeys(cleaned))


def uses_serp_proxy_group(proxy_groups: list[str]) -> bool:
    return any(group.upper() in SERP_PROXY_GROUPS for group in proxy_groups)


def normalize_proxy_groups(proxy_groups: list[str]) -> list[str]:
    cleaned = [group.upper() if group.upper() in SERP_PROXY_GROUPS else group for group in proxy_groups]
    if uses_serp_proxy_group(cleaned) and len(cleaned) > 1:
        Actor.log.warning(
            f"GOOGLE_SERP cannot be mixed with other proxy groups. "
            f"Received {cleaned}; using ['GOOGLE_SERP'] only."
        )
        return ["GOOGLE_SERP"]
    return cleaned


def parse_google_profile_text(title: str, snippet: str, company_name: str) -> dict:
    title = _clean(title)
    snippet = _clean(snippet)
    combined = _clean(f"{title} {snippet}")
    name = ""
    headline = ""
    location = ""

    if title:
        name = _clean(re.split(r"\s[-|]\s|\s\|\s*LinkedIn", title, maxsplit=1)[0])
        headline_match = re.search(r"\s[-|]\s(.+?)(?:\s\|\s*LinkedIn|$)", title)
        if headline_match:
            headline = _clean(headline_match.group(1))

    company_pattern = re.escape(company_name)
    at_company = re.search(
        rf"([A-Z][^.;|·]{{2,140}}?\bat\s+{company_pattern}\b)",
        combined,
        flags=re.IGNORECASE,
    )
    if at_company:
        headline = _clean(at_company.group(1))
    elif not headline:
        role_match = re.search(
            r"([A-Z][^.;|·]{2,140}?\b(?:founder|ceo|cto|director|manager|head|hr|recruiter|engineer|lead|vp)\b[^.;|·]{0,100})",
            combined,
            flags=re.IGNORECASE,
        )
        if role_match:
            headline = _clean(role_match.group(1))

    location_match = re.search(r"(?:^|[.·]\s*)([^.·]{2,90}?(?:Area|India|United States|UK|Canada|Surat|Ahmedabad|Mumbai|Bengaluru|Delhi))\s*[.·]", f"{snippet}.", flags=re.IGNORECASE)
    if location_match:
        location = _clean(location_match.group(1))

    return {"name": name, "headline": headline or snippet, "location": location}


async def extract_google_results(page, query: str) -> list[dict]:
    rows = await page.evaluate(
        """
() => {
  const clean = (value) => (value || '').replace(/\\s+/g, ' ').trim();
  const nodes = Array.from(document.querySelectorAll('a[href]'));
  const results = [];
  for (const node of nodes) {
    const href = node.href || node.getAttribute('href') || '';
    if (!/linkedin\\.com\\/in\\//i.test(href)) continue;
    const root = node.closest('div.g, div[data-sokoban-container], div.MjjYud, div') || node;
    const title = clean(node.innerText) || clean(root.querySelector('h3')?.innerText);
    const snippet = clean(root.innerText).slice(0, 500);
    results.push({ url: href, title, snippet });
  }
  return results;
}
"""
    )
    html = await page.content()
    for match in re.finditer(r"linkedin\.com/in/([a-zA-Z0-9_%.-]{3,100})", html, flags=re.IGNORECASE):
        rows.append({"url": f"https://www.linkedin.com/in/{match.group(1)}", "title": "", "snippet": ""})
    cleaned: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        url = normalize_linkedin_profile_url(row.get("url", ""))
        if not url or url in seen:
            continue
        seen.add(url)
        cleaned.append(
            {
                "url": url,
                "google_title": _clean(row.get("title", "")),
                "google_snippet": _clean(row.get("snippet", "")),
                "source_query": query,
            }
        )
    return cleaned


async def accept_google_consent(page) -> None:
    await click_first_visible(
        page,
        [
            "button:has-text('Accept all')",
            "button:has-text('I agree')",
            "button:has-text('Reject all')",
            "form[action*='consent'] button",
        ],
        timeout_ms=1200,
    )


def _result_looks_like_decision_maker(result: dict, company_name: str, decision_keywords: list[str]) -> bool:
    """
    Quick SERP-level check: does the Google title/snippet suggest this profile
    is a decision maker at the target company?
    """
    title = result.get("google_title", "")
    snippet = result.get("google_snippet", "")
    combined = f"{title} {snippet}"
    parsed = parse_google_profile_text(title, snippet, company_name)
    headline = parsed.get("headline", "")
    check_text = f"{combined} {headline}"
    role_info = classify_role(
        headline,
        headline_matches=matched_decision_keywords(check_text, decision_keywords),
        decision_keywords=decision_keywords,
    )
    return role_info["is_decision_maker"]


async def fetch_google_page(
    page,
    query: str,
    *,
    start: int = 0,
    fingerprint: dict,
    google_search_scheme: str,
) -> list[dict]:
    """Navigate to one Google SERP page and return extracted profile rows."""
    search_url = f"{google_search_scheme}://www.google.com/search?q={quote_plus(query)}&start={start}"
    Actor.log.info(f"Google search: {query!r} (start={start})")
    try:
        await page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
        await accept_google_consent(page)
        await human_settle(page, fingerprint, 0.8, 1.8)
        return await extract_google_results(page, query)
    except Exception as exc:
        if "ERR_TUNNEL_CONNECTION_FAILED" in str(exc):
            raise RuntimeError(
                "Google SERP proxy tunnel failed. "
                "Check proxy configuration."
            ) from exc
        Actor.log.warning(f"Google query failed: {query!r}: {exc}")
        return []


# ---------------------------------------------------------------------------
# NEW: Two-phase Google collection
#
# Phase 1 – Keyword queries  (site:linkedin.com/in "Company" ("Keyword"))
#   For each keyword, fetch the first page of results (≤10 results).
#   Inspect the first KEYWORD_QUERY_PREVIEW_COUNT hits:
#     • If decision_makers_only=True  → only add results that look like DMs.
#     • If decision_makers_only=False → add all results.
#   If the preview shows ≥1 DM hit (or DM mode is off), continue fetching
#   additional pages of that keyword query up to google_pages_per_query.
#
# Phase 2 – General query  (site:linkedin.com/in "Company")
#   Run last, collect everything (filtered by DM status when mode is on).
# ---------------------------------------------------------------------------

async def collect_google_profile_results_v2(
    page,
    *,
    company_name: str,
    role_keywords: list[str],
    locations: list[str],
    max_results: int,
    google_pages_per_query: int,
    fingerprint: dict,
    google_search_scheme: str,
    decision_makers_only: bool,
    decision_keywords: list[str],
) -> list[dict]:
    """
    New two-phase Google collection strategy.

    Phase 1: For each keyword (and optional location combo), run
      site:linkedin.com/in "Company" ("Keyword")
    and keep the top-N results that pass the decision-maker preview check.

    Phase 2: Run the bare general query
      site:linkedin.com/in "Company"
    and collect remaining results up to max_results.
    """
    discovered: list[dict] = []
    seen: set[str] = set()

    def _add(result: dict) -> bool:
        url = normalize_linkedin_profile_url(result.get("url", ""))
        if not url or url in seen:
            return False
        if decision_makers_only and not _result_looks_like_decision_maker(result, company_name, decision_keywords):
            return False
        seen.add(url)
        discovered.append({**result, "url": url})
        return True

    # ------------------------------------------------------------------ #
    # Phase 1: per-keyword queries                                         #
    # ------------------------------------------------------------------ #
    # Build keyword × location combos (keyword-only first, then with each location)
    keyword_queries: list[tuple[str, str]] = []  # (query_string, keyword_label)
    for keyword in role_keywords:
        keyword_queries.append((
            f'site:linkedin.com/in "{company_name}" ("{keyword}")',
            keyword,
        ))
        for location in locations:
            keyword_queries.append((
                f'site:linkedin.com/in "{company_name}" ("{keyword}") "{location}"',
                keyword,
            ))

    for query_str, keyword_label in keyword_queries:
        if len(discovered) >= max_results:
            break

        # Fetch first page
        first_page_rows = await fetch_google_page(
            page, query_str, start=0,
            fingerprint=fingerprint,
            google_search_scheme=google_search_scheme,
        )
        if not first_page_rows:
            debug = await page_extract_debug(page)
            Actor.log.warning(f"No results for keyword query '{keyword_label}'. Debug: {debug}")
            continue

        # Preview first N to decide whether keyword is yielding DMs
        preview_rows = first_page_rows[:KEYWORD_QUERY_PREVIEW_COUNT]
        dm_hits_in_preview = sum(
            1 for r in preview_rows
            if _result_looks_like_decision_maker(r, company_name, decision_keywords)
        )
        if decision_makers_only and dm_hits_in_preview == 0:
            Actor.log.info(
                f"Keyword '{keyword_label}': 0/{len(preview_rows)} preview results look like "
                "decision makers — skipping further pages for this query."
            )
            # Still try to add any genuine DMs from the full first page
            for row in first_page_rows:
                _add(row)
            continue

        Actor.log.info(
            f"Keyword '{keyword_label}': {dm_hits_in_preview}/{len(preview_rows)} preview hits "
            f"look like decision makers — collecting up to {google_pages_per_query} page(s)."
        )

        # Add all from the first page
        added_first = sum(1 for row in first_page_rows if _add(row))
        Actor.log.info(f"  Page 1: added {added_first} results (total so far: {len(discovered)})")

        # Fetch additional pages if needed
        for page_index in range(1, google_pages_per_query):
            if len(discovered) >= max_results:
                break
            await human_delay(1.5, 3.5)
            rows = await fetch_google_page(
                page, query_str, start=page_index * 10,
                fingerprint=fingerprint,
                google_search_scheme=google_search_scheme,
            )
            if not rows:
                break
            added = sum(1 for row in rows if _add(row))
            Actor.log.info(f"  Page {page_index + 1}: added {added} results (total: {len(discovered)})")
            await human_delay(1.0, 2.5)

    # ------------------------------------------------------------------- #
    # Phase 2: general company query (no keyword filter)                  #
    # ------------------------------------------------------------------- #
    if len(discovered) < max_results:
        general_query = f'site:linkedin.com/in "{company_name}"'
        Actor.log.info(f"Phase 2 — general query: {general_query!r}")

        for page_index in range(google_pages_per_query):
            if len(discovered) >= max_results:
                break
            rows = await fetch_google_page(
                page, general_query, start=page_index * 10,
                fingerprint=fingerprint,
                google_search_scheme=google_search_scheme,
            )
            if not rows:
                break
            added = sum(1 for row in rows if _add(row))
            Actor.log.info(
                f"  General query page {page_index + 1}: added {added} results "
                f"(total: {len(discovered)})"
            )
            if page_index < google_pages_per_query - 1:
                await human_delay(1.5, 3.5)

    Actor.log.info(f"Google collection complete: {len(discovered)} unique profile URLs.")
    return discovered[:max_results]


async def log_browser_ip(page, *, uses_google_serp: bool = False) -> None:
    if uses_google_serp:
        Actor.log.info("Skipping HTTPS IP diagnostic — GOOGLE_SERP proxy does not tunnel arbitrary HTTPS.")
        return
    try:
        response = await page.goto("https://api.apify.com/v2/browser-info", wait_until="domcontentloaded", timeout=30000)
        status = response.status if response else None
        body = _clean(await page.locator("body").inner_text(timeout=5000))
        ip_match = re.search(r'"clientIp"\s*:\s*"([^"]+)"|"ip"\s*:\s*"([^"]+)"', body)
        current_ip = next((group for group in (ip_match.groups() if ip_match else []) if group), "")
        Actor.log.info(f"Proxy IP diagnostic: status={status}, current_ip={current_ip or 'unknown'}, body_sample={body[:250]}")
    except Exception as exc:
        Actor.log.warning(f"Proxy IP diagnostic failed: {exc}")


async def run_proxy_connectivity_test(page, *, proxy_info, uses_google_serp: bool) -> None:
    log_proxy_info(proxy_info, label="Connectivity test ProxyInfo")
    await log_browser_ip(page, uses_google_serp=uses_google_serp)

    tests = [] if uses_google_serp else ["https://www.google.com"]
    if uses_google_serp:
        tests.append("http://www.google.com/search?q=apify")

    last_exc: Exception | None = None
    for url in tests:
        try:
            Actor.log.info(f"Proxy connectivity test navigation: {url}")
            response = await page.goto(url, wait_until="commit", timeout=60000)
            status = response.status if response else None
            title = ""
            try:
                title = await page.title()
            except Exception:
                pass
            Actor.log.info(f"Proxy connectivity test OK: url={url}, status={status}, final_url={page.url}, title={title[:120]}")
            return
        except Exception as exc:
            last_exc = exc
            Actor.log.warning(f"Proxy connectivity test failed for {url}: {exc}")
            if not uses_google_serp or not is_tunnel_failure(exc):
                break
            Actor.log.warning(
                "HTTPS Google failed with a tunnel error through GOOGLE_SERP. "
                "Testing plain HTTP Google SERP next."
            )

    if last_exc:
        raise last_exc


async def create_proxy_configuration_from_input(
    *,
    use_apify_proxy: bool,
    proxy_groups: list[str],
    company_name: str,
    visit_linkedin_profiles: bool = False,
) -> tuple[object | None, object | None, list[str], str, bool]:
    proxy_groups = normalize_proxy_groups(proxy_groups)
    uses_google_serp = uses_serp_proxy_group(proxy_groups)

    proxy_country = ""
    Actor.log.info(
        f"Proxy input: use_apify_proxy={use_apify_proxy}, groups={proxy_groups}, "
        f"uses_google_serp={uses_google_serp}, visit_linkedin_profiles={visit_linkedin_profiles}"
    )

    if not use_apify_proxy:
        return None, None, proxy_groups, proxy_country, uses_google_serp

    search_proxy_configuration = None
    linkedin_proxy_configuration = None

    if uses_google_serp:
        Actor.log.info("Creating Apify ProxyConfiguration for Google SERP search.")
        search_proxy_configuration = await Actor.create_proxy_configuration(groups=["GOOGLE_SERP"])
        if visit_linkedin_profiles:
            Actor.log.info("Creating Apify ProxyConfiguration for LinkedIn profile visits with RESIDENTIAL.")
            linkedin_proxy_configuration = await Actor.create_proxy_configuration(groups=["RESIDENTIAL"])
    else:
        Actor.log.info(f"Creating Apify ProxyConfiguration for groups={proxy_groups}.")
        search_proxy_configuration = await Actor.create_proxy_configuration(groups=proxy_groups)
        linkedin_proxy_configuration = search_proxy_configuration

    if not search_proxy_configuration:
        raise RuntimeError("Could not create Apify ProxyConfiguration for search.")

    return search_proxy_configuration, linkedin_proxy_configuration, proxy_groups, proxy_country, uses_google_serp


async def new_proxy_info_for_attempt(proxy_configuration, base_session_id: str, attempt: str):
    if not proxy_configuration:
        return None
    if attempt == "configured-session":
        session_id = validate_proxy_session_id(sanitize_proxy_session_id(base_session_id))
    elif attempt == "fresh-session":
        session_id = validate_proxy_session_id(sanitize_proxy_session_id(f"{base_session_id}_{random.randint(100000, 999999)}"))
    elif attempt == "no-session":
        session_id = None
    else:
        raise ValueError(f"Unknown proxy attempt: {attempt}")
    Actor.log.info(f"Generating ProxyInfo with attempt={attempt}, session_id={session_id or '(none)'}")
    proxy_info = await proxy_configuration.new_proxy_info(session_id=session_id)
    log_proxy_info(proxy_info, label=f"Generated ProxyInfo ({attempt})")
    return proxy_info


async def open_browser_with_proxy_preflight(
    playwright,
    *,
    proxy_configuration,
    session_id: str,
    headless: bool,
    fingerprint: dict,
    uses_google_serp: bool,
):
    attempts = ["configured-session"]
    if proxy_configuration:
        attempts.extend(["fresh-session", "no-session"])

    last_exc: Exception | None = None
    for attempt in attempts:
        browser = None
        context = None
        try:
            proxy_info = await new_proxy_info_for_attempt(proxy_configuration, session_id, attempt)
            browser = await launch_browser(playwright, headless=headless, proxy_info=proxy_info)
            context = await make_context(browser, fingerprint)
            page = await context.new_page()
            page.set_default_timeout(20000)
            await run_proxy_connectivity_test(page, proxy_info=proxy_info, uses_google_serp=uses_google_serp)
            return browser, context, page, proxy_info
        except Exception as exc:
            last_exc = exc
            Actor.log.warning(f"Proxy/browser preflight failed on attempt '{attempt}': {exc}")
            if context:
                await context.close()
            if browser:
                await browser.close()
            if uses_google_serp or not proxy_configuration or not is_tunnel_failure(exc):
                break

    if uses_google_serp:
        Actor.log.warning(
            "Proxy preflight could not verify connectivity (expected for GOOGLE_SERP). "
            "Continuing — the proxy will be applied to actual Google search URLs. "
            f"Preflight error was: {last_exc}"
        )
        browser = await launch_browser(playwright, headless=headless, proxy_info=None)
        proxy_info = await new_proxy_info_for_attempt(proxy_configuration, session_id, "configured-session")
        browser = await launch_browser(playwright, headless=headless, proxy_info=proxy_info)
        context = await make_context(browser, fingerprint)
        page = await context.new_page()
        page.set_default_timeout(20000)
        return browser, context, page, proxy_info

    raise RuntimeError(
        "Proxy preflight failed. Root cause: browser could not establish a working connection through the generated proxy. "
        f"Last error: {last_exc}"
    ) from last_exc


async def read_public_profile_snapshot(page) -> dict:
    return await page.evaluate(
        """
() => {
  const clean = (value) => (value || '').replace(/\\s+/g, ' ').trim();
  const jsonLd = Array.from(document.querySelectorAll('script[type="application/ld+json"]'))
    .map((node) => {
      try { return JSON.parse(node.textContent || '{}'); } catch (e) { return {}; }
    });
  const person = jsonLd.find((item) => item && (item['@type'] === 'Person' || item.name));
  const name =
    clean(person?.name) ||
    clean(document.querySelector('h1')?.innerText) ||
    clean(document.querySelector('.top-card-layout__title')?.innerText) ||
    '';
  const headline =
    clean(person?.jobTitle) ||
    clean(document.querySelector('.top-card-layout__headline')?.innerText) ||
    clean(document.querySelector('[data-test-id="about-us__headline"]')?.innerText) ||
    clean(document.querySelector('main h2')?.innerText) ||
    '';
  const location =
    clean(document.querySelector('.top-card__subline-item')?.innerText) ||
    clean(document.querySelector('.top-card-layout__first-subline')?.innerText) ||
    '';
  const image = document.querySelector('.top-card__profile-image, img[alt*="profile"], img')?.src || '';
  return { name, headline, location, image };
}
"""
    )

def company_names_match(company_name: str, candidate: str) -> bool:
    """Strict company name matching — normalized but exact."""
    def normalize(name: str) -> str:
        name = name.lower().strip()
        # Remove common suffixes that don't affect identity
        suffixes = r'\b(inc\.?|llc\.?|ltd\.?|corp\.?|co\.?|group|holdings|international|global)\b'
        name = re.sub(suffixes, '', name)
        # Remove punctuation and extra whitespace
        name = re.sub(r'[^\w\s]', '', name)
        name = re.sub(r'\s+', ' ', name).strip()
        return name

    return normalize(company_name) == normalize(candidate)


async def scrape_google_profiles(
    page,
    profile_results: list[dict],
    *,
    company_name: str,
    fingerprint: dict,
    decision_makers_only: bool,
    decision_keywords: list[str],
    visit_linkedin_profiles: bool,
    profile_delay_min: float,
    profile_delay_max: float,
    linkedin_context=None,
) -> int:
    saved = 0
    company_url = f'https://www.linkedin.com/search/results/companies/?keywords={quote_plus(company_name)}'

    for position, result in enumerate(profile_results, start=1):
        profile_url = normalize_linkedin_profile_url(result["url"])
        if not profile_url:
            continue
        scraped_at = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
        item = {
            "name": "",
            "role": "",
            "designation": "",
            "location": "",
            "url": profile_url,
            "company_url": company_url,
            "page_number": 1,
            "position_on_page": position,
            "source_query": result.get("source_query", ""),
            "google_title": result.get("google_title", ""),
            "google_snippet": result.get("google_snippet", ""),
            "is_open_to_work": False,
        }
        parsed_serp = parse_google_profile_text(
            result.get("google_title", ""),
            result.get("google_snippet", ""),
            company_name,
        )
        item["name"] = parsed_serp["name"]
        item["role"] = parsed_serp["headline"]
        item["designation"] = parsed_serp["headline"]
        item["location"] = parsed_serp["location"]

        profile_data = {
            "headline": "",
            "about_available": False,
            "current_title": "",
            "current_company_years": None,
            "total_years": None,
            "experiences": [],
        }

        if visit_linkedin_profiles:
            try:
                await human_delay(profile_delay_min, profile_delay_max)
                Actor.log.info(f"Opening public LinkedIn profile: {profile_url}")
                li_page = page
                _owned_li_page = False
                if linkedin_context is not None:
                    li_page = await linkedin_context.new_page()
                    li_page.set_default_timeout(20000)
                    _owned_li_page = True
                try:
                    await retry_async(
                        lambda: li_page.goto(profile_url, wait_until="domcontentloaded", timeout=60000),
                        attempts=2,
                        base_delay=2.0,
                        label=f"profile load {profile_url}",
                    )
                    await human_settle(li_page, fingerprint, 1.2, 2.5)
                    await close_login_popup(li_page)
                    snapshot = await read_public_profile_snapshot(li_page)
                    item["name"] = snapshot.get("name") or item["name"]
                    item["role"] = snapshot.get("headline") or item["role"]
                    item["designation"] = item["role"]
                    item["location"] = snapshot.get("location") or item["location"]
                    if not is_authwall_url(li_page.url):
                        try:
                            profile_data = await extract_profile_experience(li_page, profile_url, company_name, fingerprint)
                            await close_login_popup(li_page)
                        except Exception as exc:
                            Actor.log.debug(f"Experience extraction skipped for {profile_url}: {exc}")
                    if profile_data.get("current_title"):
                        item["role"] = profile_data["current_title"]
                        item["designation"] = profile_data["current_title"]
                    elif profile_data.get("headline"):
                        item["role"] = profile_data["headline"]
                        item["designation"] = profile_data["headline"]
                finally:
                    if _owned_li_page:
                        await li_page.close()
            except Exception as exc:
                Actor.log.warning(f"Could not read public profile {profile_url}; using Google SERP data: {exc}")
        elif position == 1:
            Actor.log.info("Using Google SERP snippets only; LinkedIn profile visits are disabled.")

        headline_text = " ".join([item.get("role", ""), result.get("google_title", ""), result.get("google_snippet", "")])
        headline_matches = matched_decision_keywords(headline_text, decision_keywords)
        item["headline_matches"] = headline_matches

        role_info = classify_role(
            item.get("role", ""),
            headline_matches=headline_matches,
            decision_keywords=decision_keywords,
        )
        role_info["confidence_score"] = (
            90 if profile_data.get("current_title")
            else 60 if visit_linkedin_profiles and item.get("role")
            else 45
        )

        # ------------------------------------------------------------------
        # Current-company verification (when experience was loaded)
        # ------------------------------------------------------------------
        if visit_linkedin_profiles:
            current_companies = await get_current_companies_from_profile(li_page) if 'li_page' in dir() else []
            Actor.log.info(f"Current companies for {profile_url}: {current_companies}")
            if current_companies and not any(company_names_match(company_name, c) for c in current_companies):
                Actor.log.info(
                    f"Skipped — current company doesn't match '{company_name}': "
                    f"{profile_url} (found: {current_companies})"
                )
                continue
        if decision_makers_only and not role_info["is_decision_maker"]:
            Actor.log.info(f"Skipped non-decision-maker profile: {profile_url}")
            continue

        item["profile_enriched"] = bool(profile_data.get("current_title") or profile_data.get("headline"))
        await Actor.push_data(
            build_output_item(
                item,
                company_name=company_name,
                company_url=company_url,
                role_title=item.get("role", ""),
                role_info=role_info,
                current_company_years=profile_data.get("current_company_years"),
                total_years=profile_data.get("total_years"),
                about_available=bool(profile_data.get("about_available")),
                scraped_at=scraped_at,
            )
        )
        saved += 1

    return saved


async def main() -> None:
    async with Actor:
        load_dotenv()
        actor_input = await Actor.get_input() or {}

        company_name = _clean(actor_input.get("company_name") or DEFAULT_COMPANY_NAME)
        role_keywords = normalize_string_list(actor_input.get("role_keywords"), DEFAULT_ROLE_KEYWORDS)
        locations = normalize_string_list(actor_input.get("locations"), [])
        max_google_results = int(actor_input.get("max_google_results") or 100)
        google_pages_per_query = 2
        visit_linkedin_profiles = bool(actor_input.get("visit_linkedin_profiles", False))
        session_id = sanitize_proxy_session_id(company_name or "li_session")
        use_apify_proxy = bool(actor_input.get("use_apify_proxy", False))
        proxy_groups = normalize_proxy_groups(normalize_string_list(actor_input.get("proxy_groups"), ["GOOGLE_SERP"]))
        headless = bool(actor_input.get("headless", Actor.configuration.headless))
        decision_makers_only = bool(actor_input.get("decision_makers_only", True))
        profile_delay_min = DEFAULT_MIN_PROFILE_DELAY_SECONDS
        profile_delay_max = DEFAULT_MAX_PROFILE_DELAY_SECONDS

        if not company_name:
            raise ValueError("company_name is required.")
        if max_google_results < 1:
            raise ValueError("max_google_results must be at least 1.")
        if google_pages_per_query < 1:
            google_pages_per_query = 1

        fingerprint = build_fingerprint(session_id)

        search_proxy_configuration = None
        linkedin_proxy_configuration = None
        uses_google_serp = uses_serp_proxy_group(proxy_groups)
        try:
            (
                search_proxy_configuration,
                linkedin_proxy_configuration,
                proxy_groups,
                _proxy_country,
                uses_google_serp,
            ) = await create_proxy_configuration_from_input(
                use_apify_proxy=use_apify_proxy,
                proxy_groups=proxy_groups,
                company_name=company_name,
                visit_linkedin_profiles=visit_linkedin_profiles,
            )
        except Exception as exc:
            raise RuntimeError(f"Apify Proxy initialization failed: {exc}") from exc

        google_search_scheme = "http" if use_apify_proxy and uses_google_serp else "https"
        Actor.log.info(
            f"Google search URL scheme set to {google_search_scheme} "
            f"(use_apify_proxy={use_apify_proxy}, uses_google_serp={uses_google_serp})."
        )
        Actor.log.info(
            f"Starting scrape for company='{company_name}', "
            f"decision_makers_only={decision_makers_only}, "
            f"keywords={role_keywords}, locations={locations}, "
            f"max_results={max_google_results}."
        )

        async with async_playwright() as playwright:
            browser, context, page, proxy_info = await open_browser_with_proxy_preflight(
                playwright,
                proxy_configuration=search_proxy_configuration,
                session_id=session_id,
                headless=headless,
                fingerprint=fingerprint,
                uses_google_serp=uses_google_serp,
            )

            linkedin_context = None
            if uses_google_serp and visit_linkedin_profiles:
                if linkedin_proxy_configuration:
                    Actor.log.info("Creating a RESIDENTIAL-proxy browser context for LinkedIn profile visits.")
                    linkedin_proxy_info = await new_proxy_info_for_attempt(
                        linkedin_proxy_configuration, session_id, "configured-session"
                    )
                    linkedin_context = await make_context(
                        browser, fingerprint, proxy=proxy_to_playwright(linkedin_proxy_info)
                    )
                else:
                    Actor.log.info("Creating a direct browser context for LinkedIn profile visits.")
                    linkedin_context = await make_context(
                        browser, fingerprint, proxy={"server": "direct://"}
                    )
            elif not uses_google_serp and visit_linkedin_profiles and linkedin_proxy_configuration:
                Actor.log.info("Creating a LinkedIn browser context using the same Apify proxy configuration.")
                linkedin_proxy_info = await new_proxy_info_for_attempt(
                    linkedin_proxy_configuration, session_id, "configured-session"
                )
                linkedin_context = await make_context(
                    browser, fingerprint, proxy=proxy_to_playwright(linkedin_proxy_info)
                )

            try:
                # -------------------------------------------------------- #
                # Collect profile URLs using the new two-phase strategy     #
                # -------------------------------------------------------- #
                profile_results = await collect_google_profile_results_v2(
                    page,
                    company_name=company_name,
                    role_keywords=role_keywords,
                    locations=locations,
                    max_results=max_google_results,
                    google_pages_per_query=google_pages_per_query,
                    fingerprint=fingerprint,
                    google_search_scheme=google_search_scheme,
                    decision_makers_only=decision_makers_only,
                    decision_keywords=role_keywords,
                )
                Actor.log.info(
                    f"Collected {len(profile_results)} unique LinkedIn profile URLs from Google."
                )

                total = await scrape_google_profiles(
                    page,
                    profile_results,
                    company_name=company_name,
                    fingerprint=fingerprint,
                    decision_makers_only=decision_makers_only,
                    decision_keywords=role_keywords,
                    visit_linkedin_profiles=visit_linkedin_profiles,
                    profile_delay_min=profile_delay_min,
                    profile_delay_max=profile_delay_max,
                    linkedin_context=linkedin_context,
                )
                Actor.log.info(f"Finished. Total structured records saved: {total}")
            finally:
                if linkedin_context:
                    await linkedin_context.close()
                await context.close()
                await browser.close()