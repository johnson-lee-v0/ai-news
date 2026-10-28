"""Five-layer economic context and transparent, non-exclusive metadata tags."""
from datetime import datetime, timezone
import re

FRAMEWORK_SOURCE = {
    "title": "Jensen Huang: AI Is a 5-Layer Cake",
    "url": "https://blogs.nvidia.com/blog/ai-5-layer-cake/",
    "date": "2026-03-10",
}

LAYERS = (
    {"id": "energy", "name": "Energy", "summary": "Electricity and cooling that can actually reach the machines.",
     "takeaway": "Power that reaches a site enables revenue; connection delays can leave financed equipment idle.",
     "metrics": ["Energized MW", "Grid connection dates", "Power and cooling cost"],
     "terms": ("power", "electricity", "grid", "cooling", "energy", "fuel cell", "megawatt", "gigawatt", "mw", "gw"),
     "sources": ("dcd-news", "discovery-capacity")},
    {"id": "chips", "name": "Chips", "summary": "Processors, memory and packaging that are qualified and shipped.",
     "takeaway": "Qualified chip and memory shipments can relieve bottlenecks; announced factories do not yet add usable supply.",
     "metrics": ["Qualified and shipped chips", "HBM supply", "Packaging capacity and yields"],
     "terms": ("gpu", "gpus", "chip", "chips", "semiconductor", "hbm", "packaging", "substrate", "substrates", "vera rubin", "blackwell"),
     "sources": ("nvidia-news", "amd-ir", "sec-nvda")},
    {"id": "infrastructure", "name": "Infrastructure", "summary": "Data centers and clouds turning installed systems into paid compute.",
     "takeaway": "Utilization, rental prices and collections determine returns; installed capacity alone does not cover debt service.",
     "metrics": ["Operating capacity and utilization", "Rental rates", "Capex, financing and liquidity"],
     "terms": ("data center", "data centers", "data centre", "data centres", "datacenter", "cloud", "ai factory", "ai factories", "compute", "capex", "coreweave", "nebius", "nscale"),
     "sources": ("dcd-news", "microsoft-blog", "sec-crwv", "sec-msft", "sec-meta", "sec-amzn", "discovery-capacity")},
    {"id": "models", "name": "Models", "summary": "Useful model capability at a sustainable cost and reliability.",
     "takeaway": "Cheaper successful tasks can expand paid adoption; weak reliability and retries can erase lower token prices.",
     "metrics": ["Cost per successful task", "Reliability", "Paid model usage"],
     "terms": ("language model", "foundation model", "llm", "openai", "anthropic", "inference", "training", "token", "tokens", "reasoning model", "model economics", "model release", "gr00t"),
     "sources": ("openai-news", "google-ai", "techcrunch-ai", "discovery-lab-funding")},
    {"id": "applications", "name": "Applications", "summary": "Products that customers keep paying for because they deliver value.",
     "takeaway": "Repeat paid use and gross profit support durable adoption; demos and free users do not establish customer returns.",
     "metrics": ["Paid adoption and retention", "Gross profit", "Customer ROI"],
     "terms": ("ai application", "ai applications", "ai apps", "copilot", "chatgpt", "software agent", "industrial agent", "customer service", "drug discovery", "autonomous", "robotics", "humanoid"),
     "sources": ("microsoft-blog", "google-ai", "techcrunch-ai")},
)
LAYER_IDS = tuple(layer["id"] for layer in LAYERS)


def annotate(article):
    """Match source text only; never infer measurements or company exposures."""
    item = dict(article)
    explicit = item.get("ai_layers")
    if isinstance(explicit, list) and all(value in LAYER_IDS for value in explicit):
        item["ai_layers"] = [key for key in LAYER_IDS if key in explicit]
        item["layer_match_basis"] = "Curator mapping; the underlying claims still need their stated evidence."
        return item
    text = " ".join(str(item.get(key) or "") for key in ("title", "summary", "observation")).lower()
    matches = {}
    for layer in LAYERS:
        found = [term for term in layer["terms"] if re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", text)]
        if found:
            matches[layer["id"]] = found
    item["ai_layers"] = list(matches)
    item["layer_match_basis"] = "Keywords in the source title/summary; a reading aid, not verified exposure."
    item["layer_match_terms"] = matches
    return item


def _time(value):
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp.astimezone(timezone.utc)
    except (ValueError, TypeError, AttributeError):
        return None


def tracking(articles, sources, now=None, static=False):
    now = now or datetime.now(timezone.utc)
    cards = []
    for layer in LAYERS:
        matches = [item for item in articles if layer["id"] in item.get("ai_layers", [])]
        appearances = [appearance for item in matches for appearance in item.get("layer_matches", [item]) if layer["id"] in appearance.get("ai_layers", [])]
        observed_sources = {item.get("source_id") for item in appearances}
        mapped = [source for source in sources if source["id"] in observed_sources or (not static and source["id"] in layer["sources"])]
        fresh = [source for source in mapped if source.get("status") == "ok" and _time(source.get("last_success_at")) and 0 <= (now - _time(source["last_success_at"])).total_seconds() <= 48 * 3600]
        status = ("reviewed_snapshot" if matches else "gap") if static else ("connected" if any(source.get("role") in ("primary", "secondary") for source in fresh) else "discovery_only" if fresh else "gap")
        dated = [(item.get("published_at"), _time(item.get("published_at"))) for item in appearances if item.get("date_precision") != "future_unverified"]
        valid = [(raw, date) for raw, date in dated if date and date <= now]
        latest = max(valid, key=lambda pair: pair[1])[0] if valid else None
        cards.append({key: layer[key] for key in ("id", "name", "summary", "takeaway", "metrics")})
        cards[-1].update(article_count=len(matches), source_ids=[source["id"] for source in mapped], last_source_date=latest,
                         status=status, metric_status="Unavailable — not a measured metrics feed",
                         gap="No measured layer metrics are connected. Source dates may be filing or discovery-feed dates; inspect each record. " +
                         ("No matched item in this snapshot." if static and not matches else "Public snapshot only; no automatic public refresh." if static else "Mapped source health does not establish full coverage or verify a headline."))
    return {"source": dict(FRAMEWORK_SOURCE), "method": "Five non-exclusive research lenses. Local tags match source metadata; public editorial mappings are explicit. One story may span several layers; counts must not be added as unique stories.",
            "scope": "Reviewed public snapshot; local refreshes do not publish it." if static else "Selected local feeds and discovery searches; evaluated when the dashboard refreshes. No new background service is installed.",
            "layers": cards}
