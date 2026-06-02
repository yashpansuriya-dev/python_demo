## LinkedIn Decision Maker Intelligence Scraper

This Apify Python Playwright actor opens a LinkedIn company page, follows the people/employees page, signs in, and saves structured decision-maker intelligence.

The scraper runs in two phases:

1. Scrape employee listing pages and use visible headline text for a lightweight decision-maker prefilter.
2. Push likely decision-maker profile URLs to the Apify request queue, then visit them sequentially in the same browser tab and extract the current role from the profile experience section.

Output records include:

- `name`, `linkedin_url`, and `location`
- `company.name` and `company.linkedin_url`
- `current_role.title`, `normalized_title`, `department`, `seniority_level`, `decision_maker_type`, `priority_score`, `confidence_score`, and matched keyword debug data
- `experience.total_years` and `experience.current_company_years`
- listing metadata including page and position

Create a `.env` file in this project folder for local runs:

```bash
LINKEDIN_EMAIL=your-email@example.com
LINKEDIN_PASSWORD=your-password
```

Default company URL:

```text
https://in.linkedin.com/company/techforceglobal
```

The actor also tries common company slug variants if the default URL is unavailable.

Useful input options:

- `decision_makers_only`: save only classified decision makers.
- `max_profiles_to_enrich`: cap profile visits to reduce blocking risk.
- `profile_delay_min_seconds` / `profile_delay_max_seconds`: random delay window before opening candidate profiles.
- `headless`: set to `false` if LinkedIn asks for security verification.
- `manual_verification_timeout_seconds`: how long the actor waits while you complete a LinkedIn checkpoint in the open browser/live view.
- `session_id`: keep this stable after a successful login so the saved LinkedIn storage state can be reused.

### LinkedIn security verification on Apify

LinkedIn may challenge a login from Apify even when the same credentials work locally, because the cloud browser/IP looks like a new device. The actor cannot bypass that checkpoint. When it happens:

1. Run with `headless=false`.
2. Keep `manual_verification_timeout_seconds` high enough, for example `600`.
3. Open the Apify browser/live view and complete LinkedIn's security verification manually.
4. Rerun with the same `session_id`; the actor saves and reuses the authenticated browser storage.

<!-- This is an Apify template readme -->

## Included features

- **[Apify SDK](https://docs.apify.com/sdk/python/)** for Python - a toolkit for building Apify [Actors](https://apify.com/actors) and scrapers in Python
- **[Input schema](https://docs.apify.com/platform/actors/development/input-schema)** - define and easily validate a schema for your Actor's input
- **[Request queue](https://docs.apify.com/sdk/python/docs/concepts/storages#working-with-request-queues)** - queues into which you can put the URLs you want to scrape
- **[Dataset](https://docs.apify.com/sdk/python/docs/concepts/storages#working-with-datasets)** - store structured data where each object stored has the same attributes
- **[Playwright](https://pypi.org/project/playwright/)** - a browser automation library

## Resources

- [Playwright for web scraping in 2023](https://blog.apify.com/how-to-scrape-the-web-with-playwright-ece1ced75f73/)
- [Scraping single-page applications with Playwright](https://blog.apify.com/scraping-single-page-applications-with-playwright/)
- [How to scale Puppeteer and Playwright](https://blog.apify.com/how-to-scale-puppeteer-and-playwright/)
- [Integration with Zapier](https://apify.com/integrations), Make, GitHub, Google Drive and other apps
- [Video guide on getting data using Apify API](https://www.youtube.com/watch?v=ViYYDHSBAKM)
- A short guide on how to build web scrapers using code templates:

[web scraper template](https://www.youtube.com/watch?v=u-i-Korzf8w)


## Getting started

For complete information [see this article](https://docs.apify.com/platform/actors/development#build-actor-locally). To run the Actor use the following command:

```bash
apify run
```

## Deploy to Apify

### Connect Git repository to Apify

If you've created a Git repository for the project, you can easily connect to Apify:

1. Go to [Actor creation page](https://console.apify.com/actors/new)
2. Click on **Link Git Repository** button

### Push project on your local machine to Apify

You can also deploy the project on your local machine to Apify without the need for the Git repository.

1. Log in to Apify. You will need to provide your [Apify API Token](https://console.apify.com/account/integrations) to complete this action.

    ```bash
    apify login
    ```

2. Deploy your Actor. This command will deploy and build the Actor on the Apify Platform. You can find your newly created Actor under [Actors -> My Actors](https://console.apify.com/actors?tab=my).

    ```bash
    apify push
    ```

## Documentation reference

To learn more about Apify and Actors, take a look at the following resources:

- [Apify SDK for JavaScript documentation](https://docs.apify.com/sdk/js)
- [Apify SDK for Python documentation](https://docs.apify.com/sdk/python)
- [Apify Platform documentation](https://docs.apify.com/platform)
- [Join our developer community on Discord](https://discord.com/invite/jyEM2PRvMU)
