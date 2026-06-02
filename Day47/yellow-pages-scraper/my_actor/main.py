from __future__ import annotations

import asyncio
import hashlib
import json
import os
import random
import re
import sys
from urllib.parse import urljoin

from apify import Actor, Request
from playwright.async_api import async_playwright

sys.stdout.reconfigure(encoding="utf-8")

# ─── Cloudflare title signatures ──────────────────────────────────────────────
CF_TITLES = {
    "just a moment",
    "attention required!",
    "attention required",
    "please wait...",
    "checking your browser",
    "one more step",
    "security check",
    "access denied",
}

VIEWPORTS = [
    {"width": 1280, "height": 720,  "device_scale_factor": 1},
    {"width": 1366, "height": 768,  "device_scale_factor": 1},
    {"width": 1440, "height": 900,  "device_scale_factor": 1},
    {"width": 1536, "height": 864,  "device_scale_factor": 1},
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
        "webgl_renderer": "ANGLE (Intel, Intel(R) UHD Graphics 620 Direct3D11 vs_5_0 ps_5_0, D3D11)",
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
        "webgl_renderer": "ANGLE (NVIDIA, NVIDIA GeForce GTX 1650 Direct3D11 vs_5_0 ps_5_0, D3D11)",
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


# ══════════════════════════════════════════════════════════════════════════════
#  Human-like helpers
# ══════════════════════════════════════════════════════════════════════════════

async def human_delay(min_s: float = 1.0, max_s: float = 2.5):
    await asyncio.sleep(random.uniform(min_s, max_s))


async def human_mouse_wander(page, fingerprint: dict):
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
    except Exception as e:
        Actor.log.debug(f"Mouse wander skipped: {e}")


async def random_scroll(page):
    try:
        for i in range(random.randint(3, 6)):
            if page.is_closed():
                return
            distance = random.randint(220, 680)
            if i and random.random() < 0.2:
                distance = -random.randint(80, 220)
            await page.mouse.wheel(0, distance)
            await asyncio.sleep(random.uniform(0.45, 1.25))
    except Exception as e:
        Actor.log.debug(f"Scroll skipped: {e}")


async def human_settle(page, fingerprint: dict, min_s=0.8, max_s=1.8):
    await human_delay(min_s, max_s)
    if random.random() < 0.85:
        await human_mouse_wander(page, fingerprint)
    if random.random() < 0.65:
        await random_scroll(page)


async def type_like_human(page, selector: str, text: str):
    Actor.log.info(f"  [type] '{selector}' <- '{text}'")
    await page.click(selector)
    await human_delay(0.3, 0.7)
    await page.keyboard.press("Control+a")
    await asyncio.sleep(random.uniform(0.05, 0.15))
    await page.keyboard.press("Delete")
    await human_delay(0.2, 0.5)
    for char in text:
        await page.type(selector, char, delay=random.randint(55, 175))
    await human_delay(0.4, 0.9)


# ══════════════════════════════════════════════════════════════════════════════
#  Cloudflare handler  —  with pre-warm trick for /search URLs
# ══════════════════════════════════════════════════════════════════════════════

async def soft_refresh_challenge(page, fingerprint: dict):
    try:
        if page.is_closed():
            return
        await human_mouse_wander(page, fingerprint)
        if random.random() < 0.4:
            await page.mouse.wheel(0, random.randint(80, 180))
        await human_delay(2.0, 4.5)
    except Exception as e:
        Actor.log.debug(f"Challenge soft interaction skipped: {e}")


def is_cloudflare_title(title: str) -> bool:
    title_lower = title.lower()
    return any(kw in title_lower for kw in CF_TITLES)


async def wait_for_cloudflare(
    page,
    timeout_s: int = 180,
    *,
    allow_manual: bool = True,
    refresh_attempts: int = 3,
) -> bool:
    """
    Poll until Cloudflare clears or timeout.
    On each CF hit: wanders mouse, scrolls slightly, waits, then reloads.
    """
    deadline = asyncio.get_event_loop().time() + timeout_s
    manual_notice_shown = False
    fp = getattr(page, "_fingerprint", build_fingerprint("fallback"))
    attempt = 0

    while asyncio.get_event_loop().time() < deadline:
        try:
            title = (await page.title()).strip()
        except Exception:
            title = ""

        Actor.log.info(f"[CF] title='{title}'")

        # Check for interactive challenge iframes
        try:
            challenge_count = await page.locator(
                "iframe[src*='challenges.cloudflare.com'],"
                "iframe[src*='hcaptcha.com'],"
                "div#challenge-form,"
                "div#cf-challenge-running"
            ).count()
        except Exception as e:
            Actor.log.warning(f"[CF] Page closed while checking challenge: {e}")
            return False

        if challenge_count:
            if not allow_manual:
                Actor.log.warning("[CF] Interactive checkbox challenge — cannot solve headlessly.")
                return False
            if not manual_notice_shown:
                Actor.log.warning("[CF] Manual checkbox detected — complete it in the browser window.")
                manual_notice_shown = True
            await asyncio.sleep(2)
            continue

        if not is_cloudflare_title(title):
            Actor.log.info(f"[CF] ✅ Passed — clean title: '{title}'")
            return True

        attempt += 1
        if attempt > refresh_attempts:
            Actor.log.warning("[CF] Still blocked after configured refresh attempts.")
            return False
        refresh_label = f"{attempt}/{refresh_attempts}" if refresh_attempts else str(attempt)
        Actor.log.warning(f"[CF] Challenge title on URL '{page.url}' refresh={refresh_label}: '{title}'")
        await soft_refresh_challenge(page, fp)
        try:
            if attempt <= refresh_attempts:
                wait_before_refresh = random.uniform(1.8, 4.5)
                Actor.log.info(f"[CF] Browser-like refresh after {wait_before_refresh:.1f}s...")
            else:
                wait_before_refresh = random.uniform(8.0, 15.0)
                Actor.log.info(f"[CF] Still blocked after refresh attempts; waiting {wait_before_refresh:.1f}s...")
            await asyncio.sleep(wait_before_refresh)
            await page.reload(wait_until="domcontentloaded", timeout=30_000)
            await asyncio.sleep(random.uniform(4.0, 8.0))
        except Exception as e:
            Actor.log.debug(f"Reload error: {e}")
        continue

    Actor.log.warning("[CF] ❌ Timed out waiting for Cloudflare to clear.")
    return False


async def prewarm_then_goto(
    page,
    url: str,
    *,
    fingerprint: dict,
    cf_wait_seconds: int,
    allow_manual: bool,
    cf_refresh_attempts: int,
) -> bool:
    """
    Two-phase navigation:
      1. Visit homepage first to warm cookies/session.
      2. Then navigate to the actual target URL.
    This greatly reduces CF blocks on /search pages.
    """
    page._fingerprint = fingerprint
    Actor.log.info(f"[nav] Navigating directly to target: {url}")
    await human_delay(0.4, 1.1)
    response = await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    Actor.log.info(f"[nav] HTTP {response.status if response else '?'} -> {url}")
    await human_settle(page, fingerprint, 0.5, 1.2)
    return await wait_for_cloudflare(
        page,
        timeout_s=cf_wait_seconds,
        allow_manual=allow_manual,
        refresh_attempts=cf_refresh_attempts,
    )

    # Phase 1 — homepage warm-up (skip if we're already on YP)
    current = page.url
    if "yellowpages.com" not in current:
        Actor.log.info("[prewarm disabled] old homepage warm-up skipped")
        try:
            r = await page.goto(
                "https://www.yellowpages.com",
                wait_until="domcontentloaded",
                timeout=60_000,
            )
            Actor.log.info(f"[prewarm] HTTP {r.status if r else '?'} -> homepage")
            await human_settle(page, fingerprint, 1.5, 3.0)
            # pass CF on homepage
            if not await wait_for_cloudflare(
                page,
                timeout_s=cf_wait_seconds,
                allow_manual=allow_manual,
                refresh_attempts=cf_refresh_attempts,
            ):
                Actor.log.warning("[prewarm] CF not cleared on homepage.")
                return False
            await human_settle(page, fingerprint, 1.0, 2.0)
        except Exception as e:
            Actor.log.warning(f"[prewarm] Homepage visit failed: {e}")

    # Phase 2 — navigate to actual URL
    Actor.log.info(f"[prewarm] Navigating to target: {url}")
    await human_delay(0.8, 1.8)
    response = await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    Actor.log.info(f"[prewarm] HTTP {response.status if response else '?'} -> {url}")
    await human_settle(page, fingerprint, 0.8, 1.8)
    return await wait_for_cloudflare(
        page,
        timeout_s=cf_wait_seconds,
        allow_manual=allow_manual,
        refresh_attempts=cf_refresh_attempts,
    )


async def homepage_search_then_wait(
    page,
    *,
    fingerprint: dict,
    query: str,
    location: str,
    cf_wait_seconds: int,
    allow_manual: bool,
    cf_refresh_attempts: int,
) -> bool:
    page._fingerprint = fingerprint
    Actor.log.info("[search-flow] Opening homepage for form search...")
    response = await page.goto(
        "https://www.yellowpages.com",
        wait_until="domcontentloaded",
        timeout=60_000,
    )
    Actor.log.info(f"[search-flow] HTTP {response.status if response else '?'} -> homepage")

    await human_settle(page, fingerprint, 2.0, 4.0)
    if not await wait_for_cloudflare(
        page,
        timeout_s=cf_wait_seconds,
        allow_manual=allow_manual,
        refresh_attempts=cf_refresh_attempts,
    ):
        return False

    await human_settle(page, fingerprint, 1.5, 3.0)
    if not await do_search(page, fingerprint, query, location):
        return False

    await human_settle(page, fingerprint, 1.5, 3.5)
    return await wait_for_cloudflare(
        page,
        timeout_s=cf_wait_seconds,
        allow_manual=allow_manual,
        refresh_attempts=cf_refresh_attempts,
    )


# ══════════════════════════════════════════════════════════════════════════════
#  Fingerprint / proxy / browser helpers
# ══════════════════════════════════════════════════════════════════════════════

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
    cleaned = re.sub(r"_+", "_", cleaned).strip("._") or "yp_session"
    digest = hashlib.sha1(value.encode()).hexdigest()[:8]
    prefix = cleaned[: max(1, max_length - len(digest) - 1)].rstrip("._")
    return f"{prefix}_{digest}"


def proxy_to_playwright(proxy_info):
    if not proxy_info:
        return None
    return {"server": proxy_info.url, "username": proxy_info.username, "password": proxy_info.password}


def is_apify_cloud() -> bool:
    return os.getenv("APIFY_IS_AT_HOME") == "1"


async def new_proxy_info_safe(proxy_configuration, session_id: str):
    if not proxy_configuration:
        return None
    safe_id = sanitize_proxy_session_id(session_id)
    Actor.log.info(f"Proxy session_id='{safe_id}'")
    return await proxy_configuration.new_proxy_info(session_id=safe_id)


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
  window.chrome.app = window.chrome.app || {{}};
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


async def launch_browser(playwright, *, headless: bool, proxy_info=None, fingerprint=None, prefer_chrome: bool = True):
    fingerprint = fingerprint or build_fingerprint("fallback")
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
    if prefer_chrome and not proxy:
        try:
            Actor.log.info(f"Launching installed Google Chrome headless={headless}")
            return await playwright.chromium.launch(channel="chrome", **opts)
        except Exception as e:
            Actor.log.warning(f"Chrome channel failed, using bundled Chromium: {e}")
    Actor.log.info(f"Launching Chromium headless={headless}")
    return await playwright.chromium.launch(**opts)


async def align_user_agent_with_browser(browser, fingerprint: dict) -> dict:
    try:
        major = browser.version.split("/", 1)[-1].split(".", 1)[0]
        if major.isdigit():
            fingerprint = dict(fingerprint)
            os_part = (
                "Macintosh; Intel Mac OS X 10_15_7"
                if fingerprint["platform"] == "MacIntel"
                else "Windows NT 10.0; Win64; x64"
            )
            fingerprint["user_agent"] = (
                f"Mozilla/5.0 ({os_part}) AppleWebKit/537.36 "
                f"(KHTML, like Gecko) Chrome/{major}.0.0.0 Safari/537.36"
            )
    except Exception as e:
        Actor.log.warning(f"UA align failed: {e}")
    return fingerprint


async def make_context(browser, *, fingerprint: dict | None = None, cookies=None, storage_state=None):
    viewport = random.choice([{"width": v["width"], "height": v["height"]} for v in VIEWPORTS])
    opts = {
        "viewport": viewport,
        "screen": viewport,
        "locale": "en-US",
        "timezone_id": "America/New_York",
        "color_scheme": "light",
        "java_script_enabled": True,
        "accept_downloads": False,
    }
    if storage_state:
        opts["storage_state"] = storage_state
    ctx = await browser.new_context(**opts)
    if cookies:
        await ctx.add_cookies(cookies)
    return ctx


# ══════════════════════════════════════════════════════════════════════════════
#  Storage state persistence
# ══════════════════════════════════════════════════════════════════════════════

async def load_storage_state(key: str):
    try:
        state = await Actor.get_value(key)
        if isinstance(state, dict):
            Actor.log.info(f"Loaded browser storage state from '{key}'")
            return state
    except Exception as e:
        Actor.log.warning(f"Could not load storage state: {e}")
    return None


async def save_storage_state(context, key: str):
    try:
        state = await context.storage_state()
        await Actor.set_value(key, state)
        Actor.log.info(f"Saved browser storage state to '{key}'")
    except Exception as e:
        Actor.log.warning(f"Could not save storage state: {e}")


# ══════════════════════════════════════════════════════════════════════════════
#  Request helpers
# ══════════════════════════════════════════════════════════════════════════════

async def requeue_request(request_queue, request, retries: int, reason: str):
    url = request.url
    await request_queue.add_request(
        Request.from_url(
            url,
            unique_key=f"{url}#retry-{retries+1}-{random.random()}",
            user_data={**request.user_data, "retries": retries + 1, "last_retry_reason": reason},
        ),
        forefront=True,
    )


async def safe_close_page(page):
    try:
        if not page.is_closed():
            await page.close()
    except Exception:
        pass


def parse_cookies(raw):
    if not raw:
        return []
    if isinstance(raw, list):
        return raw
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, list) else []
    except json.JSONDecodeError:
        Actor.log.warning("cloudflare_cookies is not valid JSON, ignoring.")
        return []


