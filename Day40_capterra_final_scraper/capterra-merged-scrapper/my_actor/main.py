from __future__ import annotations

import asyncio
import csv
import os
import random
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse

from apify import Actor, Request
from playwright.async_api import async_playwright

sys.stdout.reconfigure(encoding="utf-8")


CF_TITLES = {
    "just a moment",
    "attention required!",
    "please wait...",
    "checking your browser",
    "one more step",
    "security check",
    "access denied",
}

VIEWPORTS = [
    {"width": 1280, "height": 720},
    {"width": 1366, "height": 768},
    {"width": 1440, "height": 900},
    {"width": 1920, "height": 1080},
]

PRODUCT_CSV_FIELDS = [
    "product_index",
    "software_category",
    "product_id",
    "name",
    "url",
    "rating",
    "reviews_count",
    "description",
]

REVIEW_CSV_FIELDS = [
    "product_id",
    "review_title",
    "description",
    "author",
    "rating",
    "date",
    "pros",
    "cons",
    "author_profession",
    "author_industry",
    "author_duration",
]


async def human_delay(min_s=1.0, max_s=2.5):
    await asyncio.sleep(random.uniform(min_s, max_s))


async def human_mouse_wander(page):
    for _ in range(random.randint(3, 6)):
        await page.mouse.move(
            random.randint(80, 1200),
            random.randint(80, 700),
            steps=random.randint(10, 25),
        )
        await asyncio.sleep(random.uniform(0.08, 0.25))


async def random_scroll(page):
    for _ in range(random.randint(2, 4)):
        await page.evaluate(f"window.scrollBy(0, {random.randint(250, 650)})")
        await asyncio.sleep(random.uniform(0.35, 0.8))


async def wait_for_cloudflare(page, timeout_s=180, *, allow_manual=True) -> bool:
    deadline = asyncio.get_event_loop().time() + timeout_s
    manual_notice_shown = False

    while asyncio.get_event_loop().time() < deadline:
        try:
            title = (await page.title()).lower().strip()
        except Exception:
            title = ""

        Actor.log.info(f"[CF] title='{title}'")

        challenge_count = await page.locator(
            "iframe[src*='challenges.cloudflare.com'],"
            "iframe[src*='hcaptcha.com'],"
            "div#challenge-form,"
            "div#cf-challenge-running"
        ).count()

        if challenge_count:
            if not allow_manual:
                Actor.log.warning("[CF] Checkbox/challenge found. Run headed to verify manually.")
                return False
            if not manual_notice_shown:
                Actor.log.warning("[CF] Click the checkbox in the opened browser; the actor will continue.")
                manual_notice_shown = True
            await asyncio.sleep(2)
            continue

        if not any(keyword in title for keyword in CF_TITLES):
            Actor.log.info("[CF] Challenge cleared")
            return True

        await human_mouse_wander(page)
        await asyncio.sleep(2)

    Actor.log.warning("[CF] Timed out waiting for challenge to clear.")
    return False


async def launch_browser(playwright, *, headless: bool):
    args = [
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
        "--disable-blink-features=AutomationControlled",
        "--window-size=1366,768",
    ]

    if os.name == "nt":
        try:
            Actor.log.info(f"Launching installed Google Chrome headless={headless}")
            return await playwright.chromium.launch(channel="chrome", headless=headless, args=args)
        except Exception as e:
            Actor.log.warning(f"Chrome channel failed, using bundled Chromium: {e}")

    Actor.log.info(f"Launching bundled Chromium headless={headless}")
    return await playwright.chromium.launch(headless=headless, args=args)


async def make_context(browser):
    viewport = random.choice(VIEWPORTS)
    return await browser.new_context(
        viewport=viewport,
        screen=viewport,
        locale="en-US",
        timezone_id="America/New_York",
        color_scheme="light",
        java_script_enabled=True,
        accept_downloads=False,
    )


async def goto_verified(page, url: str, *, headless: bool) -> bool:
    response = await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    Actor.log.info(f"HTTP {response.status if response else '?'} {url}")
    return await wait_for_cloudflare(
        page,
        timeout_s=45 if headless else 180,
        allow_manual=not headless,
    )


async def optional_inner_text(locator, default="") -> str:
    try:
        if await locator.count() == 0:
            return default
        return " ".join((await locator.first.inner_text()).split())
    except Exception:
        return default


async def optional_raw_inner_text(locator, default="") -> str:
    try:
        if await locator.count() == 0:
            return default
        return (await locator.first.inner_text()).strip()
    except Exception:
        return default


