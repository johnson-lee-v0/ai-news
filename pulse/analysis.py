"""Transparent triage rules, never unsourced factual investment conclusions."""
from datetime import datetime, timezone
import re
import hashlib
import unicodedata

RULES = {
    "funding": {
        "terms": ("financing", "funding", "debt", "credit", "loan", "guarantee", "investment", "invests", "notes offering", "capital raise", "convertible", "equity stake", "valuation", "fundraising", "fundraise", "ipo", "liquidity", "cash burn", "refinancing", "warrant"),
        "implication": "If the financing closes on usable terms, it may fund capacity before customer cash arrives. It does not establish incremental end-demand or recognized revenue.",
        "beneficiaries": "Conditional: the financed operator and its equipment suppliers if funds become available and are spent.",
        "risks": "Potential pressure: creditors and equity holders if utilization, customer collections or refinancing disappoint.",
        "counterevidence": "A headline amount may be an undrawn facility, conditional commitment or refinancing. Customer and investor overlap alone does not invalidate a transaction.",
        "confirms": "Executed terms, cash received, maturity schedule, collateral, guarantees, customer concentration and subsequent utilization.",
        "refutes": "Unmet funding conditions, canceled commitments, offsetting repayments, or no incremental cash available.",
    },
    "earnings": {
        "terms": ("earnings", "financial results", "quarter results", "quarterly results", "fiscal", "revenue", "guidance", "10-q", "10-k"),
        "implication": "Compare the same fiscal period and metric before drawing a read-through. An earnings date announcement is not a reported result; guidance is management's forecast.",
        "beneficiaries": "Conditional: suppliers with documented exposure to realized revenue growth or funded capital expenditure.",
        "risks": "Potential pressure: exposed businesses if growth misses sourced expectations, margins weaken or cash conversion falls.",
        "counterevidence": "Bookings, backlog and commitments can outpace realized revenue. Mix, timing and working capital can explain apparent divergences.",
        "confirms": "Primary release and filing for the completed period; metric definitions; cash flow; guidance bridge and separately dated consensus.",
        "refutes": "Announcement is only a scheduled call, mismatched fiscal periods, different metric definitions or a material cash-flow contradiction.",
    },
    "capacity": {
        "terms": ("data center", "data centre", "datacenter", "capacity", "gigawatt", "megawatt", "campus", "compute infrastructure", "gpu", "chips", "power", "factory", "manufacturing"),
        "implication": "If announced capacity reaches service on schedule, supply can expand. A project delay may reflect power, permits or location choices; it does not by itself prove weak demand.",
        "beneficiaries": "Conditional: power, cooling, networking and semiconductor suppliers with actual contracted exposure.",
        "risks": "Potential pressure: operators carrying idle assets or construction obligations before customers and power are ready.",
        "counterevidence": "Announcements may cover planned rather than operating assets. Capacity can move between regions without changing total demand.",
        "confirms": "Commissioning dates, power/interconnection approvals, delivered hardware, customer acceptance and utilization.",
        "refutes": "Permits or power fail, schedules slip, capacity is relocated, or delivery and usage do not follow the announcement.",
    },
    "demand": {
        "terms": ("demand", "customer", "contract", "backlog", "adoption", "partnership", "cloud", "inference", "training", "ai"),
        "implication": "If announced adoption or contracts translate into paid, recurring usage, demand may strengthen. Customer statements and commitments alone do not measure utilization or cash receipts.",
        "beneficiaries": "Conditional: compute providers and suppliers able to fulfill the specific workload profitably.",
        "risks": "Potential pressure: providers exposed to concentration, price concessions or workloads funded by temporary credits.",
        "counterevidence": "Pilot usage, cloud credits, cancellable backlog or overlapping announcements may overstate durable external demand.",
        "confirms": "Named contract terms, external customer spending, billed usage, cash collections and retention after credits expire.",
        "refutes": "Canceled or duplicated commitments, low utilization, weak collections or subsidized usage that does not renew.",
    },
    "other": {
        "terms": (),
        "implication": "No specific operational implication is established by this source metadata. Read the original before connecting it to the supply chain.",
        "beneficiaries": "Unresolved until the primary document identifies an economic exposure.",
        "risks": "Unresolved; no directional market call is inferred.",
        "counterevidence": "The item may be administrative or unrelated to AI economics.",
        "confirms": "An explicit, dated disclosure connecting the event to demand, capacity, funding or reported earnings.",
        "refutes": "The full document provides no material connection to those questions.",
    },
}


