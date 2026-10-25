"""Small, polite public-source ingester. No login, paid API, or X scraping."""
import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path

from . import storage

UTC = timezone.utc
USER_AGENT = "AIStockPulse/0.2 local single-user public-company research"
MAX_RESPONSE_BYTES = 2_000_000
FETCH_TIMEOUT = 12
from .catalog import SOURCES


def utc_now():
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.suppressed = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.suppressed += 1
        if tag in ("p", "div", "br", "li"):
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.suppressed = max(0, self.suppressed - 1)
        self.parts.append(" ")

    def handle_data(self, data):
        if not self.suppressed:
            self.parts.append(data)


def plain_text(value):
    parser = PlainText()
    parser.feed(value or "")
    return re.sub(r"\s+", " ", "".join(parser.parts)).strip()


def canonical_url(value):
    parts = urllib.parse.urlsplit((value or "").strip())
    if parts.scheme not in ("https", "http") or not parts.hostname or parts.username or parts.password:
        raise ValueError("Article URL must be public HTTP(S)")
    if parts.hostname.lower() in ("localhost", "127.0.0.1", "::1"):
        raise ValueError("Local article URLs are not public evidence")
    query = [(key, val) for key, val in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
             if not key.lower().startswith("utm_") and key.lower() not in ("fbclid", "gclid", "mc_cid", "mc_eid")]
    return urllib.parse.urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path or "/",
                                   urllib.parse.urlencode(sorted(query)), ""))


def parse_date(value, now=None):
    """Return UTC date + precision without manufacturing a missing source timestamp."""
    if not value or not str(value).strip():
        return None, "unknown"
    value = str(value).strip()
    precision = "day" if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) else "second"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(value)
        except (ValueError, TypeError, OverflowError):
            return None, "unknown"
    if parsed.tzinfo is None:
        if precision != "day":
            return None, "unknown_timezone"
        parsed = parsed.replace(tzinfo=UTC)
    parsed = parsed.astimezone(UTC)
    # Retain bad source dates for inspection, but do not portray them as published today.
    if parsed > (now or datetime.now(UTC)) + timedelta(minutes=5):
        precision = "future_unverified"
    return parsed.isoformat(timespec="seconds").replace("+00:00", "Z"), precision


def classify(text, entity):
    lowered = text.lower()
    entities = {entity} if entity else set()
    aliases = {"NVIDIA": ["nvidia"], "AMD": ["amd", "advanced micro devices"],
               "Microsoft": ["microsoft", "azure"], "Amazon": ["amazon", "aws"],
               "Meta": ["meta", "facebook"], "CoreWeave": ["coreweave"],
               "OpenAI": ["openai"], "Alphabet": ["google", "alphabet"],
               "Oracle": ["oracle"], "SpaceX": ["spacex"], "Anthropic": ["anthropic"]}
    for company, names in aliases.items():
        if any(re.search(r"\b" + re.escape(name) + r"\b", lowered) for name in names):
            entities.add(company)
    tags = []
    keywords = {
        "demand": ["demand", "customer", "contract", "backlog", "adoption", "usage", "revenue"],
        "capacity": ["data center", "datacenter", "compute", "gpu", "gigawatt", "megawatt", "power", "capacity", "infrastructure", "accelerator"],
        "funding": ["financ", "debt", "invest", "credit", "guarantee", "funding", "billion", "equity", "loan"],
        "earnings": ["earnings", "financial results", "quarterly results", "guidance", "10-q", "10-k"],
    }
    for tag, words in keywords.items():
        if any(word in lowered for word in words):
            tags.append(tag)
    return sorted(entities), tags


def make_article(source, title, url, summary, raw_date, observed_at, **extra):
    title = plain_text(title)[:500]
    summary = plain_text(summary)[:900]
    url = canonical_url(url)
    if not title:
        raise ValueError("Article title is empty")
    published_at, precision = parse_date(raw_date)
    entities, tags = classify(title + " " + summary, source.get("entity"))
    # Generic SEC headlines repeat across distinct filings; accession is identity.
    # Publication date also prevents an identically titled later press release
    # from being mistaken for a syndicated copy of an earlier announcement.
    fingerprint = re.sub(r"\s+", " ", title + "\n" + summary).strip().lower()
    fingerprint += "|" + str(published_at or raw_date or "")
    fingerprint += "|" + str(extra.get("accession_number", ""))
    return {"id": hashlib.sha256(url.encode()).hexdigest()[:24], "title": title,
            "url": url, "published_at": published_at, "date_precision": precision,
            "date_kind": "filing_date" if source["kind"] == "sec_filing" else "search_feed_date" if source.get("role") == "discovery" else "feed_date",
            "source_date_raw": raw_date, "observed_at": observed_at, "first_seen_at": observed_at,
            "source_id": source["id"], "source_name": source["name"], "kind": source["kind"],
            "summary": summary, "entities": entities, "tags": tags,
            "content_hash": hashlib.sha256(fingerprint.encode()).hexdigest(), **extra}