async def scrape_product_card(card, start_url: str) -> dict | None:
    try:
        product_name = await optional_inner_text(card.locator("h2"))
        partial_url = await card.locator('a[href*="/p/"]').first.get_attribute("href")
        product_url = urljoin(start_url, partial_url).rstrip("/") if partial_url else ""

        rating_text = await optional_inner_text(card.locator("span.sr2r3oj").first)
        rating = rating_text.split("(")[0].strip() if rating_text else ""
        no_of_reviews = ""
        if "(" in rating_text and ")" in rating_text:
            no_of_reviews = rating_text.split("(", 1)[1].split(")", 1)[0].strip()

        description = await optional_inner_text(card.locator("p.text-neutral-99").first)

        # included_features = []
        # not_included_features = []
        # feature_items = card.locator(
        #     '[data-testid="product-card-category-features"] div.flex.items-center,'
        #     '[data-test-id="product-card-category-features"] div.flex.items-center'
        # )
        # for i in range(await feature_items.count()):
        #     feature = feature_items.nth(i)
        #     text = await optional_inner_text(feature)
        #     icon_class = await feature.locator("i").first.get_attribute("class") or ""
        #     if "icon-check" in icon_class:
        #         included_features.append(text)
        #     elif "icon-x" in icon_class:
        #         not_included_features.append(text)

        if not product_url:
            return None

        return {
            "name": product_name,
            "url": product_url,
            "rating": rating,
            "reviews_count": no_of_reviews,
            "description": description,
        }
    except Exception as e:
        Actor.log.warning(f"Product card parse error: {e}")
        return None


async def scrape_review_page(page) -> tuple[list[dict], bool]:
    await random_scroll(page)
    await human_delay(1.0, 2.0)

    container = page.locator('div[data-test-id="review-cards-container"]')
    review_cards = container.locator("div.e1xzmg0z.c1ofrhif.typo-10")
    reviews_count = await review_cards.count()
    Actor.log.info(f"  Reviews on this page: {reviews_count}")

    if reviews_count == 0:
        return [], False

    reviews = []
    for i in range(reviews_count):
        review = review_cards.nth(i)
        try:
            author_text = await optional_raw_inner_text(review.locator("div.typo-10.text-neutral-90"))
            lines = [line.strip() for line in author_text.split("\n") if line.strip()]

            pros_locator = review.locator("span:has-text('Pros') >> xpath=../following-sibling::p")
            cons_locator = review.locator("span:has-text('Cons') >> xpath=../following-sibling::p")

            reviews.append({
                "review_title": (await optional_inner_text(review.locator("h3"))).replace('"', ""),
                "author_name": lines[0] if len(lines) > 0 else "",
                "author_profession": lines[1] if len(lines) > 1 else "",
                "author_industry": lines[2] if len(lines) > 2 else "",
                "author_duration": lines[3] if len(lines) > 3 else "",
                "review_stars": await optional_inner_text(review.locator("span.sr2r3oj").nth(0)),
                "review_date": await optional_inner_text(review.locator("div.typo-0")),
                "review_description": await optional_inner_text(review.locator("div.space-y-6 > p")),
                "review_pros": await optional_inner_text(pros_locator),
                "review_cons": await optional_inner_text(cons_locator),
            })
        except Exception as e:
            Actor.log.warning(f"Review {i} parse error: {e}")

    return reviews, True


async def get_category_cards(page, category_page: int):
    card_selector = 'div[id^="product-card-container-"]'
    try:
        await page.wait_for_selector(card_selector, timeout=5_000)
    except Exception:
        title = (await page.title()).lower()
        body_text = (await optional_inner_text(page.locator("body"))).lower()
        if "not found" in title or "not found" in body_text or "404" in title:
            Actor.log.warning(f"Category page {category_page} not found; stopping category pagination.")
        else:
            Actor.log.warning(f"No product cards found on category page {category_page}; stopping category pagination.")
        return page.locator(card_selector), 0

    cards = page.locator(card_selector)
    return cards, await cards.count()


def slugify(value: str, *, fallback: str = "item") -> str:
    safe_name = "".join(
        char.lower() if char.isalnum() else "_" for char in value.strip()
    ).strip("_")
    return "_".join(part for part in safe_name.split("_") if part) or fallback


def unique_product_id(product: dict, used_ids: set[str]) -> str:
    product_id = slugify(product.get("name", ""), fallback="product")
    unique_id = product_id
    suffix = 2
    while unique_id in used_ids:
        unique_id = f"{product_id}_{suffix}"
        suffix += 1
    used_ids.add(unique_id)
    return unique_id