def parse_time(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


RULES["models"] = {
    "terms": ("model", "benchmark", "tokens", "token price", "open source", "open weight", "reasoning", "agent", "agents", "latency", "accuracy", "cost per", "distillation"),
    "implication": "If a model delivers comparable task quality at a lower total cost, adoption and margins could change. A launch or selected benchmark alone does not establish profitable production use.",
    "beneficiaries": "Conditional: users and application providers if quality-adjusted cost falls; efficient infrastructure suppliers if total usage expands.",
    "risks": "Potential pressure: providers whose pricing advantage or margins depend on a performance lead that narrows.",
    "counterevidence": "Selected benchmarks may exclude retries, human review, latency, reliability or energy. Cheaper tokens can increase total compute demand.",
    "confirms": "Independent evaluations on the same task, transparent pricing, end-to-end cost and sustained paid production use.",
    "refutes": "Quality or reliability fails in production, advertised cost excludes necessary overhead, or demand does not persist."
}
RULES["policy"] = {
    "terms": ("export control", "export ban", "regulation", "antitrust", "permit", "moratorium", "sanction", "chip ban", "copyright", "restriction"),
    "implication": "If the rule is binding and applies to the named activity, market access, project timing or costs may change. A proposal, political statement and effective rule are different stages.",
    "beneficiaries": "Conditional: compliant suppliers or alternative regions if demand moves and equivalent capacity exists.",
    "risks": "Potential pressure: firms with documented affected products, customers, sites or contractual exposure.",
    "counterevidence": "Exemptions, court orders, transition periods and implementation details may materially limit the headline effect.",
    "confirms": "Official rule text, effective date, scope, exemptions and company-specific disclosures of exposure.",
    "refutes": "A proposal is withdrawn, stayed, narrowed, or does not apply to the relevant products or projects."
}

WATCHLIST = ["OpenAI", "Anthropic", "NVIDIA", "AMD", "Microsoft", "Amazon", "Alphabet", "Meta", "CoreWeave", "Oracle", "Broadcom", "TSMC", "SpaceX"]
ALIASES = {"OpenAI": ("openai", "chatgpt"), "Anthropic": ("anthropic", "claude"), "NVIDIA": ("nvidia",), "AMD": ("amd", "advanced micro devices"), "Microsoft": ("microsoft", "azure"), "Amazon": ("amazon", "aws"), "Alphabet": ("alphabet", "google", "deepmind"), "Meta": ("meta", "facebook"), "CoreWeave": ("coreweave",), "Oracle": ("oracle",), "Broadcom": ("broadcom",), "TSMC": ("tsmc",), "SpaceX": ("spacex", "xai", "grok")}
DOMAINS = [
    ("funding", "Funding & valuation", "Can the builders pay for their commitments?", ["OpenAI", "Anthropic", "CoreWeave", "Oracle"]),
    ("demand", "Paid demand", "Is usage becoming recurring cash receipts?", ["OpenAI", "Anthropic", "Microsoft", "Amazon", "Alphabet"]),
    ("capacity", "Capacity & power", "What is planned, energized, delivered and actually used?", ["NVIDIA", "AMD", "CoreWeave", "Oracle", "Broadcom", "TSMC"]),
    ("earnings", "Results & guidance", "Did results and outlook change for comparable periods?", WATCHLIST),
    ("models", "Model economics", "Does better or cheaper AI change real production economics?", ["OpenAI", "Anthropic", "Alphabet", "Meta"]),
    ("policy", "Policy & constraints", "What rules or physical constraints alter delivery or access?", WATCHLIST),
]


def contains(text, term):
    return bool(re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", text))


def enrich(article, now=None):
    now = now or datetime.now(timezone.utc)
    item = dict(article)
    text = (item.get("title", "") + " " + item.get("summary", "")).lower()
    title = item.get("title", "").lower()
    scores = {key: sum(contains(text, term) for term in rule["terms"]) for key, rule in RULES.items() if key != "other"}
    matched = [key for key, count in scores.items() if count]
    lens = max(scores, key=scores.get) if any(scores.values()) else "other"
    if scores["funding"]:
        lens = "funding"
    elif scores["earnings"]:
        lens = "earnings"
    elif scores["policy"]:
        lens = "policy"
    rule = RULES[lens]
    entities = set(item.get("entities") or [])
    for entity, aliases in ALIASES.items():
        if any(contains(text, alias) for alias in aliases):
            entities.add(entity)
    item["entities"] = sorted(entities)
    published = parse_time(item.get("published_at"))
    age = (now - published).total_seconds() / 86400 if published else None
    freshness = 20 if age is not None and 0 <= age <= 2 else 14 if age is not None and 0 <= age <= 7 else 6 if age is not None and 0 <= age <= 30 else 0
    material_terms = ("valuation", "fundraising", "funding", "liquidity", "default", "cash flow", "cash burn", "capex", "capital expenditure", "financial results", "guidance", "cancels", "canceled", "withdraws", "cuts", "delay", "debt", "export control", "megawatt", "gigawatt")
    material_hits = sum(contains(text, term) for term in material_terms)
    materiality = min(34, material_hits * 8 + (8 if lens in ("funding", "earnings") else 0))
    economics = min(14, sum(scores.values()) * 2)
    watch = 10 if set(entities) & set(WATCHLIST) else 3 if matched else 0
    role = item.get("source_role") or ("primary" if item.get("kind") in ("company_ir", "sec_filing") else "secondary")
    evidence = {"primary": 10, "secondary": 7, "discovery": 1}.get(role, 1)
    noise = 20 if any(term in text for term in ("geforce now", "call of duty", "game ready driver", "best deals", "coupon", "black friday")) and not any(term in text for term in ("data center", "financial results", "ai infrastructure")) else 0
    if any(term in title for term in ("founder summit", "founders summit", "buy tickets", "save on tickets", "sponsored", "register now", "sponsor content")):
        noise += 50
    if any(term in title for term in ("evil twin", "stocks to buy", "stock to buy", "could skyrocket", "could make you", "my top", "millionaire maker")):
        noise += 30
    scheduled = any(term in title for term in ("to report", "will report", "announces date", "sets date", "earnings call scheduled"))
    if scheduled:
        noise += 12
        materiality = min(materiality, 8)
    ai_context = bool(set(entities) & set(WATCHLIST)) or any(contains(text, term) for term in ("ai", "artificial intelligence", "data center", "datacenter", "compute", "inference", "semiconductor"))
    relevance = "material" if material_hits and ai_context and not noise else "watch" if matched and ai_context and not noise else "background"
    if age is None or age < 0 or age > 90:
        relevance = "background"
    elif age > 30 and relevance == "material":
        relevance = "watch"
    priority = {"recency": freshness, "material_terms": materiality, "topic_relevance": economics, "watchlist": watch, "source_type": evidence, "noise_adjustment": -noise}
    item.update({key: rule[key] for key in ("implication", "beneficiaries", "risks", "counterevidence", "confirms", "refutes")})
    # A lower proposed valuation is not automatically a cash shortfall or weaker compute demand.
    if lens == "funding" and any(contains(text, term) for term in ("valuation", "ipo")):
        item["implication"] = "Check final valuation, cash proceeds and investor protections: a target or IPO expectation is not a completed financing. If terms move lower, the same cash raise may be more dilutive; if proceeds or timing disappoint, funding capacity may weaken. Valuation bargaining alone does not establish weaker paid compute demand."
    if scheduled:
        item["implication"] = "This is a scheduled reporting event, not a reported result. Wait for the completed-period release before comparing revenue, margins, cash flow, guidance or separately sourced consensus."
    review_status = item.get("review_status") or "unreviewed"
    if review_status != "unreviewed" and item.get("reviewed_hash") != item.get("content_hash"):
        review_status = "unreviewed"
    item.update({"lens": lens, "topic": lens, "lenses": matched, "event_flags": matched,
                 "score": max(0, sum(priority.values())), "priority_factors": priority, "relevance": relevance,
                 "score_reason": "%s recency + %s material-term relevance + %s topic + %s watchlist + %s source-type − %s noise. Transparent triage only; not a market-impact or probability estimate." % (freshness, materiality, economics, watch, evidence, noise),
                 "observation": item.get("title", "Untitled source item"),
                 "uncertainty": "Conditional rule using title, supplied description or filing metadata. No full-document verification or independent corroboration is implied. Publication recency and the source type affect ranking; a high score does not establish truth.",
                 "published_age_days": age, "stale": age is None or age > 7 or age < 0,
                 "inference_type": "conditional_rule", "source_role": role,
                 "review_status": review_status})
    if role == "discovery":
        item["uncertainty"] += " Search-feed discovery lead: open the original publisher, check the date and trace the underlying disclosure before accepting the claim."
    if item.get("kind") == "sec_filing":
        item["uncertainty"] += " SEC filing detection is metadata only; numeric results and contractual terms have not been extracted."
    return item


def story_key(article):
    """Conservative exact-title grouping. Distinct numbers/claims are never fuzzily merged."""
    title = unicodedata.normalize("NFKC", article.get("title", "")).lower()
    publisher = (article.get("publisher_name") or article.get("source_name") or "").lower().strip()
    if publisher and title.endswith(" - " + publisher):
        title = title[:-(len(publisher) + 3)]
    normalized = re.sub(r"[^a-z0-9]+", " ", title).strip()
    published = (article.get("published_at") or "unknown")[:10]
    if not normalized:
        normalized = str(article.get("id", "unknown"))
    return hashlib.sha256((normalized + "|" + published).encode()).hexdigest()[:20]


def group_stories(articles):
    groups = {}
    for article in articles:
        groups.setdefault(story_key(article), []).append(article)
    stories = []
    for key, group in groups.items():
        # Prefer a publisher source over a discovery wrapper, unless it was locally dismissed.
        ordered = sorted(group, key=lambda a: (a.get("review_status") != "dismissed", {"primary": 3, "secondary": 2, "discovery": 1}.get(a.get("source_role"), 0), a["score"]), reverse=True)
        head = dict(ordered[0])
        head.update(story_id=key, article_ids=[a["id"] for a in ordered if a.get("id")], related_count=len(group)-1,
                    related_sources=[{"name": a.get("source_name"), "url": a.get("url"), "role": a.get("source_role"), "article_id": a.get("id")} for a in ordered[1:]],
                    grouping_note="Matching title and publication day only. Related appearances may repeat one report; they are not independent confirmations.")
        stories.append(head)
    stories.sort(key=lambda a: (a["score"], a.get("published_at") or ""), reverse=True)
    return stories


def coverage(sources, now):
    domains = []
    for key, name, question, entities in DOMAINS:
        aliases = {"models": {"models", "product"}, "policy": {"policy", "permits"}, "funding": {"funding", "valuation"}, "capacity": {"capacity", "power"}}.get(key, {key})
        mapped = [s for s in sources if aliases & set(s.get("topics") or s.get("source_topics") or [])]
        available = [s for s in mapped if s.get("status") == "ok" and parse_time(s.get("last_success_at")) and 0 <= (now - parse_time(s["last_success_at"])).total_seconds() <= 48*3600]
        direct = [s for s in available if s.get("role") in ("primary", "secondary")]
        status = "covered" if direct else "discovery_only" if available else "gap"
        domains.append({"id": key, "name": name, "question": question, "entities": entities,
                        "connected_sources": [s["id"] for s in available], "status": status,
                        "note": "A working source is mapped to this question; completeness and every named company are not guaranteed." if direct else "Discovery leads only; source verification is still required." if available else "No mapped source succeeded within 48 hours. Use a targeted manual source check."})
    return {"domains": domains,
            "gaps": ["X trends/session coverage is not connected.", "Live CDS and consensus estimates are not connected.", "SEC coverage is selected recent filing metadata, not full-text financial extraction.", "Anthropic has discovery coverage; no direct Anthropic official news feed is connected.", "RSS search results are a bounded discovery sample; publication dates and original reporting require review."],
            "source_health": {"ok": sum(s.get("status") == "ok" for s in sources), "total": len(sources)},
            "note": "Source health measures fetch success. Topic coverage measures mapped sources. Neither proves all important news was found."}


def compose(data, now=None):
    now = now or datetime.now(timezone.utc)
    reviews = data.get("reviews", {})
    articles = [enrich({**a, **reviews.get(a.get("id"), {})}, now) for a in data.get("articles", [])]
    articles.sort(key=lambda a: (a["score"], a.get("published_at") or "", a.get("first_seen_at") or ""), reverse=True)
    stories = group_stories(articles)
    refreshes = data.get("refreshes", [])
    latest = refreshes[0] if refreshes else {}
    sources = data.get("sources", [])
    ok = sum(s.get("status") == "ok" for s in sources)
    recent = [a for a in stories if a["published_age_days"] is not None and 0 <= a["published_age_days"] <= 2]
    fresh_count = latest.get("new_count", 0)
    changed = latest.get("changed_count", 0)
    headline = "%s discovered · %s revised in selected coverage" % (fresh_count, changed) if refreshes else "Your evidence brief starts with a refresh"
    if refreshes and not recent:
        headline += ". No feed or filing date in the past 48 hours."
    bullets = (["%s loaded articles shown as %s story groups; %s have feed or filing dates within 48 hours. Search-feed dates may be updates; original publication still needs checking." % (len(articles), len(stories), len(recent)),
                "The latest refresh found %s new and %s revised items. Exact repeats stay in history; similar coverage does not count as independent confirmation." % (fresh_count, changed),
                "%s of %s configured sources succeeded on their latest attempt. Discovery searches widen coverage but do not verify claims." % (ok, len(sources))]
               if refreshes else ["Refresh official feeds, reporting and targeted discovery searches.", "No fixture stories are loaded into the real feed."])
    actionable = [a for a in stories if a["review_status"] != "dismissed" and a["relevance"] == "material"]
    # A short brief should not spend every slot on retellings of one company's event.
    priority_items, represented = [], set()
    candidates = actionable + [a for a in stories if a["review_status"] != "dismissed" and a["relevance"] == "watch"]
    for article in candidates:
        subject = next((entity for entity in WATCHLIST if contains(article.get("title", "").lower(), entity.lower())), None)
        subject = subject or next((entity for entity in article.get("entities", []) if entity in WATCHLIST), None)
        bucket = subject or ("sector:" + article["lens"])
        if bucket in represented:
            continue
        represented.add(bucket)
        priority_items.append(article)
        if len(priority_items) == 6:
            break
    questions = [{"topic": key, "question": question, "items": sum(a["topic"] == key for a in actionable)} for key, name, question, entities in DOMAINS]
    return {**data, "articles": articles, "stories": stories, "as_of": now.isoformat(),
            "coverage": coverage(sources, now), "watchlist": {"entities": WATCHLIST, "topics": [x[0] for x in DOMAINS]},
            "brief": {"headline": headline, "bullets": bullets, "priority_questions": questions, "priority_items": priority_items,
                      "coverage_note": "Selected official feeds + reporting + public search RSS. Ranked by cash, orders, delivery and economics terms; automatic implications remain conditional prompts. X and market-wide completeness are not claimed."},
            "stats": {"articles": len(articles), "total_articles": data.get("total_count", len(articles)), "story_count": len(stories), "new_items": fresh_count, "changed_items": changed, "last_refresh": latest.get("finished_at"), "source_ok": ok, "source_total": len(sources), "recent_items": len(recent), "discovery_items": sum(a["source_role"] == "discovery" for a in articles), "needs_review": sum(a["review_status"] == "unreviewed" and a["relevance"] == "material" for a in stories)}}
