# GitHub Pages deployment

The public dashboard is a static, read-only snapshot at `https://johnson-lee-v0.github.io/ai-news/`. GitHub Pages cannot execute the local Python backend. The original local app and its data remain separate.

## Included behavior

The published interface supports section navigation, company/topic/source filters, sorting, expandable implications and provenance, external source links, the public X account reading list and the clearly illustrative probability calculator. It fetches one same-origin JSON snapshot under the repository path. It makes no requests to `/api/` and sends no writes.

Live refresh, server reading-queue actions and manual lead capture are local-app features. They are hidden and disabled in public mode. Source cards describe reviewed references rather than fabricated endpoint-health checks. The snapshot has a reviewed-at timestamp; original publication, event/report and historical quote dates remain separate. Old review dates trigger a stale warning. No X timeline, real-time CDS or analyst-consensus feed is connected.

## Content boundary

`public/brief.json` contains independently written concise public summaries and conditional analysis with cited sources. `public/SOURCES.md` records source dates and access limitations. Neither file is a raw runtime export. Subscriber-only article remainders, fetched bodies, local research packets, databases, private notes, logs, credentials and personal filesystem details are excluded.

The build script reads only the reviewed public brief, public account catalog and six static interface assets. Its exact ten-file output includes HTML, JavaScript, CSS, an original SVG icon, the JSON snapshot, a commit/hash manifest and `.nojekyll`. Unexpected files in the output directory are rejected rather than silently uploaded. The source schema rejects unknown export fields and obvious private paths; this is an additional guard, not a substitute for secret scanning and review.

## Deliberate publication workflow

1. Recheck the original public sources. Edit the public brief with source dates, access limits, counterevidence and the actual review time. Do not copy the local database or article bodies.
2. Run unit and browser checks. Build `_site/`, inspect the desktop/mobile result, and scan the exact source, Git history and artifact for secrets/private details.
3. Commit and push the reviewed changes. Run the **GitHub Pages** workflow manually on the intended `main` commit.
4. Verify that the Pages deployment succeeded for that commit, then check the live `/ai-news/` assets, populated snapshot, manifest and interactive behavior.

There is no scheduled workflow and no automatic public news refresh. A rebuild does not change the review timestamp or make historical evidence current. GitHub Actions uses pinned official actions, read-only build permissions and the Pages/OIDC permissions needed for the deployment job. No persistent credential is added to the repository.

Visit comparison uses one path-scoped localStorage key containing stable IDs, fingerprints and a visit timestamp. It sends nothing to an application server; no source text, URLs, personal notes or user-account data are stored there. Storage failures degrade to an explicit unavailable state. A new browser or cleared storage establishes a baseline without marking existing content new.