def homepage_url() -> str:
    """Return the real Yellow Pages homepage URL."""
    return "https://www.yellowpages.com"


# ══════════════════════════════════════════════════════════════════════════════
#  Yellow Pages — search form
# ══════════════════════════════════════════════════════════════════════════════

async def do_search(page, fingerprint: dict, query: str, location: str) -> bool:
    Actor.log.info(f"🔎 Searching for '{query}' in '{location}'")
    try:
        await page.wait_for_selector("#query", timeout=15_000)
    except Exception:
        Actor.log.warning("Search box (#query) not found.")
        return False

    await type_like_human(page, "#query", query)
    await type_like_human(page, "#location", location)

    Actor.log.info("  [search] Pausing before clicking Find...")
    await human_delay(0.8, 1.8)

    try:
        btn = page.locator("button[type='submit'][value='Find']")
        box = await btn.bounding_box()
        if box:
            await page.mouse.move(
                box["x"] + box["width"] / 2 + random.uniform(-5, 5),
                box["y"] + box["height"] / 2 + random.uniform(-3, 3),
                steps=random.randint(8, 18),
            )
            await human_delay(0.2, 0.5)
    except Exception as e:
        Actor.log.debug(f"Mouse move to button skipped: {e}")

    Actor.log.info("  [search] Clicking Find button...")
    try:
        await page.click("button[type='submit'][value='Find']", timeout=10_000)
    except Exception:
        Actor.log.warning("  Direct click failed — pressing Enter.")
        await page.press("#location", "Enter")

    Actor.log.info("  [search] Waiting for results page...")
    try:
        await page.wait_for_url("**/search**", timeout=20_000)
        Actor.log.info(f"  [search] ✅ Results URL: {page.url}")
        return True
    except Exception:
        Actor.log.warning(f"  [search] URL did not change. Current: {page.url}")
        await asyncio.sleep(3)
        return "/search" in page.url


