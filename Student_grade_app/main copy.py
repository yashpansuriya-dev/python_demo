from __future__ import annotations

import asyncio
import hashlib
import json
import os
import random
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

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
    # selectors = [
    #     "button[aria-label='Dismiss']",
    #     "button[aria-label='Close']",
    #     "button.contextual-sign-in-modal__modal-dismiss",
    #     "button.modal__dismiss",
    #     "button:has-text('Dismiss')",
    #     "button:has-text('Close')",
    # ]
    selector = "button.modal__dismiss svg"
    # button = page.locator(selector).first
    try:
        button = page.locator(selector).first
        if await button.count() and await button.is_visible(timeout=1200):
            await button.click()
            await human_delay(0.6, 1.2)
            return
    except Exception:
        Actor.log.info("close button didnt clicked")

    # for selector in selectors:
    #     try:
    #         button = page.locator(selector).first
    #         if await button.count() and await button.is_visible(timeout=1200):
    #             await button.click()
    #             await human_delay(0.6, 1.2)
    #             return
    #     except Exception:
    #         continue


async def click_first_visible(page, selectors: list[str], timeout_ms: int = 2500) -> bool:
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if await locator.count() and await locator.is_visible(timeout=timeout_ms):
                box = await locator.bounding_box()
                if box:
                    await page.mouse.move(
                        box["x"] + box["width"] / 2 + random.uniform(-5, 5),
                        box["y"] + box["height"] / 2 + random.uniform(-3, 3),
                        steps=random.randint(8, 18),
                    )
                    await human_delay(0.2, 0.5)
                await locator.click()
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
        "This LinkedIn Page isn’t available"
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


async def login_if_needed(page, email: str, password: str, fingerprint: dict) -> None:
    if not email or not password:
        raise RuntimeError("LinkedIn credentials are required. Add LINKEDIN_EMAIL and LINKEDIN_PASSWORD to .env or Actor input.")

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

    Actor.log.info("Signing in to LinkedIn.")
    await type_like_human(page, user_selector, email)
    await type_like_human(page, pass_selector, password)
    await click_first_visible(page, ["button[type='submit']", "span:has-text('Sign in')"], timeout_ms=5000)
    await page.wait_for_load_state("domcontentloaded", timeout=60000)
    await human_settle(page, fingerprint, 3.0, 5.5)

    body_text = ""
    try:
        body_text = (await page.locator("body").inner_text(timeout=4000)).lower()
    except Exception:
        pass
    if any(token in body_text for token in ["security verification", "quick security check", "enter the code", "captcha"]):
        raise RuntimeError("LinkedIn requested security verification. Run headful and complete the challenge manually, then rerun.")


async def save_storage_state(context) -> None:
    try:
        await Actor.set_value(STORAGE_STATE_KEY, await context.storage_state())
    except Exception as exc:
        Actor.log.warning(f"Could not save LinkedIn storage state: {exc}")


