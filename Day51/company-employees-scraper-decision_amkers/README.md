## What does Google LinkedIn Decision Maker Scraper do?

Google LinkedIn Decision Maker Scraper finds **public LinkedIn profile URLs** for a target company by searching [Google](https://www.google.com/) with queries such as `site:linkedin.com/in/ "Techforce Global" "CEO"`, then extracts structured decision-maker intelligence from Google result titles and snippets. Optional LinkedIn profile visits can be enabled for extra enrichment, but the default mode does not require LinkedIn cookies, sessions, or login.

On Apify, you can run it on demand, schedule recurring runs, access results by API, monitor failures, export datasets, and connect the output to tools such as Google Sheets, Make, Zapier, or your CRM.

## Why use Google LinkedIn Decision Maker Scraper?

Use this Actor when you need a practical list of likely founders, executives, directors, managers, HR contacts, and other people connected with a company. Google search can surface public LinkedIn profiles that are difficult to collect from LinkedIn company employee pages without logging in. The Actor also lets you add custom title keywords, so you can search only for the roles that matter to your campaign.

Common use cases include B2B prospecting, recruitment sourcing, account research, competitor organization mapping, and finding local decision makers in a specific city such as Surat, Ahmedabad, or London.

## How to use Google LinkedIn Decision Maker Scraper

1. Open the Actor input tab.
2. Enter the company name, for example `Techforce Global`.
3. Review the default role keywords such as Founder, CEO, CTO, Director, HR, Head, VP, Manager, and Talent Acquisition.
4. Add optional location filters such as `Surat`.
5. Choose the maximum number of profiles to collect.
6. Run the Actor and open the Dataset tab when it finishes.
7. Download the dataset or consume it through the Apify API.

## Input

The main input fields are:

```json
{
  "company_name": "Techforce Global",
  "decision_makers_only": true,
  "role_keywords": ["Founder", "CEO", "CTO", "Director", "HR"],
  "locations": ["Surat"],
  "max_google_results": 100,
  "visit_linkedin_profiles": false
}
```

`role_keywords` controls both Google query generation and the decision-maker classifier. `locations` adds city or region words to the query. `decision_makers_only` saves only matching profiles when enabled. `visit_linkedin_profiles` can be enabled when you want public LinkedIn page enrichment after Google discovery.

## Output

Each saved dataset item contains profile, role, company, experience, and scraping metadata. You can download the dataset in various formats such as JSON, HTML, CSV, or Excel.

```json
{
  "name": "Example Person",
  "linkedin_url": "https://www.linkedin.com/in/example-person",
  "location": "Surat, Gujarat, India",
  "company": {
    "name": "Techforce Global",
    "linkedin_url": "https://www.linkedin.com/search/results/companies/?keywords=Techforce+Global"
  },
  "current_role": {
    "title": "Founder and CEO at Techforce Global",
    "normalized_title": "CEO",
    "department": "Business",
    "seniority_level": "Founder",
    "is_decision_maker": true,
    "decision_maker_type": "Business",
    "priority_score": 98,
    "matched_keywords": ["Founder", "CEO"],
    "confidence_score": 85
  }
}
```

## Data table

| Field | Description |
| --- | --- |
| `name` | Person name from the public profile or Google result |
| `linkedin_url` | Canonical `https://www.linkedin.com/in/...` profile URL |
| `location` | Public profile location when visible |
| `company` | Target company name and company search URL |
| `current_role` | Classified title, department, seniority, priority, and matched keywords |
| `experience` | Total and current-company years when visible |
| `scraping_metadata` | Google query, snippet, scrape time, and enrichment status |

## Pricing / Cost estimation

How much does it cost to scrape LinkedIn decision makers from Google? Cost depends mainly on the number of Google result pages and LinkedIn profiles visited. Start with a small test, for example 20 to 50 profiles, then increase `max_google_results` once the output quality looks right. Apify free tier limits may cover small tests, while larger recurring runs consume compute units according to browser runtime.

## Tips or Advanced options

Use narrow role keywords for cleaner lead lists, for example `Founder`, `CEO`, `CTO`, and `Director`. Add city filters when you need local contacts. For Google at scale, enable Apify Proxy only when your plan and compliance requirements allow it, and use the `GOOGLE_SERP` proxy group. The Actor always includes a general company query (no input toggle). Keep `visit_linkedin_profiles` disabled for the lowest-friction run mode; enable it only when Google snippets are not enough.

## FAQ, disclaimers, and support

This Actor only targets publicly available pages surfaced by Google and public LinkedIn profile pages. You are responsible for ensuring that your use complies with applicable laws, LinkedIn terms, Google terms, privacy requirements, and your internal data handling policies. Some profiles may show limited public data or a login prompt; in those cases the Actor falls back to Google title and snippet data where possible.

For bugs, feature requests, or custom scraping needs, use the Actor Issues tab in Apify Console.