def _local_name(tag):
    return tag.rsplit("}", 1)[-1]


def parse_feed(payload, source, observed_at, with_stats=False):
    root = ET.fromstring(payload)
    if _local_name(root.tag) not in ("rss", "feed", "RDF"):
        raise ValueError("Response is not RSS or Atom")
    items = [node for node in root.iter() if _local_name(node.tag) in ("item", "entry")]
    result = []
    rejected = 0
    max_items = source.get("max_items", 40)
    for item in items[:max_items]:
        fields = {}
        link = ""
        publisher_name, publisher_url = "", ""
        for child in item:
            key = _local_name(child.tag)
            fields[key] = "".join(child.itertext())
            if key == "source":
                publisher_name = plain_text(fields[key])[:200]
                try:
                    publisher_url = canonical_url(child.attrib.get("url", ""))
                except ValueError:
                    publisher_url = ""
            if key == "link" and child.attrib.get("rel", "alternate") == "alternate":
                link = child.attrib.get("href") or fields[key]
        # A malformed item should not make every otherwise valid item disappear.
        try:
            result.append(make_article(source, fields.get("title", ""), link,
                          fields.get("description") or fields.get("summary") or fields.get("encoded") or fields.get("content", ""),
                          fields.get("pubDate") or fields.get("published") or fields.get("date") or None,
                          observed_at, publisher_name=publisher_name or source["name"],
                          publisher_url=publisher_url or source["url"],
                          verification_status="discovery_lead" if source.get("role") == "discovery" else "publisher_metadata",
                          discovered_via=source["id"]))
        except (ValueError, TypeError):
            rejected += 1
            continue
    if items and not result:
        raise ValueError("Feed contained items but none had usable titles and links")
    stats = {"rejected_count": rejected, "window_truncated_count": max(0, len(items) - max_items)}
    return (result, stats) if with_stats else result


def parse_sec(payload, source, observed_at, with_stats=False):
    data = json.loads(payload)
    if not isinstance(data, dict) or "filings" not in data:
        raise ValueError("Missing SEC submissions filing data")
    if str(data.get("cik", "")).lstrip("0") != source["cik"].lstrip("0"):
        raise ValueError("SEC company identifier does not match source")
    recent = data["filings"].get("recent")
    if not isinstance(recent, dict) or not isinstance(recent.get("form"), list):
        raise ValueError("Missing SEC recent filing arrays")
    result = []
    rejected = 0
    relevant_forms = {"10-K", "10-Q", "8-K", "20-F", "6-K", "S-1", "S-1/A", "424B4", "424B5"}
    for i, form in enumerate(recent["form"]):
        if (form[:-2] if form.endswith("/A") else form) not in relevant_forms and form not in relevant_forms:
            continue
        def field(key):
            array = recent.get(key, [])
            return array[i] if i < len(array) else ""
        accession = field("accessionNumber")
        document = field("primaryDocument")
        if not re.fullmatch(r"\d{10}-\d{2}-\d{6}", accession or "") or not document or "/" in document:
            rejected += 1
            continue
        description = field("primaryDocDescription")
        report_date = field("reportDate")
        summary = "SEC filing metadata only. Form " + form + "."
        if report_date:
            summary += " Report/event date: " + report_date + "."
        if field("items"):
            summary += " Items: " + str(field("items")) + "."
        summary += " Document contents have not been extracted; this alert does not establish a numeric result or contractual term."
        url = "https://www.sec.gov/Archives/edgar/data/" + str(int(source["cik"])) + "/" + accession.replace("-", "") + "/" + urllib.parse.quote(document)
        title = source["entity"] + " files " + form + (" — " + description if description and description != form else "")
        result.append(make_article(source, title, url, summary, field("filingDate"), observed_at,
                                  filing_form=form, report_date=report_date, accession_number=accession))
        if len(result) >= source.get("max_items", 15):
            break
    stats = {"rejected_count": rejected, "window_truncated_count": None}
    return (result, stats) if with_stats else result