async def extract_employees(page, company_url: str) -> list[dict]:
    return await page.evaluate(
        """
({ companyUrl }) => {
  const clean = (value) => (value || '').replace(/\\s+/g, ' ').trim();
  const abs = (href) => {
    try { return new URL(href, location.href).toString().split('?')[0]; }
    catch (e) { return href || ''; }
  };

  const directText = (node) => {
    if (!node) return '';
    return clean(
      Array.from(node.childNodes)
        .filter((child) => child.nodeType === Node.TEXT_NODE)
        .map((child) => child.textContent)
        .join(' ')
    );
  };

  const findCard = (anchor) => {
    let node = anchor;
    for (let i = 0; node && i < 10; i += 1) {
      const text = clean(node.innerText || '');
      if (
        node.querySelector &&
        node.querySelector('img[alt]') &&
        node.querySelector('a[href*="/in/"]') &&
        text.length > 10 &&
        text.length < 1200
      ) {
        return node;
      }
      node = node.parentElement;
    }
    return anchor.closest('li, .org-people-profile-card, .reusable-search__result-container, div');
  };

  const anchors = Array.from(document.querySelectorAll('main a[href*="/in/"], a[href*="/in/"]'))
    .filter((anchor) => {
      const href = anchor.getAttribute('href') || '';
      const text = clean(anchor.innerText || anchor.textContent || '');
      const aria = clean(anchor.getAttribute('aria-label') || '');
      if (!href.includes('/in/')) return false;
      if (href.includes('/learning/') || href.includes('/sales/')) return false;
      if (/status is offline/i.test(text) || /status is offline/i.test(aria)) return false;
      return true;
    });

  const seen = new Set();
  const results = [];

  for (const anchor of anchors) {
    const url = abs(anchor.getAttribute('href'));
    if (!url || seen.has(url)) continue;

    const card = findCard(anchor);
    if (!card) continue;

    const image = card.querySelector('img[alt]');
    const imageName = clean(image ? image.getAttribute('alt') : '').replace(/^View\\s+/, '');
    const anchorName = directText(anchor) || clean(anchor.querySelector('span[aria-hidden="true"]')?.textContent);
    const name = imageName || anchorName;
    if (!name || /status is offline/i.test(name) || /connect$/i.test(name)) continue;

    const infoContainer = anchor.closest('p')?.parentElement || card;
    const lineNodes = Array.from(infoContainer.querySelectorAll('p, div'))
      .map((node) => clean(node.innerText || node.textContent || ''))
      .filter(Boolean)
      .filter((line) => line !== name)
      .filter((line) => !line.includes('Verified'))
      .filter((line) => !/^Connect$/i.test(line))
      .filter((line) => !/^Invite .* to connect$/i.test(line))
      .map((line) => line.replace(/^.*?\\s+•\\s+\\d+(st|nd|rd|th)$/i, '').trim())
      .filter(Boolean);

    const uniqueLines = [];
    for (const line of lineNodes) {
      if (!uniqueLines.includes(line) && line !== name) uniqueLines.push(line);
    }

    const likelyLines = uniqueLines.filter((line) => {
      if (/\\b(connect|message|follow|invite|verified|status is offline)\\b/i.test(line)) return false;
      if (line.length > 220) return false;
      return true;
    });

    const designation = likelyLines[0] || '';
    const location = likelyLines[1] || '';

    if (!designation && !location && !imageName) continue;
    seen.add(url);
    results.push({
      name,
      designation,
      location,
      url,
      company_url: companyUrl
    });
  }

  return results;
}
""",
        {"companyUrl": company_url},
    )


# async def extract_employees_2(page, company_url: str) -> list[dict]:
#     cards = 