def category_page_url(start_url: str, page_number: int) -> str:
    clean_url = urlunparse(urlparse(start_url)._replace(query=""))
    if page_number <= 1:
        return clean_url
    return f"{clean_url}?page={page_number}"


def read_existing_product_rows(products_csv_path: Path) -> list[dict]:
    if not products_csv_path.exists():
        return []

    with products_csv_path.open(newline="", encoding="utf-8-sig") as csv_file:
        rows = list(csv.DictReader(csv_file))

    for index, row in enumerate(rows, start=1):
        row["product_index"] = row.get("product_index") or str(index)
    return rows


def write_csv_outputs(
    category_name: str,
    products: list[dict],
    *,
    base_dir: Path | str = "csv_outputs",
    batch_label: str = "",
) -> Path:
    output_dir = Path(base_dir) / slugify(category_name, fallback="software")
    output_dir.mkdir(parents=True, exist_ok=True)
    category_slug = slugify(category_name, fallback="software")
    products_csv_path = output_dir / "products.csv"
    named_products_csv_path = output_dir / f"00_{category_slug}_products.csv"
    batch_products_csv_path = (
        output_dir / f"00_{category_slug}_products_{slugify(batch_label, fallback='batch')}.csv"
        if batch_label
        else None
    )

    product_rows = read_existing_product_rows(products_csv_path)
    used_ids = {row.get("product_id", "") for row in product_rows if row.get("product_id")}
    existing_urls = {row.get("url", "") for row in product_rows if row.get("url")}
    review_files = []
    batch_product_rows = []

    for product in products:
        if product.get("url", "") in existing_urls:
            continue

        product_id = unique_product_id(product, used_ids)
        product_row = {
            "product_index": str(len(product_rows) + 1),
            "software_category": category_name,
            "product_id": product_id,
            "name": product.get("name", ""),
            "url": product.get("url", ""),
            "rating": product.get("rating", ""),
            "reviews_count": product.get("reviews_count", ""),
            "description": product.get("description", ""),
        }
        product_rows.append(product_row)
        batch_product_rows.append(product_row)
        existing_urls.add(product.get("url", ""))

        review_path = output_dir / f"{product_id}_reviews.csv"
        review_files.append((review_path, product_id, product.get("reviews", [])))

    for product_csv_path in (products_csv_path, named_products_csv_path):
        with product_csv_path.open("w", newline="", encoding="utf-8-sig") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=PRODUCT_CSV_FIELDS)
            writer.writeheader()
            writer.writerows(product_rows)

    if batch_products_csv_path:
        with batch_products_csv_path.open("w", newline="", encoding="utf-8-sig") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=PRODUCT_CSV_FIELDS)
            writer.writeheader()
            writer.writerows(batch_product_rows)

    for review_path, product_id, reviews in review_files:
        with review_path.open("w", newline="", encoding="utf-8-sig") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=REVIEW_CSV_FIELDS)
            writer.writeheader()
            for review in reviews:
                writer.writerow({
                    "product_id": product_id,
                    "review_title": review.get("review_title", ""),
                    "description": review.get("review_description", ""),
                    "author": review.get("author_name", ""),
                    "rating": review.get("review_stars", ""),
                    "date": review.get("review_date", ""),
                    "pros": review.get("review_pros", ""),
                    "cons": review.get("review_cons", ""),
                    "author_profession": review.get("author_profession", ""),
                    "author_industry": review.get("author_industry", ""),
                    "author_duration": review.get("author_duration", ""),
                })

    return output_dir