# ══════════════════════════════════════════════════════════════════════════════
#  Yellow Pages — listing card scraper
# ══════════════════════════════════════════════════════════════════════════════

async def scrape_listings(page) -> list[dict]:
    Actor.log.info("📋 Extracting business listings from results page...")
    await human_delay(1.0, 2.0)

    listings = await page.evaluate("""
        () => {
            const results = [];
            document.querySelectorAll('.result').forEach(card => {
                const nameEl   = card.querySelector('.business-name span, .business-name');
                const name     = nameEl?.innerText?.trim() || '';
                const phone    = card.querySelector('.phones.phone.primary')?.innerText?.trim() || '';
                const street   = card.querySelector('.street-address')?.innerText?.trim() || '';
                const city     = card.querySelector('.locality')?.innerText?.trim() || '';
                const cats     = [...card.querySelectorAll('.categories a')].map(a => a.innerText.trim());
                const ratingEl = card.querySelector('.ratings span.count');
                const rating   = ratingEl?.innerText?.trim() || '';
                const website  = card.querySelector('a.track-visit-website')?.href || '';
                const yp_url   = card.querySelector('a.business-name')?.href || '';
                const snippet  = card.querySelector('.snippet')?.innerText?.trim() || '';
                const years    = card.querySelector('.years-in-business .count')?.innerText?.trim() || '';
                const open_status = card.querySelector('.open-status')?.innerText?.trim() || '';
                if (name) results.push({
                    name, phone, street, city,
                    rating, categories: cats,
                    website, yp_url, snippet,
                    years_in_business: years,
                    open_status
                });
            });
            return results;
        }
    """)

    Actor.log.info(f"  Found {len(listings)} listings on this page.")
    return listings


