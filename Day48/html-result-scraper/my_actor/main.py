from __future__ import annotations

import asyncio
import hashlib
import json
import os
import random
import re
import sys
from datetime import datetime, timezone

from apify import Actor, Request
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

sys.stdout.reconfigure(encoding="utf-8")

CHALLENGE_TITLES = {
    "just a moment",
    "attention required",
    "attention required!",
    "please wait",
    "checking your browser",
    "one more step",
    "security check",
    "access denied",
}

SECURITY_BLOCK_SIGNATURES = {
    "eset endpoint security": "blocked_by_security_software",
    "web site blocked": "blocked_by_security_software",
    "blocked by the administrator": "blocked_by_security_software",
}

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


def build_fingerprint(seed: str) -> dict:
    digest = hashlib.sha256(seed.encode()).hexdigest()
    base = dict(FINGERPRINTS[int(digest[:2], 16) % len(FINGERPRINTS)])
    viewport = dict(VIEWPORTS[int(digest[2:4], 16) % len(VIEWPORTS)])
    base["viewport"] = viewport
    base["screen"] = {"width": viewport["width"], "height": viewport["height"]}
    base["device_scale_factor"] = viewport["device_scale_factor"]
    return base


def sanitize_session_id(value: str, *, max_length: int = 50) -> str:
    cleaned = re.sub(r"[^\w._~]+", "_", value.strip().lower())
    cleaned = re.sub(r"_+", "_", cleaned).strip("._") or "html_session"
    digest = hashlib.sha1(value.encode()).hexdigest()[:8]
    prefix = cleaned[: max(1, max_length - len(digest) - 1)].rstrip("._")
    return f"{prefix}_{digest}"


def is_challenge_title(title: str) -> bool:
    title_lower = title.lower()
    return any(signature in title_lower for signature in CHALLENGE_TITLES)


def proxy_to_playwright(proxy_info):
    if not proxy_info:
        return None
    return {
        "server": proxy_info.url,
        "username": proxy_info.username,
        "password": proxy_info.password,
    }


