# AI Stock Pulse

A local research inbox for AI economics: what changed in funding, paid demand, capacity delivery, earnings, models and policy; why it could matter; and what evidence would confirm or refute the implication.

The app combines selected public feeds, SEC filing metadata and news discovery searches. It runs on macOS or Linux with Python 3.9+, using only the standard library, SQLite and a small HTML/CSS/JavaScript interface. No API keys, paid services or sign-ins are required for its public-source workflow.

## Public GitHub Pages dashboard

The public site is served at **https://johnson-lee-v0.github.io/ai-news/**. It is a read-only, manually reviewed snapshot with source dates and a separate review timestamp. It is not the live Python application: refresh, saved leads and server reading-state controls are unavailable. Tabs, filtering, source links, expandable implications and the illustrative calculator work in the browser.

Only `public/brief.json`, the public account catalog and selected static assets enter the site build. Local databases, fetched article bodies and private research are never exported. Publication review timestamps are not replaced with build timestamps; historical reports remain historical.

Build the exact static artifact locally:

```sh
python3 scripts/build_site.py
```

The seven-file artifact is written to ignored `_site/`. Use `node tests/pages_smoke.cjs` with an existing Playwright installation to test it under the `/ai-news/` repository prefix. The GitHub Pages workflow is **manual only**, with no cron or automatic data publication. After reviewing and auditing a new public snapshot, push it and explicitly run that workflow. See [Pages deployment](docs/PAGES.md).

## Run locally

```sh
python3 -m pulse serve
```

Open the URL printed in the terminal (normally `http://127.0.0.1:8765`). The server binds only to loopback and chooses another port if that port is occupied. Keep the terminal running; Control-C stops the app. On macOS, `./start.command` is an equivalent launcher.

A fresh checkout starts empty. Use **Refresh sources** in the dashboard or run:

```sh
python3 -m pulse refresh
```

The project-local `data/` directory is created at runtime. It is ignored by Git and contains the database, bounded raw-response archives and daily snapshots. It is not included in this repository. A separate data directory is supported:

```sh
python3 -m pulse --data-dir /tmp/pulse-scratch serve
```

## What it provides

- A short, diverse reading queue with source dates, source-quality labels, relevance filters and local read/dismiss controls.
- A distinction between demand, physical capacity and funding. Commitments are not automatically treated as revenue; a circular financing relationship is not automatically treated as fraudulent.
- Conditional implications, counterevidence and confirmation/refutation prompts. Automatic cards use source metadata and transparent rules, not verified full-document analysis.
- Curated research notes, a financing relationship ledger and an earnings table separating reported results, management guidance and separately sourced consensus.
- Source health, last attempt/success dates and explicit coverage gaps.
- A researched X account reading list and manual post-link capture. Automatic X timelines, trends and engagement collection are not connected.

## How refresh chooses news

Think of it as checking selected mailboxes and sorting the mail. The current catalog has 16 endpoints: issuer announcements, selected SEC submission records, reporting feeds and three Google News RSS searches covering lab financing, capacity and earnings. See `pulse/catalog.py` for the exact URLs and bounded windows.

Ranking favors recent source dates, financially material terms, relevant AI companies and stronger source types. Promotions and unrelated consumer stories are reduced. The brief limits repeated company coverage, while the evidence queue retains the other items. Exact URLs/content are deduplicated; matching headlines and dates are grouped. Repeated reporting is not independent corroboration.

Search hits remain leads. Their feed dates may be later than original publication. SEC ingestion detects filing metadata; it does not extract complete financial statements or contracts. The dashboard loads the latest 500 stored records for ranking and displays the full stored count separately. Successful fetching does not guarantee complete or important-news coverage.

For research standards and source caveats, read [methodology](docs/METHODOLOGY.md), [source strategy](docs/SOURCE_STRATEGY.md) and [X access](docs/X_ACCESS.md).

## Curated research

Import your own source-checked JSON packet:

```sh
python3 -m pulse import-curation path/to/research.json
```

The packet may contain `notes`, `ledger` and/or `earnings` arrays. Notes require an ID, title, observation, implication, as-of date, uncertainty and dated source links. Financing records distinguish instrument and status. Consensus values require a separate source and date. See [the data contract](CONTRACT.md) and `pulse/research.py` for the complete validation rules. Identical reimports do not create duplicate versions.

Research notes, manual leads and fetched article contents from any local installation are intentionally excluded. Tests use synthetic data in temporary databases; nothing seeds fictional evidence into the real feed.

## Validation

```sh
python3 -m unittest discover -s tests -v
```

There is no frontend build step. Optional browser checks use an independently installed Playwright/Chromium runtime:

```sh
node tests/ui_smoke.cjs
```

Set `PLAYWRIGHT_MODULE` to an existing module path if needed and `PYTHON` to a Python 3 executable. Browser checks use isolated synthetic data and do not require a live database or user browser profile.

## Daily operation

`python3 -m pulse refresh` can be run manually or by a separately configured scheduler while the machine is awake and online. This repository installs no background service and configures no recurring schedule. Each completed refresh persists a dated snapshot. Failed sources retain previous evidence and remain visibly failed; stale data is not treated as a successful current update.

## Publication boundaries

Source, safe documentation, public account references, tests and an explicitly reviewed public snapshot are published. Local data, article archives, research packets, credentials, environment files, screenshots, logs and caches are excluded. [Publication notes](docs/PUBLICATION.md) describe the audit and its limits.