async def get_next_page_url(page) -> str | None:
    try:
        nxt = page.locator("a.next.ajax-page")
        if await nxt.count():
            href = await nxt.get_attribute("href")
            if href:
                return urljoin("https://www.yellowpages.com", href)
    except Exception:
        pass
    return None


async def click_next_results_page(
    page,
    fingerprint: dict,
    *,
    cf_wait_seconds: int,
    allow_manual: bool,
    cf_refresh_attempts: int,
) -> bool:
    try:
        next_link = page.locator("a.next.ajax-page, a.next, a[rel='next']").first
        if not await next_link.count():
            Actor.log.info("No next results link found.")
            return False

        old_url = page.url
        box = await next_link.bounding_box()
        if box:
            await page.mouse.move(
                box["x"] + box["width"] / 2 + random.uniform(-4, 4),
                box["y"] + box["height"] / 2 + random.uniform(-3, 3),
                steps=random.randint(10, 22),
            )
        await human_delay(0.5, 1.4)
        Actor.log.info("Clicking Yellow Pages next results link...")
        await next_link.click(timeout=15_000)

        try:
            await page.wait_for_url(lambda url: url != old_url, timeout=30_000)
        except Exception:
            await page.wait_for_load_state("domcontentloaded", timeout=30_000)

        await human_settle(page, fingerprint, 1.2, 2.8)
        return await wait_for_cloudflare(
            page,
            timeout_s=cf_wait_seconds,
            allow_manual=allow_manual,
            refresh_attempts=cf_refresh_attempts,
        )
    except Exception as e:
        Actor.log.warning(f"Could not click next results page: {e}")
        return False