def stealth_init_script(fingerprint: dict) -> str:
    return f"""
(() => {{
  const fp = {json.dumps(fingerprint)};
  const def = (obj, prop, val) => {{
    try {{ Object.defineProperty(obj, prop, {{ get: () => val, configurable: true }}); }} catch (e) {{}}
  }};
  def(Navigator.prototype, 'webdriver', undefined);
  def(Navigator.prototype, 'platform', fp.platform);
  def(Navigator.prototype, 'languages', fp.languages);
  def(Navigator.prototype, 'hardwareConcurrency', fp.hardware_concurrency);
  def(Navigator.prototype, 'deviceMemory', fp.device_memory);
  def(Navigator.prototype, 'plugins', [1, 2, 3, 4, 5]);
  def(Navigator.prototype, 'mimeTypes', [1, 2, 3]);
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


async def human_delay(min_s: float = 0.6, max_s: float = 1.6) -> None:
    await asyncio.sleep(random.uniform(min_s, max_s))


async def human_mouse_wander(page, fingerprint: dict) -> None:
    viewport = fingerprint["viewport"]
    try:
        for _ in range(random.randint(2, 5)):
            if page.is_closed():
                return
            await page.mouse.move(
                random.randint(40, max(80, viewport["width"] - 80)),
                random.randint(60, max(100, viewport["height"] - 80)),
                steps=random.randint(8, 22),
            )
            await asyncio.sleep(random.uniform(0.08, 0.25))
    except Exception as exc:
        Actor.log.debug(f"Mouse movement skipped: {exc}")


async def random_scroll(page) -> None:
    try:
        for index in range(random.randint(2, 5)):
            if page.is_closed():
                return
            distance = random.randint(180, 620)
            if index and random.random() < 0.2:
                distance = -random.randint(80, 220)
            await page.mouse.wheel(0, distance)
            await asyncio.sleep(random.uniform(0.35, 1.0))
    except Exception as exc:
        Actor.log.debug(f"Scroll skipped: {exc}")


async def human_settle(page, fingerprint: dict, min_s: float = 0.8, max_s: float = 1.8) -> None:
    await human_delay(min_s, max_s)
    if random.random() < 0.85:
        await human_mouse_wander(page, fingerprint)
    if random.random() < 0.6:
        await random_scroll(page)


async def wait_for_challenge_clear(
    page,
    *,
    fingerprint: dict,
    timeout_s: int,
    refresh_attempts: int,
    allow_manual: bool,
) -> bool:
    deadline = asyncio.get_event_loop().time() + timeout_s
    refresh_count = 0
    manual_notice_shown = False

    while asyncio.get_event_loop().time() < deadline:
        try:
            title = (await page.title()).strip()
        except Exception:
            title = ""

        try:
            challenge_count = await page.locator(
                "iframe[src*='challenges.cloudflare.com'],"
                "iframe[src*='hcaptcha.com'],"
                "iframe[src*='turnstile'],"
                "div#challenge-form,"
                "div#cf-challenge-running,"
                "[data-callback='onCaptchaSuccess']"
            ).count()
        except Exception as exc:
            Actor.log.warning(f"Challenge check failed: {exc}")
            return False

        if challenge_count:
            if not allow_manual:
                Actor.log.warning("Interactive challenge detected while manual solving is disabled.")
                return False
            if not manual_notice_shown:
                Actor.log.warning("Manual challenge detected. Solve it in the visible browser window.")
                manual_notice_shown = True
            await asyncio.sleep(2)
            continue

        if not is_challenge_title(title):
            Actor.log.info(f"Challenge check passed with title: {title!r}")
            return True

        if refresh_count >= refresh_attempts:
            Actor.log.warning(f"Challenge title still present after {refresh_count} refresh attempts: {title!r}")
            return False

        refresh_count += 1
        Actor.log.warning(f"Challenge title detected: {title!r}. Refresh attempt {refresh_count}/{refresh_attempts}.")
        await human_settle(page, fingerprint, 1.5, 3.5)
        await asyncio.sleep(random.uniform(1.0, 3.0))
        try:
            await page.reload(wait_until="domcontentloaded", timeout=45_000)
            await asyncio.sleep(random.uniform(3.0, 6.0))
        except Exception as exc:
            Actor.log.debug(f"Refresh failed: {exc}")

    Actor.log.warning("Timed out waiting for challenge to clear.")
    return False


async def launch_browser(playwright, *, headless: bool, proxy_info=None):
    args = [
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
        "--disable-blink-features=AutomationControlled",
    ]
    options = {"headless": headless, "args": args}
    proxy = proxy_to_playwright(proxy_info)
    if proxy:
        options["proxy"] = proxy

    if not proxy:
        try:
            Actor.log.info(f"Launching installed Google Chrome headless={headless}")
            return await playwright.chromium.launch(channel="chrome", **options)
        except Exception as exc:
            Actor.log.warning(f"Chrome channel failed, using bundled Chromium: {exc}")

    Actor.log.info(f"Launching Chromium headless={headless}")
    return await playwright.chromium.launch(**options)


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
    except Exception as exc:
        Actor.log.debug(f"User-agent alignment skipped: {exc}")
    return fingerprint


async def make_context(browser, *, fingerprint: dict, storage_state=None):
    viewport = {
        "width": fingerprint["viewport"]["width"],
        "height": fingerprint["viewport"]["height"],
    }
    options = {
        "user_agent": fingerprint["user_agent"],
        "viewport": viewport,
        "screen": viewport,
        "device_scale_factor": fingerprint["device_scale_factor"],
        "locale": fingerprint["locale"],
        "timezone_id": fingerprint["timezone_id"],
        "color_scheme": "light",
        "java_script_enabled": True,
        "accept_downloads": False,
        "extra_http_headers": {
            "Accept-Language": ",".join(fingerprint["languages"]) + ";q=0.9",
            "Upgrade-Insecure-Requests": "1",
        },
    }
    if storage_state:
        options["storage_state"] = storage_state

    context = await browser.new_context(**options)
    await context.add_init_script(stealth_init_script(fingerprint))
    return context


async def load_storage_state(key: str):
    try:
        state = await Actor.get_value(key)
        if isinstance(state, dict):
            Actor.log.info(f"Loaded browser storage state from {key!r}")
            return state
    except Exception as exc:
        Actor.log.debug(f"Storage state load skipped: {exc}")
    return None


async def save_storage_state(context, key: str) -> None:
    try:
        await Actor.set_value(key, await context.storage_state())
        Actor.log.info(f"Saved browser storage state to {key!r}")
    except Exception as exc:
        Actor.log.debug(f"Storage state save skipped: {exc}")


async def new_proxy_info_safe(proxy_configuration, session_id: str):
    if not proxy_configuration:
        return None
    safe_id = sanitize_session_id(session_id)
    Actor.log.info(f"Proxy session_id={safe_id!r}")
    return await proxy_configuration.new_proxy_info(session_id=safe_id)


async def requeue_request(request_queue, request, retries: int, reason: str) -> None:
    await request_queue.add_request(
        Request.from_url(
            request.url,
            unique_key=f"{request.url}#retry-{retries + 1}-{random.random()}",
            user_data={**request.user_data, "retries": retries + 1, "last_retry_reason": reason},
        ),
        forefront=True,
    )


def normalize_start_urls(start_urls: list[dict | str]) -> list[str]:
    urls = []
    for item in start_urls:
        url = item.get("url") if isinstance(item, dict) else str(item)
        if not url:
            continue
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"
        urls.append(url)
    return urls


def trim_html(html: str, max_html_chars: int) -> tuple[str, bool]:
    if max_html_chars and len(html) > max_html_chars:
        return html[:max_html_chars], True
    return html, False


def classify_result(title: str, html: str, http_status: int | None) -> tuple[str, str]:
    probe = f"{title}\n{html[:3000]}".lower()
    for signature, status in SECURITY_BLOCK_SIGNATURES.items():
        if signature in probe:
            return status, signature
    if http_status and http_status >= 400:
        return "http_error", f"http_{http_status}"
    return "ok", ""


async def scrape_html(page, url: str, *, fingerprint: dict, wait_until: str, page_wait_seconds: int) -> tuple[dict, str]:
    response = await page.goto(url, wait_until=wait_until, timeout=75_000)
    await human_settle(page, fingerprint, 0.8, 1.8)
    if page_wait_seconds:
        await asyncio.sleep(page_wait_seconds)

    html = await page.content()
    metadata = {
        "loaded_url": page.url,
        "http_status": response.status if response else None,
        "title": await page.title(),
    }
    return metadata, html


async def main() -> None:
    async with Actor:
        actor_input = await Actor.get_input() or {}
        start_urls = normalize_start_urls(
            actor_input.get(
                "start_urls",
                [
                    {"url": "http://www.punchrestaurant.com/"},
                    {"url": "http://www.damarino.com/"},
                ],
            )
        )

        if not start_urls:
            Actor.log.info("No start URLs specified. Exiting.")
            return

        headless = bool(actor_input.get("headless", True))
        wait_until = actor_input.get("wait_until", "domcontentloaded")
        page_wait_seconds = int(actor_input.get("page_wait_seconds", 2))
        max_retries = int(actor_input.get("max_retries", 2))
        cf_wait_seconds = int(actor_input.get("cf_wait_seconds", 90))
        cf_refresh_attempts = int(actor_input.get("cf_refresh_attempts", 2))
        max_html_chars = int(actor_input.get("max_html_chars", 0))
        use_apify_proxy = bool(actor_input.get("use_apify_proxy", False))
        proxy_groups = actor_input.get("proxy_groups") or ["RESIDENTIAL"]
        proxy_country = (actor_input.get("proxy_country") or "US").upper()
        session_seed = actor_input.get("session_id") or f"html-{random.randint(100000, 999999)}"
        fingerprint_seed = actor_input.get("fingerprint_seed") or session_seed
        allow_manual = not headless

        fingerprint = build_fingerprint(fingerprint_seed)
        storage_key = f"BROWSER_STORAGE_STATE_{sanitize_session_id(session_seed)}"

        Actor.log.info("=" * 60)
        Actor.log.info("HTML Result Scraper")
        Actor.log.info(f"URLs: {len(start_urls)}")
        Actor.log.info(f"Headless: {headless}")
        Actor.log.info(f"Proxy: {use_apify_proxy}")
        Actor.log.info(f"Viewport: {fingerprint['viewport']['width']}x{fingerprint['viewport']['height']}")
        Actor.log.info("=" * 60)

        proxy_configuration = None
        if use_apify_proxy:
            try:
                proxy_configuration = await Actor.create_proxy_configuration(
                    groups=proxy_groups,
                    country_code=proxy_country,
                )
            except Exception as exc:
                Actor.log.warning(f"Apify Proxy unavailable: {exc}")

        request_queue = await Actor.open_request_queue(name=None)
        for url in start_urls:
            await request_queue.add_request(Request.from_url(url, user_data={"retries": 0}))
            Actor.log.info(f"Queued {url}")

        async with async_playwright() as playwright:
            proxy_info = await new_proxy_info_safe(proxy_configuration, session_seed)
            storage_state = await load_storage_state(storage_key)
            browser = await launch_browser(playwright, headless=headless, proxy_info=proxy_info)
            fingerprint = await align_user_agent_with_browser(browser, fingerprint)
            context = await make_context(browser, fingerprint=fingerprint, storage_state=storage_state)

            handled = 0
            while request := await request_queue.fetch_next_request():
                page = await context.new_page()
                retries = int(request.user_data.get("retries", 0))
                url = request.url

                try:
                    if handled:
                        pause = random.uniform(1.0, 3.5)
                        Actor.log.info(f"Waiting {pause:.1f}s before next URL.")
                        await asyncio.sleep(pause)

                    Actor.log.info(f"Fetching {url} retry={retries}/{max_retries}")
                    page._fingerprint = fingerprint
                    metadata, html = await scrape_html(
                        page,
                        url,
                        fingerprint=fingerprint,
                        wait_until=wait_until,
                        page_wait_seconds=page_wait_seconds,
                    )

                    challenge_clear = await wait_for_challenge_clear(
                        page,
                        fingerprint=fingerprint,
                        timeout_s=cf_wait_seconds,
                        refresh_attempts=cf_refresh_attempts,
                        allow_manual=allow_manual,
                    )
                    if not challenge_clear:
                        if retries < max_retries:
                            await save_storage_state(context, storage_key)
                            await requeue_request(request_queue, request, retries, "challenge_not_cleared")
                            continue
                        await Actor.push_data(
                            {
                                "url": url,
                                "loaded_url": page.url,
                                "status": "blocked_by_challenge",
                                "title": await page.title(),
                                "html": html,
                                "html_length": len(html),
                                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                            }
                        )
                        continue

                    html = await page.content()
                    saved_html, was_truncated = trim_html(html, max_html_chars)
                    title = await page.title()
                    status, block_reason = classify_result(title, html, metadata["http_status"])
                    await save_storage_state(context, storage_key)

                    await Actor.push_data(
                        {
                            "url": url,
                            "loaded_url": page.url,
                            "status": status,
                            "block_reason": block_reason,
                            "http_status": metadata["http_status"],
                            "title": title,
                            "html": saved_html,
                            "html_length": len(html),
                            "html_truncated": was_truncated,
                            "retrieved_at": datetime.now(timezone.utc).isoformat(),
                        }
                    )
                    Actor.log.info(f"Saved HTML for {url} ({len(html)} chars).")

                except PlaywrightTimeoutError as exc:
                    Actor.log.warning(f"Timeout while fetching {url}: {exc}")
                    if retries < max_retries:
                        await requeue_request(request_queue, request, retries, "timeout")
                    else:
                        await Actor.push_data(
                            {
                                "url": url,
                                "status": "failed_after_retries",
                                "error": str(exc),
                                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                            }
                        )
                except Exception as exc:
                    Actor.log.exception(f"Error while fetching {url}: {exc}")
                    if retries < max_retries:
                        await requeue_request(request_queue, request, retries, str(exc)[:200])
                    else:
                        await Actor.push_data(
                            {
                                "url": url,
                                "status": "failed_after_retries",
                                "error": str(exc),
                                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                            }
                        )
                finally:
                    try:
                        await page.close()
                    except Exception:
                        pass
                    await request_queue.mark_request_as_handled(request)
                    handled += 1

            await save_storage_state(context, storage_key)
            await context.close()
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
