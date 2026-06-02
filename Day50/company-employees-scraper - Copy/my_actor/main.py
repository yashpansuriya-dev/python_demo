from __future__ import annotations

import asyncio
import hashlib
import json
import os
import random
import re
from pathlib import Path
from urllib.parse import parse_qs, unquote, urljoin, urlparse

from apify import Actor
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright


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

# URL patterns that indicate LinkedIn is blocking / not logged in
AUTHWALL_PATTERNS = [
    "/authwall",
    "/checkpoint/",
    "/login",
    "/registration",
    "/uas/login",
    "linkedin.com/signup",
]


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


def proxy_to_playwright(proxy_info):
    if not proxy_info:
        return None
    return {"server": proxy_info.url, "username": proxy_info.username, "password": proxy_info.password}


def is_authwall_url(url: str) -> bool:
    """Return True if the current URL is a login/authwall/registration page."""
    return any(pattern in url for pattern in AUTHWALL_PATTERNS)


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


async def ensure_logged_in(page, email: str, password: str, fingerprint: dict, target_url: str) -> None:
    """
    FIX 1: After login LinkedIn often redirects to /authwall, /checkpoint, or /registration.
    This function detects that and re-navigates to the intended target_url after login.
    """
    current_url = page.url
    if not is_authwall_url(current_url):
        Actor.log.info(f"Already on a valid page: {current_url}")
        return

    Actor.log.info(f"Detected redirect to wall page: {current_url}. Performing login.")
    await login_if_needed(page, email, password, fingerprint)

    # After login, LinkedIn may land on feed or another page — re-navigate to where we wanted
    post_login_url = page.url
    Actor.log.info(f"Post-login URL: {post_login_url}")

    if is_authwall_url(post_login_url):
        raise RuntimeError(
            f"Still on wall page after login attempt: {post_login_url}. "
            "Credentials may be wrong or a CAPTCHA was triggered."
        )

    # Re-navigate to the intended target only if LinkedIn did not already land
    # on an equivalent company people search page.
    if target_url and target_url not in post_login_url and not is_people_results_url(post_login_url):
        Actor.log.info(f"Re-navigating to intended target after login: {target_url}")
        await page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
        await human_settle(page, fingerprint, 2.0, 3.5)

    # Final check
    final_url = page.url
    if is_authwall_url(final_url):
        raise RuntimeError(f"Redirected to wall page even after re-navigation: {final_url}")

    Actor.log.info(f"Successfully on target page: {final_url}")


async def login_if_needed(page, email: str, password: str, fingerprint: dict) -> None:
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
            "a:has-text('Sign in')",
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
        await page.wait_for_url(lambda url: not is_authwall_url(str(url)), timeout=60000)
    except PlaywrightTimeoutError:
        Actor.log.warning(f"Login did not leave wall URL within timeout: {page.url}")

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

    if redirect_target and not is_authwall_url(page.url) and not is_people_results_url(page.url):
        Actor.log.info(f"Following LinkedIn session_redirect after login: {redirect_target}")
        await page.goto(redirect_target, wait_until="domcontentloaded", timeout=60000)
        await human_settle(page, fingerprint, 1.5, 3.0)


async def save_storage_state(context) -> None:
    try:
        await Actor.set_value(STORAGE_STATE_KEY, await context.storage_state())
    except Exception as exc:
        Actor.log.warning(f"Could not save LinkedIn storage state: {exc}")


# ---------------------------------------------------------------------------
# FIX 2: Python-native employee extraction (replaces page.evaluate JS blob)
# ---------------------------------------------------------------------------

def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


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


async def extract_employees(page, company_url: str) -> list[dict]:
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


async def scrape_people(page, company_url: str, fingerprint: dict, max_pages: int) -> int:
    seen_urls: set[str] = set()
    total = 0

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
            for position_on_page, item in enumerate(new_items, start=1):
                item["role"] = item.get("role") or item.get("designation") or ""
                item["page_number"] = page_number
                item["position_on_page"] = position_on_page
                await Actor.push_data(item)
            total += len(new_items)
            Actor.log.info(f"Saved {len(new_items)} employees from page {page_number}.")
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

        storage_state = None
        try:
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

                # Build the people URL we ultimately need to land on
                people_url = urljoin(company_url.rstrip("/") + "/", "people/")

                # FIX 1: Detect authwall/redirect BEFORE going to people page and handle login
                # Try to go to the people page; if redirected to auth wall, login then re-navigate
                await go_to_people_page(page, company_url, fingerprint)
                await ensure_logged_in(page, email, password, fingerprint, people_url)

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

                await save_storage_state(context)
                total = await scrape_people(page, company_url, fingerprint, max_pages)
                Actor.log.info(f"Finished. Total employees saved: {total}")
            finally:
                await context.close()
                await browser.close()