def fetch_public(source):
    request = urllib.request.Request(source["url"], headers={
        "User-Agent": USER_AGENT, "Accept": "application/json,application/rss+xml,application/xml,text/xml;q=0.9",
        "Accept-Encoding": "identity"})
    with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT) as response:
        if response.status != 200:
            raise ValueError("Unexpected HTTP status " + str(response.status))
        payload = response.read(MAX_RESPONSE_BYTES + 1)
        if len(payload) > MAX_RESPONSE_BYTES:
            raise ValueError("Public response exceeded the 2 MB ingestion limit")
        return payload


def _snapshot(db_path, source, payload, response_hash):
    directory = Path(db_path).parent / "raw" / source["id"]
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / (response_hash + (".json" if source["format"] == "sec" else ".xml"))
    target.write_bytes(payload)
    # Keep five response snapshots per source; extracted article versions remain in SQLite.
    for old in sorted(directory.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)[5:]:
        old.unlink()
    return str(target.relative_to(Path(db_path).parent))


def refresh(db_path, sources=None, fetcher=None, sleep=time.sleep):
    sources = SOURCES if sources is None else sources
    fetcher = fetch_public if fetcher is None else fetcher
    storage.register_sources(db_path, sources)
    started = utc_now()
    with storage.connect(db_path) as db:
        run_id = db.execute("INSERT INTO refreshes(started_at) VALUES(?)", (started,)).lastrowid
    counts = {"new_count": 0, "changed_count": 0, "duplicate_count": 0, "error_count": 0, "skipped_count": 0, "rejected_count": 0}
    source_results = []
    for index, source in enumerate(sources):
        attempted = utc_now()
        with storage.connect(db_path) as db:
            previous = db.execute("SELECT cooldown_until FROM sources WHERE id=?", (source["id"],)).fetchone()
        if previous and previous["cooldown_until"] and previous["cooldown_until"] > attempted:
            counts["skipped_count"] += 1
            source_results.append({"id": source["id"], "status": "cooldown", "until": previous["cooldown_until"]})
            continue
        try:
            payload = fetcher(source)
            response_hash = hashlib.sha256(payload).hexdigest()
            parser = parse_sec if source["format"] == "sec" else parse_feed
            articles, parse_stats = parser(payload, source, attempted, with_stats=True)
            snapshot = _snapshot(db_path, source, payload, response_hash)
            with storage.connect(db_path) as db:
                for article in articles:
                    status = storage.save_article(db, article, response_hash, return_status=True)
                    counts[{"new": "new_count", "changed": "changed_count", "duplicate": "duplicate_count"}[status]] += 1
                counts["rejected_count"] += parse_stats["rejected_count"]
                db.execute("""UPDATE sources SET status='ok',last_attempt_at=?,last_success_at=?,
                    last_error=NULL,item_count=?,rejected_count=?,window_truncated_count=?,cooldown_until=NULL,latest_response_hash=?,latest_snapshot=? WHERE id=?""",
                    (attempted, attempted, len(articles), parse_stats["rejected_count"], parse_stats["window_truncated_count"], response_hash, snapshot, source["id"]))
            source_results.append({"id": source["id"], "status": "ok", "item_count": len(articles), **parse_stats})
        except Exception as exc:
            counts["error_count"] += 1
            # Access denial is terminal for this refresh; wait a day before any new attempt.
            cooldown = None
            if isinstance(exc, urllib.error.HTTPError) and exc.code in (403, 429):
                cooldown = (datetime.now(UTC) + timedelta(hours=24)).isoformat(timespec="seconds").replace("+00:00", "Z")
            error = (type(exc).__name__ + ": " + str(exc))[:600]
            with storage.connect(db_path) as db:
                db.execute("""UPDATE sources SET status='error',last_attempt_at=?,last_error=?,cooldown_until=? WHERE id=?""",
                           (attempted, error, cooldown, source["id"]))
            source_results.append({"id": source["id"], "status": "error", "error": error})
        if index < len(sources) - 1:
            sleep(0.65)
    finished = utc_now()
    with storage.connect(db_path) as db:
        db.execute("""UPDATE refreshes SET finished_at=?,new_count=?,changed_count=?,duplicate_count=?,error_count=?,skipped_count=?,rejected_count=? WHERE id=?""",
                   (finished, counts["new_count"], counts["changed_count"], counts["duplicate_count"], counts["error_count"], counts["skipped_count"], counts["rejected_count"], run_id))
    return {"id": run_id, "started_at": started, "finished_at": finished, **counts, "sources": source_results}