# ══════════════════════════════════════════════════════════════════════════════
#  Yellow Pages — business DETAIL page scraper
# ══════════════════════════════════════════════════════════════════════════════

async def scrape_business_detail(page) -> dict:
    """
    Scrape everything available on a YP business detail page.
    Returns a dict of all fields found.
    """
    Actor.log.info("  [detail] Extracting business detail fields...")
    await human_delay(1.0, 2.0)
    await random_scroll(page)

    detail = await page.evaluate("""
        () => {
            const txt = (sel, root=document) => root.querySelector(sel)?.innerText?.trim() || '';
            const attr = (sel, a, root=document) => root.querySelector(sel)?.getAttribute(a) || '';
            const all  = (sel, root=document) => [...root.querySelectorAll(sel)].map(el => el.innerText.trim()).filter(Boolean);

            // ── Core info ──
            const name      = txt('h1.business-name, .sales-info h1, h1');
            const phone     = txt('.phone.primary, .phones');
            const address   = txt('.address');
            const street    = txt('.street-address');
            const city      = txt('.locality');
            const zip_code  = txt('.postal-code');
            const state_val = txt('.region');

            // ── Ratings ──
            const rating        = txt('.ratings .rating-stars + span, .overall-rating');
            const review_count  = txt('.reviews-count, .count');

            // ── Hours ──
            const hours_rows = [];
            document.querySelectorAll('.open-hours tr, .hours-card tr, table.hours tr').forEach(row => {
                const day  = row.querySelector('td:first-child, th')?.innerText?.trim() || '';
                const time = row.querySelector('td:last-child')?.innerText?.trim() || '';
                if (day) hours_rows.push({ day, time });
            });

            // ── Categories ──
            const categories = all('.categories a, .category a');

            // ── Website & social ──
            const website = attr('a.website-link, a.track-visit-website', 'href');
            const email   = attr('a[href^="mailto:"]', 'href').replace('mailto:', '');

            // ── About / description ──
            const about = txt('.from-the-business .description, .business-description, .general-info .description, p.description');

            // ── Amenities / extra attributes ──
            const amenities = all('.amenities-info li, .additional-info li, .extra-details li');

            // ── Payment methods ──
            const payment = all('.payment-methods li, .payments li');

            // ── Neighborhood ──
            const neighborhood = txt('.neighborhood, .neighborhoods');

            // ── Social links ──
            const socials = {};
            document.querySelectorAll('a[href*="facebook.com"], a[href*="twitter.com"], a[href*="instagram.com"], a[href*="yelp.com"]').forEach(a => {
                const href = a.href;
                if (href.includes('facebook'))  socials.facebook  = href;
                if (href.includes('twitter'))   socials.twitter   = href;
                if (href.includes('instagram')) socials.instagram = href;
                if (href.includes('yelp'))      socials.yelp      = href;
            });

            // ── Photos ──
            const photos = [...document.querySelectorAll('.photo-tile img, .gallery img, .photos img')]
                .map(img => img.src || img.getAttribute('data-src') || '')
                .filter(src => src && !src.includes('data:'));

            // ── Reviews (first page already loaded) ──
            const reviews = [];
            document.querySelectorAll('.review, .reviews .review-card, article.clearfix').forEach(r => {
                const ratingWords = { one: '1', two: '2', three: '3', four: '4', five: '5' };
                const taRating = [...r.classList].find(cls => /^ta-\\d+$/.test(cls))
                    || [...r.querySelectorAll('[class*="ta-"]')]
                        .flatMap(el => [...el.classList])
                        .find(cls => /^ta-\\d+$/.test(cls))
                    || '';
                const overallRatingEl = r.querySelector('.result-ratings.overall .rating-indicator, .rating-indicator');
                const overallRatingClass = overallRatingEl
                    ? [...overallRatingEl.classList].find(cls => ratingWords[cls])
                    : '';
                const starCount = overallRatingEl
                    ? overallRatingEl.querySelectorAll('li.rating-star').length
                    : 0;
                reviews.push({
                    reviewer : txt('.reviewer-name, .user-display-name, .author-info .name, a.author', r),
                    stars    : txt('.rating-stars, .review-stars', r)
                        || ratingWords[overallRatingClass]
                        || (starCount ? String(starCount) : '')
                        || taRating.replace('ta-', ''),
                    date     : txt('.date-descriptor, .review-date, .date-posted', r),
                    title    : txt('.review-response header, h3, .review-title', r),
                    body     : txt('.review-text, .review-body p, .review-response p', r),
                });
            });

            // ── Map / coordinates (from schema.org or meta) ──
            let lat = '', lng = '';
            document.querySelectorAll('script[type="application/ld+json"]').forEach(s => {
                try {
                    const d = JSON.parse(s.textContent);
                    if (d.geo) { lat = String(d.geo.latitude || ''); lng = String(d.geo.longitude || ''); }
                } catch(e) {}
            });

            return {
                name, phone, address, street, city, zip_code,
                state: state_val, rating, review_count,
                hours: hours_rows, categories, website, email,
                about, amenities, payment_methods: payment,
                neighborhood, social_links: socials,
                photos, reviews, latitude: lat, longitude: lng,
            };
        }
    """)

    Actor.log.info(
        f"  [detail] ✅ name='{detail.get('name','')}' "
        f"phone='{detail.get('phone','')}' "
        f"rating='{detail.get('rating','')}' "
        f"reviews={len(detail.get('reviews',[]))} "
        f"hours={len(detail.get('hours',[]))} "
        f"photos={len(detail.get('photos',[]))}"
    )
    return detail