async def extract_employees(page, company_url: str) -> list[dict]:
    return await page.evaluate(
        """
({ companyUrl }) => {
  const clean = (value) => (value || '').replace(/\\s+/g, ' ').trim();
  const abs = (href) => {
    try { return new URL(href, location.href).toString().split('?')[0]; }
    catch (e) { return href || ''; }
  };
  const directText = (node) => {
    if (!node) return '';
    return clean(
      Array.from(node.childNodes)
        .filter((child) => child.nodeType === Node.TEXT_NODE)
        .map((child) => child.textContent)
        .join(' ')
    );
  };
  const escapeRegex = (value) => value.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&');
  const stripConnectionPrefix = (line, name) => {
    let value = clean(line).replace(/Verified/g, '').trim();
    value = value.replace(
      new RegExp('^' + escapeRegex(name) + '\\\\s*(\\\\u2022|•)\\\\s*\\\\d+(st|nd|rd|th)\\\\+?', 'i'),
      ''
    ).trim();
    value = value.replace(/^\\s*(\\u2022|•)\\s*\\d+(st|nd|rd|th)\\+?\\s*/i, '').trim();
    value = value.replace(/^\\d+(st|nd|rd|th)\\+?\\s*/i, '').trim();
    return clean(value);
  };
  const findCard = (anchor) => {
    let node = anchor;
    for (let i = 0; node && i < 10; i += 1) {
      const text = clean(node.innerText || '');
      if (
        node.querySelector &&
        node.querySelector('a[href*="/in/"]') &&
        node.querySelectorAll('p').length >= 2 &&
        text.length > 10 &&
        text.length < 1200
      ) {
        return node;
      }
      node = node.parentElement;
    }
    return anchor.closest('li, .org-people-profile-card, .reusable-search__result-container, div');
  };
  const anchors = Array.from(document.querySelectorAll('main a[href*="/in/"], a[href*="/in/"]'))
    .filter((anchor) => {
      const href = anchor.getAttribute('href') || '';
      const text = clean(anchor.innerText || anchor.textContent || '');
      const aria = clean(anchor.getAttribute('aria-label') || '');
      if (!href.includes('/in/')) return false;
      if (href.includes('/learning/') || href.includes('/sales/')) return false;
      if (/status is offline/i.test(text) || /status is offline/i.test(aria)) return false;
      return true;
    });
  const seen = new Set();
  const results = [];
  for (const anchor of anchors) {
    const url = abs(anchor.getAttribute('href'));
    if (!url || seen.has(url)) continue;
    const card = findCard(anchor);
    if (!card) continue;
    const image = card.querySelector('img[alt]');
    const imageName = clean(image ? image.getAttribute('alt') : '').replace(/^View\\s+/, '');
    const anchorName = directText(anchor) || clean(anchor.querySelector('span[aria-hidden="true"]')?.textContent);
    const name = (anchorName || imageName).replace(/\\s*(\\u2022|•)\\s*\\d+(st|nd|rd|th)\\+?.*$/i, '').trim();
    if (!name || /status is offline/i.test(name) || /connect$/i.test(name)) continue;
    const nameParagraph = anchor.closest('p');
    const infoContainer = nameParagraph?.parentElement || card;
    const lineNodes = Array.from(infoContainer.querySelectorAll('p'))
      .filter((node) => node !== nameParagraph)
      .map((node) => stripConnectionPrefix(node.innerText || node.textContent || '', name))
      .filter(Boolean)
      .filter((line) => line !== name)
      .filter((line) => !/^Connect$/i.test(line))
      .filter((line) => !/^Invite .* to connect$/i.test(line));
    const uniqueLines = [];
    for (const line of lineNodes) {
      if (!uniqueLines.includes(line)) uniqueLines.push(line);
    }
    const likelyLines = uniqueLines.filter((line) => {
      if (/\\b(connect|message|follow|invite|verified|status is offline)\\b/i.test(line)) return false;
      if (line.length > 220) return false;
      return true;
    });
    const designation = likelyLines[0] || '';
    const location = designation.split(' ').pop() || '';
    if (!designation && !location && !imageName) continue;
    seen.add(url);
    results.push({
      name,
      designation,
      location,
      url,
      company_url: companyUrl
    });
  }
  return results;
}
""",
        {"companyUrl": company_url},
    )


