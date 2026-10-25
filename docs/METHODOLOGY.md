# Evidence and interpretation

AI Stock Pulse is a local research inbox. Its automated output organizes public evidence and proposes conditional questions. It does not independently verify every issuer claim, produce a calibrated investment probability, or recommend a trade.

## Read the source before the implication

The default collector reads selected company feeds, reporting feeds, public search RSS and SEC filing metadata. A feed title or description is evidence of what that publisher announced. It may omit terms, caveats, reporting scope, or later corrections. A new filing record establishes that a filing exists; it does not establish that the filing supports an earnings or solvency claim. Open the dated source to investigate the full document.

Each item retains its source identity, canonical link, source publication date when available, first-seen and observed times, and a content hash. An unknown publication date remains unknown. Discovery time does not become publication time. RSS dates are labeled feed dates, SEC dates are filing dates, and search dates are search-feed dates. A publisher or search index may update an item; the original publication date needs separate verification. Date-only sources should not be interpreted as precise intraday timestamps. Missing or failed sources remain visible; they are not evidence that nothing happened.

The dashboard's observation summarizes the retrieved headline or description. Its implication is a rule-based, conditional research lens. Beneficiaries, risks, counterevidence, confirmation and refutation prompts describe what to investigate; they do not establish company-specific outcomes. A supplied source link is provenance, not an automatic fact check of an imported analyst note.

Ranking is an attention order based on available metadata and topic relevance. It is not a return forecast, popularity measurement, recommendation, or confidence percentage. A higher position cannot compensate for an unavailable source. The daily brief describes the collected set and its gaps, not the entire AI market.

## Transparent relevance and reading state

The ranking uses source recency, financial terms, economic topic, watchlist entities and source role, with penalties for promotional or unrelated consumer items. Each card exposes its score explanation. The score is a heuristic; false positives and missed stories remain possible. The brief limits repeated company coverage, but this can also omit a second material event from the same company; inspect the complete evidence queue.

Exact canonical URLs identify stored articles. Exact normalized headline and date matches form reading groups; different figures remain separate. Grouping is conservative and does not reliably merge every retelling or prove independent corroboration. Reading actions apply to the currently displayed group. A materially revised content hash returns that appearance to unread. Read/dismiss flags are convenience controls and never promote a claim to verified.

The source coverage matrix distinguishes functioning mapped sources, discovery-only coverage and gaps. A mapped source does not guarantee coverage of every named company. The latest 500 stored records are loaded for ranking; older records remain in the database. Every source also has a bounded collection window, so daily refresh frequency does not guarantee complete historical capture.

## Three different questions

| Dimension | What to establish | What does not establish it by itself |
| --- | --- | --- |
| Demand | Workload consumption, customer adoption, pricing, paid utilization, contractual terms and concentration | An announced investment, training ambition, or supplier backlog |
| Capacity | Delivered chips, energized sites, power availability, deployment dates and usable capacity | A land purchase, planned megawatts, or project announcement |
| Funding | Cash funded, financing closed, liquidity, maturities, collateral, covenants and guarantees | A headline commitment or prospective funding round |

A customer seeking more compute and a provider delaying one site can coexist. Match period, geography, workload, technology, counterparty and project status before inferring an industry shortage or demand collapse. Ask whether other suppliers absorb the workload, whether power or financing causes the delay, and whether utilization and pricing corroborate the hypothesis. These are analytical possibilities. Curated notes should investigate a claim with dated sources and preserve corrections, rather than assuming the original framing was accurate.

For a useful interpretation, write a narrow observed change, a conditional implication, its affected businesses, at least one credible alternative, and the next dated disclosure that could confirm or refute it. Unknowns should name the missing measurement or contract term rather than use a vague confidence score.

## Financing relationships

The curated ledger separates investments, customer contracts, cloud credits, debt, guarantees and concentration observations. Record the payer and recipient, instrument, amount and currency, source date, as-of date, status, source URL, and a note describing scope. Leave an unknown amount unknown. Distinguish announced, committed, drawn, funded, closed and contingent statuses using the source's language.

Use an overlap group for related announcements, revised totals, tranches and parent commitments. A funded portion plus the remaining portion may describe one commitment; the parent total must not be added again. A customer's spending commitment and a supplier's reported revenue are different measures. Credits, loan principal, guarantees, equity valuations, managed assets, planned gigawatts and revenue cannot be summed into a meaningful funding total.

