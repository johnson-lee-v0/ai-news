# Data and HTTP contract

Python 3.9+ standard-library runtime on macOS or Linux, SQLite persistence and loopback-only HTTP. Runtime evidence belongs in the ignored `data/` directory; synthetic fixtures belong in tests and temporary databases. The source of truth for accepted fields is the implementation in `pulse/`.

## Dashboard

`GET /api/dashboard` returns collected articles, grouped stories, source states, refresh history, a conditional brief, statistics, coverage, a watchlist, public account references, X access status, manual leads and curated research sections.

Article fields include `id`, `title`, `url`, `published_at` (nullable), `date_kind`, `date_precision`, `observed_at`, `first_seen_at`, `revised_at`, `source_id`, `source_name`, `source_role`, `kind`, `summary`, `entities`, `tags`, `content_hash`, `verification_status` and provenance. The legacy `published_at` key can hold a feed/index/filing date; interpret it with `date_kind`, not automatically as original publication.

Source roles are `primary`, `secondary` and `discovery`. Successful fetching or primary-source status does not independently verify a claim. Source states include attempt/success timestamps, errors, collected item counts, rejected counts and bounded-window metadata.

Analysis adds transparent score factors, relevance, topic/lenses, conditional implication, counterevidence, confirmation/refutation prompts and effective reading status. Story groups contain `article_ids` for currently grouped appearances and related links. Grouping does not prove independent corroboration. The brief limits repeated company coverage; the full reading queue retains other loaded articles.

The dashboard loads the latest 500 stored records and reports the total count separately. Refresh summaries distinguish new records, selected-record revisions, unchanged/alternate appearances, rejected records, failed sources and skipped sources. Source mappings and successful requests do not guarantee comprehensive coverage.

## Local actions

- `GET /api/health`: service/version information.
- `POST /api/refresh` with `{}`: refresh configured public endpoints and save a daily snapshot.
- `POST /api/leads` with `{url, note}`: save an individual HTTPS X/Twitter post URL as an unverified lead; no post fetch.
- `POST /api/review` with `{article_ids, status}`: atomically update 1–100 explicit stored article IDs. Status is `unreviewed`, `reviewed` or `dismissed`; `reviewed` means read, not verified. A single `article_id` is also accepted. Content revisions return that appearance to unread.

Writes require JSON and same-origin loopback requests. The service exposes only its explicit HTTP routes, not arbitrary project files or the database.

## Curated research import

`python3 -m pulse import-curation PATH` accepts a JSON object with only `notes`, `ledger` and/or `earnings` arrays. Identical records are not re-versioned. Revised records retain prior versions. IDs must be 1–100 letters, numbers, hyphens or underscores. Dates must be valid ISO dates and must not be in the future.

A note requires `id`, `title`, `observation`, `implication`, `as_of`, `uncertainty` and nonempty `sources`. Each source requires `url`, `title` and `date`. Optional fields can document fact/claim type, counterevidence, beneficiaries, risks, event/report dates and confirmation/refutation tests. Imported narrative remains the curator's assessment.

A financing record requires `id`, `as_of`, `source_url`, `source_date`, `from_entity`, `to_entity`, `instrument`, `status` and `note`. Supported instruments include equity, customer contracts, cloud credits, debt, guarantees, capacity and investment. Unknown amounts stay unknown; `overlap_group` tracks related commitments. The app does not add unlike or overlapping amounts into a grand total.

An earnings record requires `id`, `as_of`, `source_url`, `source_date`, `company`, `period`, `metric`, `unit` and at least one of `reported`, `guidance` or `consensus`. Guidance requires `guidance_period`; consensus additionally requires `consensus_source_url`, `consensus_as_of` and `consensus_period`. Compare consistent periods, currencies and metric definitions.

## Interpretation

Automatic implications are conditional reading questions, not independently verified research or market forecasts. A probability illustration uses `1 - exp(-spread_decimal * horizon / (1 - recovery))`; inputs are illustrative/user supplied, with explicit horizon and risk-neutral assumptions. It is not a live CDS quote or a calibrated physical default forecast.