async def extract_employees(page, company_url: str) -> list[dict]:
    return await page.evaluate(
        """
({ companyUrl }) => {
  const clean = (value) => (value || '').replace(/\\s+/g, ' ').trim();
  const abs = (href) => {
    try { return new URL(href, location.href).toString().split('?')[0]; }
    catch (e) { return href || ''; }
  };
  const directText = (node) => {
    if (!node) return '';
    return clean(
      Array.from(node.childNodes)
        .filter((child) => child.nodeType === Node.TEXT_NODE)
        .map((child) => child.textContent)
        .join(' ')
    );
  };
  const stripNoise = (line, name) => {
    let value = clean(line).replace(/Verified/g, '').trim();
    value = value.replace(new RegExp('^' + name.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&'), 'i'), '').trim();
    value = value.replace(/^\\s*(\\u2022|•|â€¢)\\s*\\d+(st|nd|rd|th)\\+?\\s*/i, '').trim();
    value = value.replace(/^\\d+(st|nd|rd|th)\\+?\\s*/i, '').trim();
    return clean(value);
  };
  const findCard = (anchor) => {
    let node = anchor;
    for (let i = 0; node && i < 12; i += 1) {
      if (node.querySelector) {
        const text = clean(node.innerText || '');
        const profileLinks = node.querySelectorAll('a[href*="/in/"]').length;
        if (profileLinks >= 1 && text.length > 20 && text.length < 1500) {
          const lines = text.split('\\n').map(clean).filter(Boolean);
          if (lines.length >= 2) return node;
        }
      }
      node = node.parentElement;
    }
    return anchor.closest('li, .org-people-profile-card, .reusable-search__result-container, div');
  };
  const anchors = Array.from(document.querySelectorAll('a[href*="/in/"]'))
    .filter((anchor) => {
      const href = anchor.getAttribute('href') || '';
      const text = clean(anchor.innerText || anchor.textContent || '');
      const aria = clean(anchor.getAttribute('aria-label') || '');
      if (!href.includes('/in/')) return false;
      if (href.includes('/learning/') || href.includes('/sales/')) return false;
      if (/status is offline/i.test(text) || /status is offline/i.test(aria)) return false;
      return true;
    });
  const seen = new Set();
  const results = [];
  for (const anchor of anchors) {
    const url = abs(anchor.getAttribute('href'));
    if (!url || seen.has(url)) continue;
    const card = findCard(anchor);
    if (!card) continue;

    const image = card.querySelector('img[alt]');
    const imageName = clean(image ? image.getAttribute('alt') : '').replace(/^View\\s+/, '');
    const anchorName = directText(anchor) || clean(anchor.querySelector('span[aria-hidden="true"]')?.textContent);
    const name = (anchorName || imageName)
      .replace(/\\s*(\\u2022|•|â€¢)\\s*\\d+(st|nd|rd|th)\\+?.*$/i, '')
      .trim();
    if (!name || /status is offline|connect|message|follow/i.test(name)) continue;

    const rawLines = clean(card.innerText || '')
      .split('\\n')
      .map(clean)
      .filter(Boolean);
    const lines = [];
    for (const rawLine of rawLines) {
      const line = stripNoise(rawLine, name);
      if (!line) continue;
      if (line === name) continue;
      if (/^(connect|message|follow)$/i.test(line)) continue;
      if (/^invite .* to connect$/i.test(line)) continue;
      if (/status is offline/i.test(line)) continue;
      if (line.length > 220) continue;
      if (!lines.includes(line)) lines.push(line);
    }

    let designation = lines[0] || '';
    let location = lines[1] || '';

    const nameParagraph = anchor.closest('p');
    const infoContainer = nameParagraph?.parentElement;
    if (infoContainer) {
      const paragraphLines = Array.from(infoContainer.querySelectorAll('p'))
        .filter((node) => node !== nameParagraph)
        .map((node) => stripNoise(node.innerText || node.textContent || '', name))
        .filter(Boolean)
        .filter((line) => !/^(connect|message|follow)$/i.test(line));
      if (paragraphLines[0]) designation = paragraphLines[0];
      if (paragraphLines[1]) location = paragraphLines[1];
    }

    if (!designation && !location && !imageName) continue;
    seen.add(url);
    results.push({
      name,
      designation,
      location,
      url,
      company_url: companyUrl
    });
  }
  return results;
}
""",
        {"companyUrl": company_url},
    )


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
    return await click_first_visible(
        page,
        [
            "button[aria-label='Next']",
            "button[aria-label*='Next']",
            ".artdeco-pagination__button--next:not([disabled])",
            "li.artdeco-pagination__indicator--number.active + li button",
        ],
        timeout_ms=2000,
    )


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
            for item in new_items:
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
                await go_to_people_page(page, company_url, fingerprint)
                await login_if_needed(page, email, password, fingerprint)
                if "/people" not in page.url:
                    await page.goto(urljoin(company_url.rstrip("/") + "/", "people/"), wait_until="domcontentloaded")
                    await human_settle(page, fingerprint, 1.5, 3.0)
                await save_storage_state(context)
                total = await scrape_people(page, company_url, fingerprint, max_pages)
                Actor.log.info(f"Finished. Total employees saved: {total}")
            finally:
                await context.close()
                await browser.close()

