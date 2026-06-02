from __future__ import annotations

import asyncio
import hashlib
import json
import os
import random
import re
from html import unescape
from urllib.parse import urljoin, urlparse, urlunparse

from apify import Actor, Request
from playwright.async_api import async_playwright


CF_TITLES = {
    "just a moment",
    "attention required",
    "please wait",
    "checking your browser",
    "security check",
    "access denied",
}

VIEWPORTS = [
    {"width": 1280, "height": 720, "device_scale_factor": 1},
    {"width": 1366, "height": 768, "device_scale_factor": 1},
    {"width": 1440, "height": 900, "device_scale_factor": 1},
    {"width": 1536, "height": 864, "device_scale_factor": 1},
]

FINGERPRINTS = [
    {
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
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
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
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

SOCIAL_DOMAINS = {
    "facebook.com": "facebook",
    "instagram.com": "instagram",
    "linkedin.com": "linkedin",
    "twitter.com": "twitter",
    "x.com": "twitter",
    "youtube.com": "youtube",
    "youtu.be": "youtube",
    "tiktok.com": "tiktok",
    "pinterest.com": "pinterest",
    "threads.net": "threads",
    "github.com": "github",
    "medium.com": "medium",
}

CONTACT_KEYWORDS = (
    "contact",
    "contact-us",
    "about",
    "about-us",
    "team",
    "staff",
    "leadership",
    "support",
    "customer-service",
    "location",
    "locations",
    "office",
    "offices",
    "privacy",
)

EMAIL_RE = re.compile(r"(?<![\w.+-])[\w.+-]{1,64}@[\w.-]+\.[A-Za-z]{2,24}(?![\w.-])")
PHONE_RE = re.compile(
    r"(?:(?:\+|00)\d{1,3}[\s().-]*)?(?:\(?\d{2,4}\)?[\s().-]*){2,5}\d{2,4}"
)


def clean_url(raw_url: str) -> str:
    raw_url = (raw_url or "").strip()
    if not raw_url:
        return ""
    if not raw_url.startswith(("http://", "https://")):
        raw_url = "https://" + raw_url
    parsed = urlparse(raw_url)
    return urlunparse((parsed.scheme, parsed.netloc.lower(), parsed.path or "/", "", parsed.query, ""))


def root_url(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}/"


def same_domain(url: str, base_url: str) -> bool:
    return urlparse(url).netloc.lower().removeprefix("www.") == urlparse(base_url).netloc.lower().removeprefix("www.")


def unique(values: list[str], limit: int | None = None) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        value = re.sub(r"\s+", " ", (value or "").strip())
        if not value:
            continue
        key = value.lower().rstrip("/#")
        if key not in seen:
            seen.add(key)
            output.append(value)
            if limit and len(output) >= limit:
                break
    return output


def build_fingerprint(seed: str) -> dict:
    digest = hashlib.sha256(seed.encode()).hexdigest()
    fp = dict(FINGERPRINTS[int(digest[:2], 16) % len(FINGERPRINTS)])
    viewport = dict(VIEWPORTS[int(digest[2:4], 16) % len(VIEWPORTS)])
    fp["viewport"] = viewport
    fp["screen"] = {"width": viewport["width"], "height": viewport["height"]}
    fp["device_scale_factor"] = viewport["device_scale_factor"]
    return fp


def proxy_to_playwright(proxy_info):
    if not proxy_info:
        return None
    return {"server": proxy_info.url, "username": proxy_info.username, "password": proxy_info.password}


def sanitize_session_id(value: str, *, max_length: int = 50) -> str:
    cleaned = re.sub(r"[^\w._~]+", "_", value.strip().lower())
    cleaned = re.sub(r"_+", "_", cleaned).strip("._") or "contact_session"
    digest = hashlib.sha1(value.encode()).hexdigest()[:8]
    prefix = cleaned[: max(1, max_length - len(digest) - 1)].rstrip("._")
    return f"{prefix}_{digest}"


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


def parse_bool(value, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y", "on"}:
            return True
        if normalized in {"false", "0", "no", "n", "off", ""}:
            return False
    return bool(value)


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
  def(Navigator.prototype, 'plugins', [1, 2, 3, 4, 5]);
  def(Navigator.prototype, 'mimeTypes', [1, 2, 3]);
  window.chrome = window.chrome || {{}};
  window.chrome.runtime = window.chrome.runtime || {{}};
  const gp = WebGLRenderingContext.prototype.getParameter;
  WebGLRenderingContext.prototype.getParameter = function(p) {{
    if (p === 37445) return fp.webgl_vendor;
    if (p === 37446) return fp.webgl_renderer;
    return gp.call(this, p);
  }};
  def(screen, 'width', fp.screen.width);
  def(screen, 'height', fp.screen.height);
  def(screen, 'availWidth', fp.screen.width);
  def(screen, 'availHeight', fp.screen.height - 40);
}})();
"""


async def human_delay(min_s: float = 0.5, max_s: float = 1.4) -> None:
    await asyncio.sleep(random.uniform(min_s, max_s))


async def human_settle(page, fingerprint: dict, min_s: float = 0.7, max_s: float = 1.8) -> None:
    await human_delay(min_s, max_s)
    try:
        vp = fingerprint["viewport"]
        for _ in range(random.randint(2, 4)):
            await page.mouse.move(
                random.randint(40, max(80, vp["width"] - 80)),
                random.randint(60, max(100, vp["height"] - 80)),
                steps=random.randint(8, 18),
            )
            await asyncio.sleep(random.uniform(0.05, 0.2))
        if random.random() < 0.7:
            await page.mouse.wheel(0, random.randint(250, 700))
            await asyncio.sleep(random.uniform(0.4, 1.0))
    except Exception as exc:
        Actor.log.debug(f"Human settle skipped: {exc}")


def is_cloudflare_title(title: str) -> bool:
    return any(token in title.lower() for token in CF_TITLES)


async def wait_for_cloudflare(page, *, timeout_s: int, refresh_attempts: int, allow_manual: bool) -> bool:
    deadline = asyncio.get_event_loop().time() + timeout_s
    attempts = 0
    while asyncio.get_event_loop().time() < deadline:
        title = ""
        try:
            title = (await page.title()).strip()
            challenge_count = await page.locator(
                "iframe[src*='challenges.cloudflare.com'], iframe[src*='hcaptcha.com'], "
                "div#challenge-form, div#cf-challenge-running"
            ).count()
        except Exception:
            challenge_count = 0

        if challenge_count and allow_manual:
            Actor.log.warning("Cloudflare checkbox detected. Complete it in the visible browser window.")
            await asyncio.sleep(2)
            continue
        if not challenge_count and not is_cloudflare_title(title):
            return True
        if attempts >= refresh_attempts:
            return False

        attempts += 1
        Actor.log.warning(f"Cloudflare-like page detected: title='{title}', refresh {attempts}/{refresh_attempts}")
        await human_delay(2.0, 5.0)
        try:
            await page.reload(wait_until="domcontentloaded", timeout=45_000)
        except Exception as exc:
            Actor.log.debug(f"Cloudflare reload failed: {exc}")
    return False


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
        return await playwright.chromium.launch(channel="chrome", **opts)
    except Exception:
        return await playwright.chromium.launch(**opts)


async def make_context(browser, *, fingerprint: dict, cookies=None, storage_state=None):
    viewport = {"width": fingerprint["viewport"]["width"], "height": fingerprint["viewport"]["height"]}
    context_options = {
        "viewport": viewport,
        "screen": viewport,
        "user_agent": fingerprint["user_agent"],
        "locale": fingerprint["locale"],
        "timezone_id": fingerprint["timezone_id"],
        "color_scheme": "light",
        "java_script_enabled": True,
        "accept_downloads": False,
    }
    if storage_state:
        context_options["storage_state"] = storage_state
    context = await browser.new_context(**context_options)
    await context.add_init_script(stealth_init_script(fingerprint))
    await context.set_extra_http_headers(
        {
            "Accept-Language": "en-US,en;q=0.9",
            "Upgrade-Insecure-Requests": "1",
        }
    )
    if cookies:
        await context.add_cookies(cookies)
    return context


async def load_storage_state(key: str):
    try:
        state = await Actor.get_value(key)
        return state if isinstance(state, dict) else None
    except Exception as exc:
        Actor.log.debug(f"Could not load browser storage state: {exc}")
        return None


async def save_storage_state(context, key: str) -> None:
    try:
        await Actor.set_value(key, await context.storage_state())
    except Exception as exc:
        Actor.log.debug(f"Could not save browser storage state: {exc}")


async def safe_close_page(page) -> None:
    try:
        if page and not page.is_closed():
            await page.close()
    except Exception:
        pass


async def new_proxy_info(proxy_configuration, session_id: str):
    if not proxy_configuration:
        return None
    return await proxy_configuration.new_proxy_info(session_id=sanitize_session_id(session_id))


async def navigate(page, url: str, *, fingerprint: dict, cf_wait_seconds: int, cf_refresh_attempts: int, allow_manual: bool) -> bool:
    await human_delay(0.4, 1.2)
    response = await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    Actor.log.info(f"HTTP {response.status if response else '?'} -> {url}")
    await human_settle(page, fingerprint)
    return await wait_for_cloudflare(
        page,
        timeout_s=cf_wait_seconds,
        refresh_attempts=cf_refresh_attempts,
        allow_manual=allow_manual,
    )


def decode_obfuscated_emails(text: str) -> str:
    text = unescape(text or "")
    replacements = [
        (r"\s*\[\s*at\s*\]\s*", "@"),
        (r"\s*\(\s*at\s*\)\s*", "@"),
        (r"\s+at\s+", "@"),
        (r"\s*\[\s*dot\s*\]\s*", "."),
        (r"\s*\(\s*dot\s*\)\s*", "."),
        (r"\s+dot\s+", "."),
    ]
    for pattern, repl in replacements:
        text = re.sub(pattern, repl, text, flags=re.I)
    return text


def valid_email(email: str) -> bool:
    lower = email.lower().strip(".,;:)")
    bad_ext = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".css", ".js")
    return "@" in lower and not lower.endswith(bad_ext) and ".." not in lower


def extract_emails(text: str, hrefs: list[str]) -> list[str]:
    values: list[str] = []
    for href in hrefs:
        if href.lower().startswith("mailto:"):
            values.append(href.split(":", 1)[1].split("?", 1)[0])
    values.extend(EMAIL_RE.findall(decode_obfuscated_emails(text)))
    return unique([email.strip(".,;:)").lower() for email in values if valid_email(email)], 50)


def normalize_phone(phone: str) -> str:
    phone = re.sub(r"\s+", " ", phone).strip(" .,-;:|")
    digits = re.sub(r"\D", "", phone)
    if len(digits) < 7 or len(digits) > 16:
        return ""
    if len(digits) >= 13 and not phone.strip().startswith(("+", "00")):
        return ""
    return phone


def extract_phones(text: str, hrefs: list[str]) -> list[str]:
    values: list[str] = []
    for href in hrefs:
        if href.lower().startswith("tel:"):
            values.append(href.split(":", 1)[1])
    for candidate in PHONE_RE.findall(text):
        if re.search(r"[\s().-]", candidate):
            values.append(candidate)
    return unique([phone for raw in values if (phone := normalize_phone(raw))], 30)


def social_type(url: str) -> str:
    host = urlparse(url).netloc.lower().removeprefix("www.")
    for domain, label in SOCIAL_DOMAINS.items():
        if host == domain or host.endswith("." + domain):
            return label
    return ""


def is_noise_social_url(url: str) -> bool:
    lowered = url.lower()
    return any(token in lowered for token in ("/share", "/intent/", "sharer.php", "login", "signup"))


def extract_social_links(hrefs: list[str]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for href in hrefs:
        kind = social_type(href)
        if not kind or is_noise_social_url(href):
            continue
        grouped.setdefault(kind, []).append(href.split("?", 1)[0].rstrip("/"))
    return {key: unique(values, 20) for key, values in grouped.items()}


def possible_address(line: str) -> bool:
    if len(line) < 12 or len(line) > 220:
        return False
    if any(token in line for token in ("{", "}", "[", "]", "\"", "=>")):
        return False
    has_number = bool(re.search(r"\b\d{1,6}\b", line))
    has_address_word = bool(
        re.search(
            r"\b(street|st\.|road|rd\.|avenue|ave\.|suite|ste\.|floor|fl\.|drive|dr\.|"
            r"lane|ln\.|blvd|boulevard|parkway|pkwy|highway|hwy|plaza|building|india|usa|uk)\b",
            line,
            re.I,
        )
    )
    return has_number and has_address_word


async def page_payload(page, base_url: str) -> dict:
    return await page.evaluate(
        """(baseUrl) => {
            const abs = (value) => {
                try { return new URL(value, baseUrl).href; } catch (e) { return ""; }
            };
            const text = document.body ? document.body.innerText : "";
            const html = document.documentElement ? document.documentElement.innerHTML : "";
            const links = [...document.querySelectorAll("a[href]")].map(a => ({
                href: abs(a.getAttribute("href")),
                rawHref: a.getAttribute("href") || "",
                text: (a.innerText || a.getAttribute("aria-label") || a.title || "").trim()
            }));
            const addresses = [...document.querySelectorAll("address, [itemprop='address'], [class*='address' i], [id*='address' i]")]
                .map(el => el.innerText.trim()).filter(Boolean);
            const jsonLd = [...document.querySelectorAll("script[type='application/ld+json']")]
                .map(el => el.textContent || "");
            return { url: location.href, title: document.title, text, html, links, addresses, jsonLd };
        }""",
        base_url,
    )


def parse_json_ld_addresses(raw_items: list[str]) -> list[str]:
    values: list[str] = []

    def walk(node):
        if isinstance(node, dict):
            address = node.get("address")
            if isinstance(address, str):
                values.append(address)
            elif isinstance(address, dict):
                parts = [
                    address.get("streetAddress"),
                    address.get("addressLocality"),
                    address.get("addressRegion"),
                    address.get("postalCode"),
                    address.get("addressCountry"),
                ]
                joined = ", ".join(str(part) for part in parts if part)
                if joined:
                    values.append(joined)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    for raw in raw_items:
        try:
            walk(json.loads(raw))
        except Exception:
            continue
    return values


def extract_addresses(payloads: list[dict]) -> list[str]:
    candidates: list[str] = []
    for payload in payloads:
        candidates.extend(payload.get("addresses", []))
        candidates.extend(parse_json_ld_addresses(payload.get("jsonLd", [])))
        for line in (payload.get("text") or "").splitlines():
            line = re.sub(r"\s+", " ", line).strip(" -|")
            if possible_address(line):
                candidates.append(line)
    return unique(candidates, 25)


def score_link(link: dict, base_url: str) -> int:
    href = link.get("href", "")
    if not href or not same_domain(href, base_url):
        return 0
    text = (link.get("text", "") or "").lower().strip()
    path = urlparse(href).path.lower().strip("/")
    path_parts = [part for part in re.split(r"[/_-]+", path) if part]
    score = 0
    for index, keyword in enumerate(CONTACT_KEYWORDS):
        key_parts = keyword.split("-")
        if path == keyword or path.endswith("/" + keyword):
            score += 400 - index
        elif all(part in path_parts for part in key_parts):
            score += 260 - index
        elif text in {keyword, keyword.replace("-", " ")}:
            score += 240 - index
        elif keyword.replace("-", " ") in text:
            score += 45 - index
    if len(path_parts) > 3:
        score -= 80
    if any(part in path_parts for part in ("blog", "store", "actors", "pricing", "api", "docs")):
        score -= 120
    if urlparse(href).fragment:
        score -= 5
    return score


def discover_contact_pages(payload: dict, base_url: str, max_pages: int) -> list[str]:
    scored: list[tuple[int, str]] = []
    for link in payload.get("links", []):
        href = link.get("href", "").split("#", 1)[0]
        if not href or not href.startswith(("http://", "https://")):
            continue
        if same_domain(href, base_url):
            score = score_link({**link, "href": href}, base_url)
            if score > 0:
                scored.append((score, href))

    fallback_paths = [
        "/contact",
        "/contact-us",
        "/about",
        "/about-us",
        "/team",
        "/support",
        "/locations",
    ]
    for path in fallback_paths:
        scored.append((60, urljoin(root_url(base_url), path)))

    ordered = [url for _, url in sorted(scored, key=lambda item: item[0], reverse=True)]
    return unique(ordered, max_pages)


def merge_payloads(start_url: str, payloads: list[dict]) -> dict:
    text = "\n".join(payload.get("text", "") for payload in payloads)
    hrefs = [
        link.get("href", "")
        for payload in payloads
        for link in payload.get("links", [])
        if link.get("href", "").startswith(("http://", "https://", "mailto:", "tel:"))
    ]
    all_links = unique([href for href in hrefs if href.startswith(("http://", "https://"))], 200)
    social_links = extract_social_links(all_links)
    return {
        "start_url": start_url,
        "final_url": payloads[0].get("url", start_url) if payloads else start_url,
        "title": payloads[0].get("title", "") if payloads else "",
        "status": "ok",
        "emails": extract_emails(text, hrefs),
        "phones": extract_phones(text, hrefs),
        "addresses": extract_addresses(payloads),
        "social_links": social_links,
        "all_links": all_links,
        "pages_scraped": unique([payload.get("url", "") for payload in payloads]),
    }


async def requeue_request(request_queue, request, retries: int, reason: str) -> None:
    await request_queue.add_request(
        Request.from_url(
            request.url,
            unique_key=f"{request.url}#retry-{retries + 1}-{random.random()}",
            user_data={**request.user_data, "retries": retries + 1, "last_retry_reason": reason},
        ),
        forefront=True,
    )


async def scrape_site(
    context,
    start_url: str,
    *,
    fingerprint: dict,
    max_pages_per_site: int,
    cf_wait_seconds: int,
    cf_refresh_attempts: int,
    allow_manual: bool,
) -> dict:
    payloads: list[dict] = []
    page = await context.new_page()
    try:
        passed = await navigate(
            page,
            start_url,
            fingerprint=fingerprint,
            cf_wait_seconds=cf_wait_seconds,
            cf_refresh_attempts=cf_refresh_attempts,
            allow_manual=allow_manual,
        )
        if not passed:
            return {"start_url": start_url, "status": "blocked_by_cloudflare", "pages_scraped": []}

        first_payload = await page_payload(page, start_url)
        payloads.append(first_payload)

        contact_pages = discover_contact_pages(first_payload, start_url, max_pages_per_site - 1)
        for contact_url in contact_pages:
            if len(payloads) >= max_pages_per_site:
                break
            if contact_url in {payload.get("url") for payload in payloads}:
                continue
            passed = await navigate(
                page,
                contact_url,
                fingerprint=fingerprint,
                cf_wait_seconds=cf_wait_seconds,
                cf_refresh_attempts=cf_refresh_attempts,
                allow_manual=allow_manual,
            )
            if not passed:
                Actor.log.warning(f"Skipping blocked contact page: {contact_url}")
                continue
            payloads.append(await page_payload(page, start_url))

        return merge_payloads(start_url, payloads)
    finally:
        await safe_close_page(page)


async def main() -> None:
    async with Actor:
        actor_input = await Actor.get_input() or {}
        start_urls = actor_input.get("start_urls") or actor_input.get("urls") or []
        urls = [clean_url(item.get("url") if isinstance(item, dict) else str(item)) for item in start_urls]
        urls = unique([url for url in urls if url])

        if not urls:
            Actor.log.info("No URLs specified in Actor input, exiting.")
            await Actor.exit()

        headless = parse_bool(actor_input.get("headless"), True)
        use_apify_proxy = parse_bool(actor_input.get("use_apify_proxy"), False)
        proxy_groups = actor_input.get("proxy_groups") or ["RESIDENTIAL"]
        proxy_country = (actor_input.get("proxy_country") or "US").upper()
        max_pages_per_site = max(1, min(int(actor_input.get("max_pages_per_site", 5)), 20))
        max_retries = max(0, min(int(actor_input.get("max_retries", 2)), 5))
        cf_wait_seconds = max(30, min(int(actor_input.get("cf_wait_seconds", 120)), 300))
        cf_refresh_attempts = max(0, min(int(actor_input.get("cf_refresh_attempts", 3)), 8))
        page_gap = actor_input.get("page_gap_seconds") or [2, 6]
        page_gap_min, page_gap_max = float(page_gap[0]), float(page_gap[1])
        session_id = actor_input.get("session_id") or "find_contacts_" + hashlib.sha1("|".join(urls).encode()).hexdigest()[:10]
        fingerprint = build_fingerprint(actor_input.get("fingerprint_seed") or session_id)
        storage_key = "BROWSER_STORAGE_STATE_" + hashlib.sha1(session_id.encode()).hexdigest()[:16]
        allow_manual = (not headless) and os.getenv("APIFY_IS_AT_HOME") != "1"

        Actor.log.info(f"Find Contacts: {len(urls)} URL(s), max_pages_per_site={max_pages_per_site}, headless={headless}")

        request_queue = await Actor.open_request_queue()
        run_token = hashlib.sha1(f"{session_id}-{random.random()}".encode()).hexdigest()[:8]
        for index, url in enumerate(urls):
            await request_queue.add_request(
                Request.from_url(url, unique_key=f"{url}#run-{run_token}-{index}", user_data={"retries": 0})
            )

        proxy_configuration = None
        if use_apify_proxy:
            try:
                proxy_configuration = await Actor.create_proxy_configuration(groups=proxy_groups, country_code=proxy_country)
            except Exception as exc:
                Actor.log.warning(f"Apify Proxy unavailable, continuing without it: {exc}")

        async with async_playwright() as playwright:
            proxy_info = await new_proxy_info(proxy_configuration, session_id)
            browser = await launch_browser(playwright, headless=headless, proxy_info=proxy_info)
            context = await make_context(
                browser,
                fingerprint=fingerprint,
                cookies=parse_cookies(actor_input.get("cloudflare_cookies")),
                storage_state=await load_storage_state(storage_key),
            )

            handled = 0
            try:
                while request := await request_queue.fetch_next_request():
                    retries = int(request.user_data.get("retries", 0))
                    if handled:
                        await human_delay(page_gap_min, page_gap_max)
                    Actor.log.info(f"Scraping contacts ({retries}/{max_retries}): {request.url}")

                    try:
                        result = await scrape_site(
                            context,
                            request.url,
                            fingerprint=fingerprint,
                            max_pages_per_site=max_pages_per_site,
                            cf_wait_seconds=cf_wait_seconds,
                            cf_refresh_attempts=cf_refresh_attempts,
                            allow_manual=allow_manual,
                        )
                        if result.get("status") == "blocked_by_cloudflare" and retries < max_retries:
                            await save_storage_state(context, storage_key)
                            await requeue_request(request_queue, request, retries, "cloudflare")
                        else:
                            await Actor.push_data(result)
                    except Exception as exc:
                        Actor.log.exception(f"Failed to scrape {request.url}: {exc}")
                        if retries < max_retries:
                            await requeue_request(request_queue, request, retries, str(exc)[:200])
                        else:
                            await Actor.push_data(
                                {
                                    "start_url": request.url,
                                    "status": "failed_after_retries",
                                    "error": str(exc),
                                    "pages_scraped": [],
                                }
                            )
                    finally:
                        await request_queue.mark_request_as_handled(request)
                        handled += 1
                        await save_storage_state(context, storage_key)
            finally:
                await context.close()
                await browser.close()
