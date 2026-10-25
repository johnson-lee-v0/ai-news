"""Auditable, bounded public-source watchlist. Discovery results are leads, not proof."""
from urllib.parse import urlencode


def _source(id, name, url, kind, role, topics, entities, quality_note, **extra):
    return dict(id=id, name=name, url=url, kind=kind, role=role, format="rss",
                topics=topics, entities=entities, quality_note=quality_note,
                cadence_hint="on manual or approved daily refresh", enabled=True,
                coverage_note="Selected feed window; absence is not evidence that no development occurred.",
                max_items=40, **extra)


def _search(id, name, query, topics, entities):
    return _source(id, name, "https://news.google.com/rss/search?" + urlencode({
        "q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"}),
        "discovery_lead", "discovery", topics, entities,
        "Search-index lead. Publisher attribution is preserved, but article bodies and claims are not verified. Syndications are not independent corroboration.",
        query=query, lookback_days=30 if "30d" in query else 7)


SOURCES = [
    _source("nvidia-news", "NVIDIA Newsroom", "https://nvidianews.nvidia.com/releases.xml", "company_ir", "primary",
            ["demand", "capacity", "product"], ["NVIDIA"], "Issuer announcements and descriptions; statements are not independent verification.", entity="NVIDIA"),
    _source("amd-ir", "AMD Investor Relations", "https://ir.amd.com/news-events/press-releases/rss", "company_ir", "primary",
            ["earnings", "capacity", "funding"], ["AMD"], "Issuer IR feed; announced commitments are not cash received or recognized revenue.", entity="AMD"),
    _source("microsoft-blog", "Microsoft Official Blog", "https://blogs.microsoft.com/feed/", "company_ir", "primary",
            ["demand", "capacity", "product"], ["Microsoft"], "Issuer corporate blog; not a comprehensive earnings or financial-news source.", entity="Microsoft"),
] + [
    {**_source("sec-" + symbol.lower(), company + " · SEC", "https://data.sec.gov/submissions/CIK" + cik + ".json",
              "sec_filing", "primary", ["earnings", "funding", "filings"], [company],
              "SEC submission metadata only. Filing bodies and exhibits are not automatically extracted.", entity=company),
     "format": "sec", "cik": cik, "max_items": 15}
    for company, symbol, cik in [
        ("CoreWeave", "CRWV", "0001769628"), ("NVIDIA", "NVDA", "0001045810"),
        ("Microsoft", "MSFT", "0000789019"), ("Meta", "META", "0001326801"),
        ("Amazon", "AMZN", "0001018724")]
] + [
    _source("openai-news", "OpenAI News", "https://openai.com/news/rss.xml", "company_ir", "primary",
            ["product", "demand", "funding", "policy"], ["OpenAI"], "Official issuer feed; it may omit contested financing reports. Latest 40 entries only.", entity="OpenAI"),
    _source("google-ai", "Google AI Blog", "https://blog.google/technology/ai/rss/", "company_ir", "primary",
            ["product", "demand", "capacity"], ["Alphabet"], "Official Google AI announcements; product claims do not establish monetization.", entity="Alphabet"),
    _source("techcrunch-ai", "TechCrunch · AI", "https://techcrunch.com/category/artificial-intelligence/feed/", "news_report", "secondary",
            ["funding", "valuation", "product", "policy"], [], "Reported news and analysis; confirm material financial terms with original disclosures where available."),
    _source("cnbc-tech", "CNBC · Technology", "https://www.cnbc.com/id/19854910/device/rss/rss.html", "news_report", "secondary",
            ["funding", "valuation", "earnings", "demand"], [], "Technology reporting, including opinion and subscriber headlines. RSS access does not establish full-article access."),
    _source("dcd-news", "Data Center Dynamics", "https://www.datacenterdynamics.com/en/rss/", "news_report", "secondary",
            ["capacity", "power", "funding", "permits"], [], "Specialist infrastructure reporting. Sponsored items are labeled and should not be treated as independent reporting."),
    _search("discovery-lab-funding", "Discovery · OpenAI & Anthropic funding",
            "(OpenAI OR Anthropic) (valuation OR funding OR IPO OR debt) when:30d",
            ["funding", "valuation"], ["OpenAI", "Anthropic"]),
    _search("discovery-capacity", "Discovery · AI capacity & power",
            '("data center" OR "data centre") (AI OR GPU) (power OR capacity OR cancel OR delay) when:7d',
            ["capacity", "power", "permits"], []),
    _search("discovery-earnings", "Discovery · AI earnings & capex",
            "(Nvidia OR AMD OR Microsoft OR Meta OR Amazon OR Oracle OR CoreWeave) (earnings OR guidance OR capex) when:7d",
            ["earnings", "capacity", "funding"], ["NVIDIA", "AMD", "Microsoft", "Meta", "Amazon", "Oracle", "CoreWeave"]),
]
# Public search RSS returns up to 100 ranked results. Retain the whole bounded result
# page rather than silently dropping the valuation story after the first few hits.
for source in SOURCES:
    if source["role"] == "discovery":
        source["max_items"] = 100

COVERAGE_GAPS = [
    {"id": "anthropic-official", "name": "Anthropic official news", "url": "https://www.anthropic.com/news",
     "status": "manual_review", "reason": "No official RSS adapter is configured. Dedicated funding search adds discovery coverage, not official-document verification."},
    {"id": "x-trends", "name": "X posts and trends", "url": "https://x.com",
     "status": "not_connected", "reason": "No automated authenticated X feed, engagement ranking or comprehensive trending coverage. Saved links are leads only."},
    {"id": "market-feeds", "name": "Live prices, CDS and consensus", "url": None,
     "status": "not_connected", "reason": "No live market, credit-quote or consensus subscription. Historical quotes keep their publication date and horizon."},
]