# ══════════════════════════════════════════════════════════════════════════════
#  Main actor entrypoint
# ══════════════════════════════════════════════════════════════════════════════

async def main() -> None:
    async with Actor:
        actor_input = await Actor.get_input() or {}

        # ── Input parameters ──────────────────────────────────────────────────
        search_query      = actor_input.get("search_query", "pizza")
        search_location   = actor_input.get("search_location", "Los Angeles, CA")
        max_businesses    = max(1, int(actor_input.get("max_businesses", 50)))
        scrape_details    = bool(actor_input.get("scrape_details", True))
        max_cf_retries    = int(actor_input.get("max_cf_retries", 2))
        cf_wait_seconds   = max(45, min(300, int(actor_input.get("cf_wait_seconds", 120))))
        cf_refresh_attempts = max(0, min(8, int(actor_input.get("cf_refresh_attempts", 3))))
        headless          = bool(actor_input.get("headless", False))
        use_apify_proxy   = bool(actor_input.get("use_apify_proxy", True))
        proxy_groups      = actor_input.get("proxy_groups") or ["RESIDENTIAL"]
        proxy_country     = actor_input.get("proxy_country", "US")
        cloudflare_cookies = parse_cookies(actor_input.get("cloudflare_cookies"))
        use_homepage_search = bool(actor_input.get("use_homepage_search", True))
        page_gap_seconds = actor_input.get("page_gap_seconds", [8, 18])
        if not isinstance(page_gap_seconds, list) or len(page_gap_seconds) != 2:
            page_gap_seconds = [8, 18]
        page_gap_min = max(0.0, float(page_gap_seconds[0]))
        page_gap_max = max(page_gap_min, float(page_gap_seconds[1]))

        session_id   = str(actor_input.get("session_id") or f"yp_{search_query}_{proxy_country}")
        profile_seed = str(actor_input.get("fingerprint_seed") or session_id)
        fingerprint  = build_fingerprint(profile_seed)
        storage_key  = "BROWSER_STORAGE_STATE_" + hashlib.sha1(session_id.encode()).hexdigest()[:16]
        allow_manual = (not headless) and (not is_apify_cloud())

        Actor.log.info("═" * 60)
        Actor.log.info("  Yellow Pages Scraper")
        Actor.log.info(f"  Query       : {search_query}")
        Actor.log.info(f"  Location    : {search_location}")
        Actor.log.info(f"  Max businesses: {max_businesses}")
        Actor.log.info(f"  Scrape detail pages: {scrape_details}")
        Actor.log.info(f"  Headless    : {headless}  |  CF manual: {allow_manual}")
        Actor.log.info(f"  CF refresh attempts: {cf_refresh_attempts}")
        Actor.log.info(f"  Homepage search: {use_homepage_search}")
        Actor.log.info(f"  Page gap    : {page_gap_min:.1f}-{page_gap_max:.1f}s")
        Actor.log.info(f"  Viewport    : {fingerprint['viewport']['width']}x{fingerprint['viewport']['height']}")
        Actor.log.info(f"  Timezone    : {fingerprint['timezone_id']}")
        Actor.log.info("═" * 60)

        # ── Proxy setup ───────────────────────────────────────────────────────
        proxy_configuration = None
        if use_apify_proxy:
            try:
                proxy_configuration = await Actor.create_proxy_configuration(
                    groups=proxy_groups,
                    country_code=proxy_country,
                )
                Actor.log.info(f"Proxy: groups={proxy_groups} country={proxy_country}")
            except Exception as e:
                Actor.log.warning(f"Apify Proxy unavailable: {e}")

        # Start from the real homepage; Yellow Pages creates the search URL
        # after the actor types into the form and clicks Find.
        request_queue = await Actor.open_request_queue(name=None)
        first_search_url = homepage_url()
        await request_queue.add_request(
            Request.from_url(
                first_search_url,
                unique_key=f"{first_search_url}#homepage-search",
                user_data={
                    "stage": "results",
                    "retries": 0,
                    "page_num": 1,
                    "search_flow": "homepage",
                },
            )
        )
        Actor.log.info(f"Queued homepage search start: {first_search_url}")

        all_listings: list[dict] = []
        selected_businesses = 0

        async with async_playwright() as playwright:
            proxy_info    = await new_proxy_info_safe(proxy_configuration, session_id)
            storage_state = await load_storage_state(storage_key)
            browser       = await launch_browser(
                playwright, headless=headless,
                proxy_info=proxy_info, fingerprint=fingerprint,
            )
            context       = await make_context(
                browser,
                cookies=cloudflare_cookies, storage_state=storage_state,
            )

            handled_requests = 0
            while request := await request_queue.fetch_next_request():
                url      = request.url
                stage    = request.user_data.get("stage", "results")
                retries  = int(request.user_data.get("retries", 0))
                page_num = int(request.user_data.get("page_num", 1))
                listing  = request.user_data.get("listing", {})
                search_flow = request.user_data.get("search_flow", "direct")

                if stage == "results" and selected_businesses >= max_businesses:
                    Actor.log.info(
                        f"Skipping extra results page because max_businesses={max_businesses} is reached."
                    )
                    await request_queue.mark_request_as_handled(request)
                    handled_requests += 1
                    continue

                if handled_requests:
                    pause = random.uniform(1.0, 3.0) if stage == "detail" else random.uniform(page_gap_min, page_gap_max)
                    Actor.log.info(f"Session pause before next navigation: {pause:.1f}s")
                    await asyncio.sleep(pause)

                page     = await context.new_page()

                Actor.log.info(f"→ [{stage}] page={page_num} retry={retries}/{max_cf_retries}  {url}")

                try:
                    # ── Navigate using pre-warm strategy ─────────────────────
                    if stage == "results" and page_num == 1 and search_flow == "homepage":
                        passed = await homepage_search_then_wait(
                            page,
                            fingerprint=fingerprint,
                            query=search_query,
                            location=search_location,
                            cf_wait_seconds=cf_wait_seconds,
                            allow_manual=allow_manual,
                            cf_refresh_attempts=cf_refresh_attempts,
                        )
                    else:
                        passed = await prewarm_then_goto(
                            page, url,
                            fingerprint=fingerprint,
                            cf_wait_seconds=cf_wait_seconds,
                            allow_manual=allow_manual,
                            cf_refresh_attempts=cf_refresh_attempts,
                        )

                    if not passed:
                        if retries < max_cf_retries:
                            Actor.log.warning(f"CF not cleared — requeueing (retry {retries+1})")
                            await save_storage_state(context, storage_key)
                            await safe_close_page(page)
                            await requeue_request(request_queue, request, retries, "cloudflare")
                        else:
                            Actor.log.error("Max CF retries reached. Pushing blocked status.")
                            await Actor.push_data({
                                "status": "blocked_by_cloudflare",
                                "url": url,
                                "stage": stage,
                                "page_title": await page.title(),
                            })
                        continue

                    await human_settle(page, fingerprint, 1.0, 2.2)
                    await save_storage_state(context, storage_key)

                    # ══════════════════════════════════════════════════════════
                    #  STAGE: results  — scrape listing cards
                    # ══════════════════════════════════════════════════════════
                    if stage == "results":
                        title = await page.title()
                        Actor.log.info(f"📄 Results page {page_num}: '{title}'")

                        listings = await scrape_listings(page)
                        for biz in listings:
                            biz["search_query"]    = search_query
                            biz["search_location"] = search_location
                            biz["result_page"]     = page_num

                        remaining_slots = max_businesses - selected_businesses
                        if remaining_slots <= 0:
                            listings = []
                        elif len(listings) > remaining_slots:
                            Actor.log.info(
                                f"Keeping {remaining_slots} listings from page {page_num} "
                                f"to respect max_businesses={max_businesses}."
                            )
                            listings = listings[:remaining_slots]

                        if not listings:
                            Actor.log.warning("⚠️  No listings found — saving debug screenshot.")
                            await page.screenshot(
                                path=f"debug_results_p{page_num}.png", full_page=True
                            )
                            Actor.log.info(f"📸 Screenshot: debug_results_p{page_num}.png")
                        else:
                            Actor.log.info(
                                f"✅ {len(listings)} listings on page {page_num} "
                                f"(total so far: {len(all_listings) + len(listings)})"
                            )

                        if selected_businesses + len(listings) < max_businesses:
                            next_url = await get_next_page_url(page)
                            if not next_url:
                                Actor.log.info("No next page link found; not building a search URL.")
                                next_url = ""
                            if next_url:
                                await request_queue.add_request(
                                    Request.from_url(
                                        next_url,
                                        unique_key=f"{next_url}#p{page_num + 1}",
                                        user_data={
                                            "stage": "results",
                                            "retries": 0,
                                            "page_num": page_num + 1,
                                            "search_flow": "direct",
                                        },
                                    ),
                                    forefront=True,
                                )
                                Actor.log.info(f"Queued next results page {page_num + 1}: {next_url}")

                        # Queue detail pages if requested
                        if scrape_details:
                            for biz in listings:
                                yp_url = biz.get("yp_url", "")
                                if yp_url:
                                    selected_businesses += 1
                                    await request_queue.add_request(
                                        Request.from_url(
                                            yp_url,
                                            unique_key=f"{yp_url}#detail",
                                            user_data={
                                                "stage": "detail",
                                                "retries": 0,
                                                "page_num": 1,
                                                "listing": biz,
                                            },
                                        )
                                    )
                                    Actor.log.info(f"  Queued detail: {yp_url}")
                                else:
                                    # No detail URL — push listing as-is
                                    selected_businesses += 1
                                    all_listings.append(biz)
                                    await Actor.push_data(biz)
                        else:
                            # Push listings directly without detail scrape
                            selected_businesses += len(listings)
                            all_listings.extend(listings)
                            await Actor.push_data(listings)

                    # ══════════════════════════════════════════════════════════
                    #  STAGE: detail  — scrape full business page
                    # ══════════════════════════════════════════════════════════
                    elif stage == "detail":
                        Actor.log.info(f"🏢 Detail page: {url}")

                        detail = await scrape_business_detail(page)

                        # Merge: listing card data takes priority for core fields,
                        # detail page fills in the richer fields.
                        merged = {
                            # ── From listing card (already confirmed) ────────
                            "search_query":    listing.get("search_query", search_query),
                            "search_location": listing.get("search_location", search_location),
                            "result_page":     listing.get("result_page", 1),
                            "yp_url":          url,
                            # ── Prefer card value, fall back to detail ───────
                            "name":            listing.get("name") or detail.get("name", ""),
                            "phone":           listing.get("phone") or detail.get("phone", ""),
                            "street":          listing.get("street") or detail.get("street", ""),
                            "city":            listing.get("city") or detail.get("city", ""),
                            "categories":      listing.get("categories") or detail.get("categories", []),
                            "rating":          listing.get("rating") or detail.get("rating", ""),
                            "website":         listing.get("website") or detail.get("website", ""),
                            # ── Detail-only fields ───────────────────────────
                            "zip_code":        detail.get("zip_code", ""),
                            "state":           detail.get("state", ""),
                            "address":         detail.get("address", ""),
                            "email":           detail.get("email", ""),
                            "about":           detail.get("about", ""),
                            "hours":           detail.get("hours", []),
                            "amenities":       detail.get("amenities", []),
                            "payment_methods": detail.get("payment_methods", []),
                            "neighborhood":    detail.get("neighborhood", ""),
                            "social_links":    detail.get("social_links", {}),
                            "photos":          detail.get("photos", []),
                            "reviews":         detail.get("reviews", []),
                            "review_count":    detail.get("review_count", ""),
                            "latitude":        detail.get("latitude", ""),
                            "longitude":       detail.get("longitude", ""),
                            # ── Card-only extras ─────────────────────────────
                            "snippet":         listing.get("snippet", ""),
                            "years_in_business": listing.get("years_in_business", ""),
                            "open_status":     listing.get("open_status", ""),
                        }

                        all_listings.append(merged)
                        await Actor.push_data(merged)
                        Actor.log.info(
                            f"✅ Pushed detail for '{merged['name']}' "
                            f"(total: {len(all_listings)})"
                        )

                except Exception as e:
                    Actor.log.exception(f"Error on [{stage}] {url}: {e}")
                    if retries < max_cf_retries:
                        # Recycle browser on hard errors
                        for obj in (context, browser):
                            try:
                                await obj.close()
                            except Exception:
                                pass
                        retry_fp   = build_fingerprint(f"{profile_seed}-err-{retries+1}")
                        proxy_info = await new_proxy_info_safe(
                            proxy_configuration, f"{session_id}_err_{retries+1}"
                        )
                        browser    = await launch_browser(
                            playwright, headless=headless,
                            proxy_info=proxy_info, fingerprint=retry_fp,
                        )
                        context    = await make_context(
                            browser,
                            cookies=cloudflare_cookies, storage_state=storage_state,
                        )
                        fingerprint = retry_fp
                        await requeue_request(request_queue, request, retries, str(e)[:200])
                    else:
                        await Actor.push_data({
                            "status": "failed_after_retries",
                            "url": url, "stage": stage,
                            "retries": retries, "error": str(e),
                        })

                finally:
                    await safe_close_page(page)
                    await request_queue.mark_request_as_handled(request)
                    handled_requests += 1

            # ── Wrap up ───────────────────────────────────────────────────────
            Actor.log.info("═" * 60)
            Actor.log.info(f"🏁 Done. Total records pushed: {len(all_listings)}")
            Actor.log.info("═" * 60)
            await save_storage_state(context, storage_key)
            await context.close()
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())