async def main() -> None:
    async with Actor:
        actor_input = await Actor.get_input() or {}
        category_name = actor_input.get("software_category", "Application Development")
        total_products = int(actor_input.get("total_products_to_scrape", 10))
        start_category_page = max(1, int(actor_input.get("start_category_page", 1)))
        max_review_pages = max(1, min(100, int(actor_input.get("review_pages_per_product", 2))))
        max_cf_retries = int(actor_input.get("max_cf_retries", 2))
        headless = bool(actor_input.get("headless", False))

        category_query = category_name.lower().replace(" ", "-")
        start_url = f"https://www.capterra.com/{category_query}-software/"
        # first_category_url  = "https://www.yellowpages.com/search?search_terms=restaurants&geo_location_terms=Los+angeles"
        first_category_url = category_page_url(start_url, start_category_page)

        request_queue = await Actor.open_request_queue(name=None)
        await request_queue.add_request(
            Request.from_url(
                first_category_url,
                user_data={"depth": 0, "retries": 0, "category_page": start_category_page},
            )
        )

        products_done = 0
        products_queued = 0
        queued_product_urls = set()
        scraped_products = []

        async with async_playwright() as playwright:
            browser = await launch_browser(playwright, headless=headless)
            context = await make_context(browser)
                     
            while products_done < total_products and (request := await request_queue.fetch_next_request()):
                page = await context.new_page()
                url = request.url
                depth = int(request.user_data.get("depth", 0))
                retries = int(request.user_data.get("retries", 0))
                Actor.log.info(f"→ {url} depth={depth} retry={retries}/{max_cf_retries}")

                try:
                    if not await goto_verified(page, url, headless=headless):
                        if retries < max_cf_retries:
                            await request_queue.add_request(
                                Request.from_url(
                                    url,
                                    unique_key=f"{url}#retry-{retries + 1}-{random.random()}",
                                    user_data={**request.user_data, "retries": retries + 1},
                                ),
                                forefront=True,
                            )
                        continue

                    await human_delay(1.5, 3.0)
                    await human_mouse_wander(page)

                    if depth == 0:
                        category_page = int(request.user_data.get("category_page", 1))
                        cards, count_cards = await get_category_cards(page, category_page)
                        Actor.log.info(f"Cards on category page {category_page}: {count_cards}")

                        if count_cards == 0:
                            continue

                        for i in range(count_cards):
                            if products_queued >= total_products:
                                break
                            product = await scrape_product_card(cards.nth(i), start_url)
                            if not product:
                                continue
                            if product["url"] in queued_product_urls:
                                continue

                            review_url = f"{product['url']}/reviews/?page=1"
                            await request_queue.add_request(
                                Request.from_url(
                                    review_url,
                                    user_data={
                                        "depth": 1,
                                        "retries": 0,
                                        "current_page": 1,
                                        "product": product,
                                        "all_reviews": [],
                                    },
                                )
                            )
                            queued_product_urls.add(product["url"])
                            products_queued += 1
                            Actor.log.info(f"Queued reviews: {review_url}")

                        if products_queued < total_products and count_cards > 0:
                            next_category_page = category_page + 1
                            next_category_url = category_page_url(start_url, next_category_page)
                            await request_queue.add_request(
                                Request.from_url(
                                    next_category_url,
                                    user_data={
                                        "depth": 0,
                                        "retries": 0,
                                        "category_page": next_category_page,
                                    },
                                ),
                                forefront=True,
                            )
                            Actor.log.info(
                                f"Queued category page {next_category_page}: {next_category_url}"
                            )

                    elif depth == 1:
                        current_page = int(request.user_data.get("current_page", 1))
                        product = request.user_data.get("product", {})
                        all_reviews = request.user_data.get("all_reviews", [])

                        if current_page == 1:
                            page_title = await optional_inner_text(page.locator("h1"))
                            overview = await optional_inner_text(page.locator("section#key-takeaways div.lg\\:w-7\\/12"))
                            product["review_page_title"] = page_title
                  

                        page_reviews, has_more = await scrape_review_page(page)
                        all_reviews.extend(page_reviews)

                        next_page = current_page + 1
                        if has_more and page_reviews and next_page <= max_review_pages:
                            base_url = product["url"]
                            await request_queue.add_request(
                                Request.from_url(
                                    f"{base_url}/reviews/?page={next_page}",
                                    user_data={
                                        "depth": 1,
                                        "retries": 0,
                                        "current_page": next_page,
                                        "product": product,
                                        "all_reviews": all_reviews,
                                    },
                                ),
                                forefront=True,
                            )
                        else:
                            product_data = {
                                **product,
                                "software_category": category_name,
                                "total_reviews_scraped": len(all_reviews),
                                "reviews": all_reviews,
                            }
                            await Actor.push_data(product_data)
                            scraped_products.append(product_data)
                            products_done += 1
                            Actor.log.info(f"Done {products_done}/{total_products}: {product.get('name')}")

                except Exception as e:
                    Actor.log.exception(f"Error on {url}: {e}")

                finally:
                    await page.close()
                    await request_queue.mark_request_as_handled(request)

            await context.close()
            await browser.close()

        if scraped_products:
            batch_label = f"from_page_{start_category_page}_limit_{total_products}"
            csv_path = write_csv_outputs(category_name, scraped_products, batch_label=batch_label)
            Actor.log.info(f"Saved CSV files in: {csv_path}")