The MVP deliberately does not compute an aggregate financing total. A cycle of counterparties does not prove that the same dollars circulate or that a transaction is fake. The practical questions concern who bears credit risk, how cash converts to delivered services, cancellation rights, collateral reuse, related-party terms and customer concentration. Do not assign an unnamed obligation to a named company without evidence.

## Earnings comparisons

Record the company, fiscal period, metric, units, source date and source URL. Keep reported results, management guidance, separately sourced consensus and the analyst's implication distinct. Missing consensus is unavailable, not zero and not management guidance. A beat or miss requires a comparable, dated pre-result consensus source.

Check fiscal period start and end, currency, scale, GAAP versus adjusted basis, segment versus consolidated scope and quarter versus year-to-date duration before comparing. Keep cash capital expenditure, finance-lease additions and lease principal distinct unless the issuer explicitly defines a combined measure. A prior quarter's filing must not silently substitute for a new release whose periodic report has not been filed. An upcoming earnings-call announcement is not a reported result.

The imported earnings table is curated evidence, not an automatic full-filing or full-transcript analysis. Claims about management's answers require the actual relevant speech and a clear speaker; missing Q&A remains a gap.

## Interpreting a default probability

The app does not assert that CoreWeave currently has a 60% probability of default. That question requires the original dated quote, reference entity, instrument, tenor, recovery assumption, pricing convention and definition of default. An equity drawdown, bond price, CDS spread and real-world default probability are different quantities.

For education, a flat-hazard approximation uses:

```text
s = annual CDS spread in basis points / 10,000
R = assumed recovery fraction, with 0 <= R < 1
T = horizon in years
lambda ~= s / (1 - R)
cumulative risk-neutral probability ~= 1 - exp(-lambda * T)
```

This approximation assumes constant hazard and recovery and simplifies premium/default cash-flow timing. The result changes with horizon and recovery. It is not a full CDS pricer; actual calibration accounts for payment dates, discounting and accrued premium. BIS Working Paper 921, Appendix B, explains the fee/default-leg approach and exponential survival formulation. [BIS, January 2021](https://www.bis.org/publications/working-paper-921-firm-specific-risk-neutral-distributions-options-and-cds.pdf)

Risk-neutral probabilities are pricing measures. CDS spreads also compensate sellers for bearing risk, so the inferred number is not a direct statistical forecast of defaults. Liquidity, quote quality and contract features also require investigation before interpreting a particular market observation. A five-year cumulative percentage must not be described as an annual probability. [BIS, December 2005](https://www.bis.org/publications/risk-aversion-and-risk-premia-cds-market.pdf)

Any calculator inputs are illustrative or user supplied. They are not live quotes or a credit assessment of a named issuer. Do not backfill an assumed market spread merely to reproduce a headline percentage.

## Source access and freshness

The SEC's public submissions and XBRL APIs do not require an API key. They expose filing and financial-data metadata; issuer and fiscal-period checks are still necessary. [SEC API documentation](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)

SEC fair-access guidance caps a user's total requests at 10 per second across machines and asks automated clients to declare their User-Agent. The collector should stay well below that ceiling, request only needed data, and record failures rather than evade access controls. A declared identity must be truthful. [SEC developer resources](https://www.sec.gov/about/developer-resources), [access guidance](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data)

Refresh success means an endpoint was fetched and parsed, not that the underlying company has published a recent update. Check both last successful retrieval and the newest source date. Previously stored evidence remains historical after a failed refresh. A stale-source warning is a prompt to check coverage, not a market signal.

No comprehensive X trend feed is connected. Manual X/Twitter status links are saved as unverified leads without fetching the post or collecting engagement metrics. A saved link is not evidence that its content is true, available, current or representative. Verification requires a separate primary source.

Production data and manual curation belong in the local data store. Synthetic fixtures belong only under `tests/fixtures/`; no demo item is mixed into the real feed. Daily snapshots preserve what the app knew at a point in time. They do not retroactively turn later knowledge into earlier evidence.

Methodology sources checked on 2026-10-24. Company examples require their own dated evidence.
