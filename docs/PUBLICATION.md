# Public source publication

This repository is a clean initial source publication of AI Stock Pulse. It does not include the working data store or development history of a local installation.

## Included

Application source, static interface assets, public source/account configuration, independently written source-linked public summaries, documentation, a local launcher, unit tests and explicitly synthetic browser-test fixtures. The local app starts empty until the user refreshes public sources or imports their own research. The separate GitHub Pages build includes only the reviewed public snapshot in `public/brief.json`; it never reads a local database.

## Excluded

- SQLite databases, raw feed/article responses and daily dashboard snapshots.
- Local research notes, manual X leads and archived third-party article bodies.
- Browser profiles, credentials, tokens, environment files, keys and certificates.
- Runtime/source-fetch logs, caches, screenshots and validation receipts containing local machine details.
- Temporary publication tools, scanner reports and backups.

These exclusions are enforced by an explicit initial file selection and a defensive `.gitignore`. An ignore file does not sanitize files already committed; inspect the actual staged inventory before future pushes.

## Validation and audit

The publication candidate passed 60 standard-library tests, including static-publication boundaries. The optional browser test uses only temporary synthetic data, an ephemeral loopback server and stubbed refreshes. It does not use an existing database, signed-in browser profile or remote news requests.

Before the first push, the complete candidate directory and clean Git history are checked with Gitleaks using its default rules and redacted reporting. A separate manual review checks local paths, private data, fetched content, credential-like filenames, links and the exact file inventory. The audit results are reported with the publication outcome; scanner reports stay outside the repository.

These checks reduce risk but cannot guarantee the absence of every secret or sensitive detail. Future changes and source imports require their own review. Do not commit runtime data or copy credentials into configuration or test fixtures.

## CI

The workflow runs unit tests on Linux with read-only repository permissions. Third-party actions are pinned to reviewed commit IDs. Browser tests remain optional and require a separately installed Playwright/Chromium runtime. A separate manual GitHub Pages workflow deploys the allowlisted static artifact using only repository-scoped Pages permissions. No scheduled publishing, paid service or private account data integration is configured.
