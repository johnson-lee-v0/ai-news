# Source strategy

The feed should answer **what changed, how it changes cash, orders or delivery, and what would prove that interpretation wrong**. A popular post is a useful question, not evidence that the answer is true. This document describes the curation standard; a source counts as connected only when the app records a successful fetch. The account catalog is a researched watchlist, not an automatic X feed.

## What deserves attention

| Topic | Material evidence | Mistake to avoid |
| --- | --- | --- |
| Financing and private valuations | Closed rounds, actual proceeds, debt terms, maturities, unrestricted cash, secondary sale prices, investor marks | Calling a secondary bid or fund mark a new company financing; comparing pre-money with post-money values |
| Demand and adoption | Paid usage, renewals, realized pricing, customer revenue, contract conversion and concentration | Treating downloads, demos, token counts or nonbinding commitments as profitable demand |
| Capacity delivery | Movement from proposed to permitted, energized, installed and utilized capacity | Equating nameplate power, contracted supply and delivered compute; assuming every cancellation means aggregate demand fell |
| Earnings | Reported figures, period and basis, management guidance, and dated consensus when a source supplies it | Comparing different periods, presenting guidance as results, or inventing consensus |
| Infrastructure bottlenecks | Memory, advanced packaging, networking, power, cooling, construction lead times and utilization | Extrapolating one supplier or one geography to the entire market |
| Models and products | Reproducible capability, latency, price, reliability or adoption changes with a path to economics | Ranking every launch highly because it mentions AI |
| Policy and legal changes | Enacted rules, export licenses, binding orders, contracts and dated proceedings | Reporting proposals or rumors as effective law |

OpenAI and Anthropic valuation claims belong in the financing lane. Record company, old and new values, currency, valuation basis, transaction or mark date, source date, and whether a price was asked, offered, marked or actually transacted. Then ask whether funding access or contractual spending changed. A lower paper valuation alone does not establish lower compute demand. Preserve that distinction even when the story is important.

## How to choose sources

1. Start with issuer investor relations, SEC filings, official lab announcements, regulators, utility filings and local permitting records. Company statements are primary evidence of what management said, not independent proof of future outcomes. SEC filing metadata is a discovery signal until the relevant disclosure is read.
2. Use original reporting from reputable publications to find developments and seek independent corroboration. Use only publicly permitted material; a headline or search excerpt does not substitute for an inaccessible article.
3. Use specialist analysis and reproducible technical work to form and test implications. Record the author's assumptions, original evidence and commercial context.
4. Use X to discover questions, public posts and links. Promote a lead only after tracing it to evidence. Reposts, syndication and two authors relying on one anonymous source do not create additional independent confirmations.

Official [OpenAI news](https://openai.com/news/) and [Anthropic news](https://www.anthropic.com/news) complement independent analysis. Company IR and SEC disclosures should anchor claims about listed suppliers and customers. Official announcements can establish announced intent or management claims; they do not settle commercial effectiveness.

## Curated X account catalog

Canonical URLs, identity evidence, review timestamps, topics and caveats live in [`config/accounts.json`](../config/accounts.json). This is deliberately a mix of perspectives, not a follower-count ranking. Identity review occurred on October 25, 2026 UTC. Current X access and post freshness remain unverified.

| Account | Useful lens | Verification and caution |
| --- | --- | --- |
| [Dylan Patel](https://x.com/dylan522p) | Chips, infrastructure and compute costs | [Own biography](https://semianalysis.com/dylan-patel/). Commercial research; investigate assumptions and public source material. |
| [Doug O'Laughlin / Fabricated Knowledge](https://x.com/fabknowledge) | Suppliers, earnings and allocation of capital | [Own publication](https://www.fabricatedknowledge.com/about), [SemiAnalysis biography](https://semianalysis.com/doug-olaughlin/). Same research organization as Patel; do not count them as independent corroboration. |
| [Patrick Moorhead](https://x.com/PatrickMoorhead) | Enterprise and cloud adoption, silicon, product roadmaps | [Own biography](https://moorinsightsstrategy.com/team/patrick-moorhead/). Advisory relationships and vendor access require context. |
| [Ming-Chi Kuo](https://x.com/mingchikuo) | Asian hardware and manufacturing supply chain | [Industry profile](https://www.macrumors.com/guide/ming-chi-kuo/). Channel checks are estimates; Apple-heavy coverage needs a material AI connection. |
| [Ed Zitron](https://x.com/edzitron) | Funding, unit economics and counterarguments | [Own biography](https://www.wheresyoured.at/about/). Skeptical editorial perspective; follow numbers to originals and test counterevidence. |
| [Nat Bullard](https://x.com/NatBullard) | Electricity, physical capacity and energy capital | [Own biography](https://www.nathanielbullard.com/about). Consults and builds energy businesses; corroborate site claims with utilities and permits. |
| [Eric Flaningam](https://x.com/EricFlaningam) | AI value chain and business economics | [Own biography with handle](https://www.generativevalue.com/about). Investor opinions and scenarios need disclosed assumptions. |
| [Simon Willison](https://x.com/simonw) | Hands-on capability, costs and reliability | [Own biography and disclosures](https://simonwillison.net/about/). Tests do not establish enterprise adoption; disclosed vendor preview access and sponsorship matter. |

No individual X post was added as a current example because its content and publication time were not fully verified in this review. For accessible longer-form writing, use the catalog's author-site links. Simon Willison also documents [public Atom feeds](https://simonwillison.net/about/#atom-feeds); an alternative publishing channel is not proof that X is connected.

## Refresh and editorial review

The refresh command gathers configured public sources, preserves source and retrieval dates, and records success or failure. The shortlist then needs editorial review: open the original, compare with the prior state, identify the economic mechanism, find counterevidence, and state the next observable test. Consult the app's actual source-status display for what ran; a catalog entry or this strategy document does not prove ingestion or scheduling.

A useful review order is:

1. Find changes since the last successful review; include late discoveries with their original publication dates.
2. Group the same underlying event and keep its earliest known source, later confirmations, corrections and conflicting evidence together.
3. Prioritize by materiality, evidence quality, newness and decision horizon. A financing covenant change can matter more than a highly shared model demo.
4. Write a short statement of the observation, a separately labeled inference, likely beneficiaries and exposed businesses, uncertainty, counterevidence and what would confirm or refute it.
5. Check gaps across model labs, hyperscalers, chips and memory, networking, power/cooling, neocloud finance and end-customer adoption. Say which sources failed or were not connected.

Minimum provenance is canonical source URL, publisher/author, publication date, event date or report period when known, retrieval time, content provenance hash, evidence type and verification status. Unknown dates stay unknown. A new retrieval is not a new event. Separate announced investment, equity funding, debt, guarantees, credits and customer contracts; do not add their face values into revenue or assume circular transactions are fabricated.

Credit-risk commentary must name the instrument, quote timestamp, time horizon and recovery/model assumptions. A market-implied risk-neutral default probability is not a literal physical forecast or a probability of default next year unless that horizon is actually supported.

## Honest coverage

The system cannot guarantee the most relevant news or comprehensive X trends. It can make the search and selection process inspectable: which sources were attempted, when they last worked, which items were filtered or grouped, which claims were corroborated, and why the brief selected them. A quiet brief can mean no material verified change; a failed source means incomplete coverage and must remain visible. There are no inferred engagement counts, no synthetic live articles and no silent substitution of demo content.
