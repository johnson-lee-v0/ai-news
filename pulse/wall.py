"""Public-source personal wall. Metadata collection is not GPT analysis.

The local store and the explicitly requested public projection are separate from
the market research database and brief. No credentials, social scraping or trades.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import hashlib
import ipaddress
import json
import fcntl
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from .ingest import parse_date, plain_text

UTC = timezone.utc
MAX_BYTES = 3_000_000
TIMEOUT = 15
MAX_FEED_ITEMS = 24
MAX_PUBLIC_ITEMS_PER_SOURCE = 16
MAX_CHANNEL_ITEMS = 8
YOUTUBE_CHANNEL_IDS = {"tevis-investing": "UChvd7RCRJS50RWlwbfcwr3A", "sixers-highlights": "UC5qJUyng_ezl0TVjVJFqtfQ", "knicks-highlights": "UC0hb8f0OXHEzDrJDUq-YVVw"}
MEDIA_HOSTS = ("traffic.megaphone.fm", "dcs-cached.megaphone.fm")
TOP_FIELDS = {"version", "updated_at", "source_status", "items", "coverage", "model_status"}
SOURCE_FIELDS = {"id", "name", "section", "kind", "status", "home_url", "feed_url", "last_attempt_at", "last_success_at", "item_count", "note", "topics", "cooldown_until"}
ITEM_FIELDS = {"id", "section", "source_id", "title", "url", "published_at", "first_seen_at", "updated_at", "format", "topics", "summary", "media_url", "duration", "analysis", "content_hash", "provenance_hash"}
ANALYSIS_FIELDS = {"text", "basis", "reviewed_at", "source_urls"}
REVIEW_FIELDS = {"key_takeaway", "worth_reading", "rationale", "scope", "confidence", "content_hash"}
EVIDENCE_FIELDS = {"url", "published_at", "retrieved_at", "content_hash", "scope"}
REVIEW_SCOPES = {"full_text", "excerpt", "metadata", "unavailable"}
SOURCES = [
    {"id": "f1-official", "name": "Formula 1", "section": "sports", "kind": "rss", "home_url": "https://www.formula1.com/en/latest", "feed_url": "https://www.formula1.com/en/latest/all.xml", "topics": ["F1"], "note": "Official F1 feed. Some entries have no publication date; fetch time is not an event date."},
    {"id": "nba-communications", "name": "NBA Communications", "section": "sports", "kind": "rss", "home_url": "https://pr.nba.com/", "feed_url": "https://pr.nba.com/feed/", "topics": ["NBA"], "note": "League announcements, including business and WNBA coverage. This is not comprehensive game or breaking-news coverage."},
    {"id": "wall-street-skinny", "name": "The Wall Street Skinny", "section": "markets", "kind": "podcast_rss", "home_url": "https://thewallstreetskinny.com/podcast/", "feed_url": "https://feeds.megaphone.fm/TTNSE2412391117", "topics": ["Markets", "Finance education"], "note": "Publisher podcast metadata, not a transcript or independently verified analysis. Episodes without a webpage link open the podcast homepage."},
    {"id": "unusual-whales-blog", "name": "Unusual Whales · public blog", "section": "markets", "kind": "rss", "home_url": "https://unusualwhales.com/", "feed_url": "https://unusual-whales.ghost.io/rss/", "topics": ["Markets"], "note": "Public blog linked by Unusual Whales. Finance and AI title keywords filter broad news; relevant posts may be missed. Headlines are publisher claims, not verified conclusions. This is not its X feed."},
    {"id": "unusual-whales-podcast", "name": "Unusual Whales · podcast", "section": "markets", "kind": "podcast_rss", "home_url": "https://rss.com/podcasts/unusualwhales/", "feed_url": "https://media.rss.com/unusualwhales/feed.xml", "topics": ["Markets", "Podcast"], "note": "Public podcast feed. Source dates may be old; no transcript is collected. Audio opens externally when its host is outside the verified embedded-player allowlist."},
    {"id": "polymarket-news", "name": "Polymarket · news", "section": "markets", "kind": "rss", "home_url": "https://news.polymarket.com/", "feed_url": "https://news.polymarket.com/feed", "topics": ["Prediction markets"], "note": "Newsletter news and commentary. Cards use its descriptive subtitle instead of a teaser headline when available. Publisher forecasts are attributed claims, not verified probabilities or live odds."},
    {"id": "tevis-investing", "name": "Tevis · Fundamentals of Investing", "section": "markets", "kind": "public_youtube_channel", "home_url": "https://www.youtube.com/@Funofinvesting", "feed_url": "https://www.youtube.com/@Funofinvesting/videos", "topics": ["Markets", "Company analysis"], "note": "Tevis Shkodra's official site identifies this channel. Public Videos-page metadata, at most eight videos per refresh; RSS returned 404. No transcript is collected, and relative dates remain unknown unless separately verified."},
    {"id": "sixers-highlights", "name": "Philadelphia 76ers · highlights", "section": "sports", "kind": "public_youtube_channel", "home_url": "https://www.youtube.com/@sixers", "feed_url": "https://www.youtube.com/@sixers/videos", "topics": ["NBA", "Sixers", "Highlights"], "note": "Official team Videos-page metadata. Up to eight highlight/game-recap titles per refresh; not every game or the full channel. Dates and video content require separate review; RSS returned 404."},
    {"id": "knicks-highlights", "name": "New York Knicks · highlights", "section": "sports", "kind": "public_youtube_channel", "home_url": "https://www.youtube.com/@NYKnicks", "feed_url": "https://www.youtube.com/@NYKnicks/videos", "topics": ["NBA", "Knicks", "Highlights"], "note": "Official team Videos-page metadata. Up to eight highlight/game-recap titles per refresh; not every game or the full channel. Dates and video content require separate review; RSS returned 404."},
]
GAPS = [
    {"id": "kobeissi-letter", "name": "The Kobeissi Letter", "section": "markets", "kind": "requested", "home_url": "https://www.thekobeissiletter.com/about/feed", "feed_url": None, "topics": ["Markets", "Macro"], "note": "Official site confirms @KobeissiLetter. Selected public posts can be reviewed through the existing external research task's supported browser access. Direct HTTP access is restricted; no automatic timeline API, complete X coverage or paid newsletter is connected."},
    {"id": "shams", "name": "Shams Charania", "section": "sports", "kind": "requested", "home_url": "https://x.com/ShamsCharania", "feed_url": None, "topics": ["NBA"], "note": "Identity corroborated by ESPN's biography. No automatic post feed is connected; no complete breaking-news coverage is implied."},
    {"id": "nba-central", "name": "NBA Central", "section": "sports", "kind": "requested", "home_url": "https://x.com/TheDunkCentral", "feed_url": None, "topics": ["NBA"], "note": "Account identity corroborated by its Instagram profile. It is unaffiliated with the NBA. The existing external research task can review selected public posts through supported browser access; no automatic timeline API or full NBA Central coverage is connected."},
    {"id": "unusual-whales", "name": "Unusual Whales · X and live alerts", "section": "markets", "kind": "requested", "home_url": "https://unusualwhales.com/", "feed_url": None, "topics": ["Markets"], "note": "X posts and live alerts are not connected. Separate public blog and podcast sources are listed independently."},
    {"id": "polymarket", "name": "Polymarket · live odds", "section": "markets", "kind": "requested", "home_url": "https://polymarket.com/", "feed_url": None, "topics": ["Prediction markets"], "note": "Live odds are not collected. The separate news feed is publisher commentary; market prices are not independently verified probabilities."},
    {"id": "unresolved-handle", "name": "kobawaschilettwr — identity unverified", "section": "markets", "kind": "requested", "home_url": None, "feed_url": None, "topics": ["Markets"], "note": "The supplied handle has not been identified. No account or source has been guessed."},
]
COVERAGE = [
    "Selected public feeds, not complete NBA, F1 or market coverage. A successful fetch is not a factual verification.",
    "Dates come from publisher metadata. Missing dates stay unknown; fetched time is shown separately.",
    "X and Instagram feeds, engagement counts, full podcast transcripts and live trading data are not connected.",
    "Existing market research is reviewed separately. Feed items have no GPT analysis unless a dated analysis is explicitly attached.",
]


def now_iso():
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def item_content_hash(item):
    """Bind a review to public item metadata, not a mutable fetch timestamp.

    This is not a claim to have hashed or reviewed the original article. The
    separate evidence records describe exactly what the external reviewer read.
    """
    fields = ("source_id", "section", "title", "url", "published_at", "format",
              "topics", "summary", "media_url", "duration")
    value = {key: item.get(key) for key in fields}
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def valid_hash(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def date_value(value):
    if not isinstance(value, str):
        raise ValueError("Date must be an ISO timestamp")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Timestamp requires a timezone")
    return result.astimezone(UTC)


def public_url(value):
    if not isinstance(value, str) or len(value) > 2000 or re.search(r"[\\\s\x00-\x1f]", value):
        raise ValueError("A plain public HTTPS URL is required")
    p = urllib.parse.urlsplit(value)
    host = p.hostname or ""
    if p.scheme != "https" or not host or p.username or p.password or p.port not in (None, 443):
        raise ValueError("A plain public HTTPS URL is required")
    if host in ("localhost", "localhost.localdomain") or host.endswith((".localhost", ".local", ".internal")) or "." not in host:
        raise ValueError("Local addresses are forbidden")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None:
        raise ValueError("Literal IP addresses are not permitted public sources")
    if any(re.search(r"token|secret|password|api.?key|credential|authorization", key, re.I) for key, _ in urllib.parse.parse_qsl(p.query)):
        raise ValueError("Credential-like URL parameters are forbidden")
    query = [(k, v) for k, v in urllib.parse.parse_qsl(p.query, keep_blank_values=True) if not k.lower().startswith("utm_") and k.lower() not in ("fbclid", "gclid")]
    return urllib.parse.urlunsplit(("https", host.lower(), p.path or "/", urllib.parse.urlencode(query), ""))


def _safe(value):
    if isinstance(value, dict):
        for child in value.values():
            _safe(child)
    elif isinstance(value, list):
        for child in value:
            _safe(child)
    elif isinstance(value, str):
        if len(value) > 2500 or re.search(r"/Users/|/home/|[A-Z]:\\Users\\|-----BEGIN .*PRIVATE KEY-----|\b(?:gh[pousr]_[A-Za-z0-9]{25,}|github_pat_[A-Za-z0-9_]{25,}|AKIA[A-Z0-9]{16}|sk-[A-Za-z0-9_-]{25,})\b", value):
            raise ValueError("Private content or oversized text is forbidden")


def empty_payload():
    return {"version": 1, "updated_at": None,
            "source_status": [{**s, "status": "pending", "last_attempt_at": None, "last_success_at": None, "item_count": 0} for s in SOURCES] +
                             [{**s, "status": "unresolved" if s["id"] == "unresolved-handle" else "not_connected", "last_attempt_at": None, "last_success_at": None, "item_count": 0} for s in GAPS],
            "items": [], "coverage": list(COVERAGE),
            "model_status": {"mode": "external_agent", "note": "The app does not call GPT. Existing Codex research can add dated, source-backed analysis; a ChatGPT subscription has not been connected as an app API."}}


def validate_public(payload):
    """Strict input-only validation, including publication boundaries."""
    if not isinstance(payload, dict) or set(payload) != TOP_FIELDS or payload.get("version") != 1:
        raise ValueError("Personal wall must use the version 1 allowlisted schema")
    _safe(payload)
    for field in ("items", "source_status", "coverage"):
        if not isinstance(payload[field], list):
            raise ValueError("Wall collections must be lists")
    if len(payload["items"]) > 5000 or len(payload["source_status"]) > 30 or len(payload["coverage"]) > 20:
        raise ValueError("Wall collection exceeds its bounded capacity")
    future_limit = datetime.now(UTC) + timedelta(minutes=5)
    def valid_date(value, day_only=False):
        parsed = datetime.fromisoformat(value).replace(tzinfo=UTC) if day_only and isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) else date_value(value)
        if parsed > future_limit:
            raise ValueError("Publication or review timestamp cannot be in the future")
    if payload["updated_at"] is not None:
        valid_date(payload["updated_at"])
    model = payload["model_status"]
    if not isinstance(model, dict) or set(model) != {"mode", "note"} or model["mode"] != "external_agent":
        raise ValueError("No automatic model integration is configured")
    ids = set()
    for source in payload["source_status"]:
        required = SOURCE_FIELDS - {"cooldown_until"}
        if not isinstance(source, dict) or set(source) - SOURCE_FIELDS or not required <= set(source):
            raise ValueError("Unexpected or missing wall source fields")
        if not isinstance(source["id"], str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,100}", source["id"]) or source["id"] in ids or source["section"] not in ("sports", "markets") or source["status"] not in ("pending", "ok", "empty", "error", "cooldown", "not_connected", "unresolved", "selected_posts"):
            raise ValueError("Invalid source identity or status")
        ids.add(source["id"])
        if not isinstance(source["topics"], list) or not all(isinstance(t, str) for t in source["topics"]) or not isinstance(source["item_count"], int) or source["item_count"] < 0:
            raise ValueError("Invalid source topics or item count")
        for field in ("home_url", "feed_url"):
            if source[field] is not None:
                public_url(source[field])
        for field in ("last_attempt_at", "last_success_at", "cooldown_until"):
            if source.get(field) is not None:
                date_value(source[field]) if field == "cooldown_until" else valid_date(source[field])
    item_ids = set()
    required = ITEM_FIELDS - {"media_url", "duration", "content_hash", "provenance_hash"}
    for item in payload["items"]:
        if not isinstance(item, dict) or set(item) - ITEM_FIELDS or not required <= set(item):
            raise ValueError("Unexpected or missing wall item fields")
        if not isinstance(item["id"], str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,100}", item["id"]) or item["id"] in item_ids or item["source_id"] not in ids or item["section"] not in ("sports", "markets") or item["format"] not in ("article", "podcast", "video", "instagram"):
            raise ValueError("Invalid wall item identity or format")
        if item["section"] != next(s["section"] for s in payload["source_status"] if s["id"] == item["source_id"]):
            raise ValueError("Item section does not match its source")
        item_ids.add(item["id"])
        if not isinstance(item["title"], str) or not item["title"].strip() or len(item["title"]) > 500 or not isinstance(item["summary"], str) or len(item["summary"]) > 350:
            raise ValueError("Wall items require short titles and summaries")
        if not isinstance(item["topics"], list) or not all(isinstance(t, str) and len(t) <= 80 for t in item["topics"]):
            raise ValueError("Invalid item topics")
        public_url(item["url"])
        if item.get("media_url"):
            public_url(item["media_url"])
            if urllib.parse.urlsplit(item["media_url"]).hostname not in MEDIA_HOSTS:
                raise ValueError("Media host has not been verified for embedding")
        if item.get("duration") is not None and (not isinstance(item["duration"], (int, str)) or len(str(item["duration"])) > 20):
            raise ValueError("Invalid media duration")
        for field in ("published_at", "first_seen_at", "updated_at"):
            if item[field] is not None:
                valid_date(item[field], day_only=field == "published_at")
        for field in ("content_hash", "provenance_hash"):
            if field in item and not valid_hash(item[field]):
                raise ValueError("Item provenance requires a SHA256 hash")
        if "content_hash" in item and item["content_hash"] != item_content_hash(item):
            raise ValueError("Item content hash does not match its current metadata")
        analysis = item["analysis"]
        if analysis is not None:
            if not isinstance(analysis, dict) or set(analysis) - (ANALYSIS_FIELDS | REVIEW_FIELDS | {"evidence"}) or not ANALYSIS_FIELDS <= set(analysis) or not isinstance(analysis["text"], str) or not analysis["text"].strip() or len(analysis["text"]) > 1200:
                raise ValueError("Analysis requires explicit text, basis and dated sources")
            if not isinstance(analysis["basis"], str) or not analysis["basis"].strip() or not isinstance(analysis["source_urls"], list) or not 1 <= len(analysis["source_urls"]) <= 10:
                raise ValueError("Analysis provenance is missing")
            valid_date(analysis["reviewed_at"])
            for url in analysis["source_urls"]:
                public_url(url)
            if set(analysis) & (REVIEW_FIELDS | {"evidence"}):
                if not REVIEW_FIELDS | {"evidence"} <= set(analysis):
                    raise ValueError("Reading judgments require complete review fields and evidence")
                for field, maximum in (("key_takeaway", 350), ("rationale", 500), ("basis", 800)):
                    if not isinstance(analysis[field], str) or not analysis[field].strip() or len(analysis[field]) > maximum:
                        raise ValueError("Review takeaway, rationale and basis must be short and explicit")
                if analysis["worth_reading"] not in {"dig_deeper", "skim", "skip", "unavailable"} or analysis["scope"] not in REVIEW_SCOPES or analysis["confidence"] not in {"low", "medium", "high"}:
                    raise ValueError("Invalid reading judgment, access scope or confidence")
                if not valid_hash(analysis["content_hash"]) or analysis["content_hash"] != item_content_hash(item):
                    raise ValueError("Review does not match the current item content")
                if analysis["scope"] in {"metadata", "unavailable"} and analysis["confidence"] == "high":
                    raise ValueError("Limited source access cannot support a high-confidence judgment")
                if analysis["scope"] == "unavailable" and (analysis["worth_reading"] != "unavailable" or analysis["confidence"] != "low"):
                    raise ValueError("Unavailable content cannot support a reading judgment")
                evidence = analysis["evidence"]
                if not isinstance(evidence, list) or not 1 <= len(evidence) <= 10:
                    raise ValueError("Review requires one to ten source evidence records")
                for record in evidence:
                    if not isinstance(record, dict) or set(record) != EVIDENCE_FIELDS or record["scope"] not in REVIEW_SCOPES:
                        raise ValueError("Invalid review evidence fields")
                    public_url(record["url"])
                    valid_date(record["retrieved_at"])
                    if date_value(record["retrieved_at"]) > date_value(analysis["reviewed_at"]):
                        raise ValueError("Evidence retrieval cannot be later than its review")
                    if record["published_at"] is not None:
                        valid_date(record["published_at"], day_only=True)
                        published = record["published_at"]
                        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", published):
                            published = published + "T00:00:00Z"
                        if date_value(published) > date_value(record["retrieved_at"]):
                            raise ValueError("Evidence publication cannot be later than retrieval")
                    if record["scope"] == "unavailable":
                        if record["content_hash"] is not None:
                            raise ValueError("Unavailable content must not claim a content hash")
                    elif not valid_hash(record["content_hash"]):
                        raise ValueError("Accessed evidence requires a SHA256 content hash")
                if not set(analysis["source_urls"]) <= {record["url"] for record in evidence}:
                    raise ValueError("Every analysis source must have an evidence receipt")
                # An uncited supplemental receipt cannot upgrade the access
                # claimed for the sources the reader is actually given.
                scopes = {record["scope"] for record in evidence if record["url"] in analysis["source_urls"]}
                supported = {"full_text": {"full_text"}, "excerpt": {"full_text", "excerpt"}, "metadata": {"full_text", "excerpt", "metadata"}, "unavailable": {"unavailable"}}
                if not scopes & supported[analysis["scope"]] or (analysis["scope"] == "unavailable" and scopes != {"unavailable"}):
                    raise ValueError("Review scope exceeds its recorded source access")
    return deepcopy(payload)


def public_projection(payload):
    value = validate_public(payload)
    counts = {}
    selected = []
    # Reviews and explicitly imported content are retained; unreviewed feed
    # metadata has a bounded public window. The local store retains older items.
    for item in sorted(value["items"], key=lambda i: (i["published_at"] or "", i["updated_at"] or ""), reverse=True):
        source = item["source_id"]
        if item["analysis"] is not None or item["format"] in ("instagram", "video") or counts.get(source, 0) < MAX_PUBLIC_ITEMS_PER_SOURCE:
            selected.append(item)
            counts[source] = counts.get(source, 0) + 1
    value["items"] = selected
    return validate_public(value)


def load_file(path, strict=False):
    path = Path(path)
    if not path.exists():
        return empty_payload()
    try:
        if path.is_symlink() or path.stat().st_size > 10_000_000:
            raise ValueError("Unexpected wall store type or size")
        return validate_public(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError, KeyError):
        if strict:
            raise ValueError("Existing wall store is invalid; it has not been overwritten")
        value = empty_payload()
        value["coverage"].insert(0, "The local personal-wall store could not be read. Existing files have not been changed.")
        return value


read_file = load_file


def content_security_policy(static=False):
    media = " ".join("https://" + host for host in MEDIA_HOSTS)
    return ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; "
            "media-src 'self'" + (" " + media if media else "") + "; frame-src https://www.instagram.com https://www.youtube-nocookie.com; "
            "object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action " + ("'none'" if static else "'self'"))


class _FeedRedirects(urllib.request.HTTPRedirectHandler):
    def __init__(self, host):
        self.host = host

    def redirect_request(self, request, fp, code, msg, headers, newurl):
        target = public_url(newurl)
        if urllib.parse.urlsplit(target).hostname != self.host:
            raise ValueError("Feed redirected to an unapproved host")
        return super().redirect_request(request, fp, code, msg, headers, target)


def fetch_feed(source):
    url = public_url(source["feed_url"])
    accept = "text/html" if source["kind"] == "public_youtube_channel" else "application/rss+xml,application/atom+xml,application/xml,text/xml;q=0.9"
    request = urllib.request.Request(url, headers={"User-Agent": "AIStockPulse/0.3 personal public-feed reader", "Accept": accept, "Accept-Encoding": "identity", "Accept-Language": "en-US,en;q=0.9"})
    opener = urllib.request.build_opener(_FeedRedirects(urllib.parse.urlsplit(url).hostname))
    with opener.open(request, timeout=TIMEOUT) as response:
        if response.status != 200:
            raise ValueError("Unexpected feed response status")
        result = response.read(MAX_BYTES + 1)
        if len(result) > MAX_BYTES:
            raise ValueError("Feed exceeded the size limit")
        return result


def _youtube_url(value):
    url = urllib.parse.urlsplit(public_url(value))
    video = urllib.parse.parse_qs(url.query).get("v", [""])[0]
    if url.hostname not in ("www.youtube.com", "youtube.com") or url.path != "/watch" or not re.fullmatch(r"[A-Za-z0-9_-]{11}", video):
        raise ValueError("A canonical public YouTube video is required")
    return "https://www.youtube.com/watch?v=" + video


def _parse_youtube_channel(payload, source, observed_at):
    """Use only the ordinary public page's displayed Videos-tab metadata.

    No continuation requests, internal API calls, cookies or session data are
    used. Unrecognized layouts fail closed and retain the prior collected rows.
    """
    if len(payload) > MAX_BYTES:
        raise ValueError("Public channel page exceeded the size limit")
    text = payload.decode("utf-8")
    marker = re.search(r"(?:var\s+)?ytInitialData\s*=\s*", text)
    if not marker:
        raise ValueError("Public channel video metadata unavailable")
    data = json.JSONDecoder().raw_decode(text[marker.end():])[0]
    identity = data.get("metadata", {}).get("channelMetadataRenderer", {}).get("externalId")
    if not YOUTUBE_CHANNEL_IDS.get(source["id"]) or identity != YOUTUBE_CHANNEL_IDS[source["id"]]:
        raise ValueError("Public channel identity did not match the verified source")
    tabs = data.get("contents", {}).get("twoColumnBrowseResultsRenderer", {}).get("tabs", [])
    selected = [t.get("tabRenderer", {}) for t in tabs if t.get("tabRenderer", {}).get("selected")]
    if len(selected) != 1 or selected[0].get("title") != "Videos":
        raise ValueError("Public Videos tab unavailable")
    entries = []
    def walk(value):
        if isinstance(value, dict):
            if "lockupViewModel" in value:
                node = value["lockupViewModel"]
                entries.append((node.get("contentId"), node.get("metadata", {}).get("lockupMetadataViewModel", {}).get("title", {}).get("content", "")))
                return
            if "videoRenderer" in value:
                node = value["videoRenderer"]
                title = node.get("title", {})
                entries.append((node.get("videoId"), title.get("simpleText") or "".join(r.get("text", "") for r in title.get("runs", []))))
                return
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    walk(selected[0].get("content", {}))
    if not entries:
        raise ValueError("No displayed video cards found")
    rows, seen, rejected, filtered = [], set(), 0, 0
    for video, title in entries[:MAX_FEED_ITEMS]:
        if not isinstance(video, str) or not re.fullmatch(r"[A-Za-z0-9_-]{11}", video) or not isinstance(title, str) or not title.strip():
            rejected += 1
            continue
        title = re.sub(r"\s+", " ", title).strip()[:500]
        if source["id"] in ("sixers-highlights", "knicks-highlights") and not re.search(r"\b(highlights?|game recap|defeat(?:s|ed)?|take on|takes on)\b", title, re.I):
            filtered += 1
            continue
        if video in seen:
            continue
        seen.add(video)
        url = "https://www.youtube.com/watch?v=" + video
        row = {"id": "wall-" + hashlib.sha256((source["id"] + "|" + url).encode()).hexdigest()[:24],
               "section": source["section"], "source_id": source["id"], "title": title, "url": url,
               "published_at": None, "first_seen_at": observed_at, "updated_at": observed_at,
               "format": "video", "topics": list(source["topics"]),
               "summary": "Public channel video listing. The review below states what could be accessed; footage is not automatically analyzed.",
               "analysis": None, "provenance_hash": hashlib.sha256(payload).hexdigest()}
        row["content_hash"] = item_content_hash(row)
        rows.append(row)
    if not rows and rejected and not filtered:
        raise ValueError("Public channel video cards were invalid")
    return rows[:MAX_CHANNEL_ITEMS], {"rejected_count": rejected, "filtered_count": filtered,
                                     "window_truncated_count": max(0, len(entries) - MAX_FEED_ITEMS) + max(0, len(rows) - MAX_CHANNEL_ITEMS)}


def parse_feed(payload, source, observed_at):
    if source["kind"] == "public_youtube_channel":
        try:
            return _parse_youtube_channel(payload, source, observed_at)
        except (AttributeError, TypeError, KeyError, IndexError, RecursionError) as exc:
            raise ValueError("Public channel metadata schema changed") from exc
    if len(payload) > MAX_BYTES or re.search(br"<!\s*(DOCTYPE|ENTITY)\b", payload, re.I):
        raise ValueError("Unsupported or oversized XML")
    root = ET.fromstring(payload)
    tag = lambda node: node.tag.rsplit("}", 1)[-1]
    if tag(root) not in ("rss", "feed", "RDF"):
        raise ValueError("Response was not an RSS or Atom feed")
    entries = [node for node in root.iter() if tag(node) in ("item", "entry")]
    result, rejected, filtered, seen = [], 0, 0, set()
    for entry in entries[:MAX_FEED_ITEMS]:
        fields, url, media = {}, "", None
        for child in entry:
            name = tag(child)
            fields[name] = "".join(child.itertext()).strip()
            if name == "link" and child.attrib.get("rel", "alternate") == "alternate":
                url = child.attrib.get("href") or fields[name]
            if name == "enclosure" or (name == "link" and child.attrib.get("rel") == "enclosure"):
                candidate = child.attrib.get("url") or child.attrib.get("href")
                if candidate and child.attrib.get("type", "").startswith(("audio/", "video/")):
                    try:
                        media = public_url(candidate)
                    except ValueError:
                        pass
        try:
            title = plain_text(fields.get("title", ""))[:500]
            if not title:
                raise ValueError("No title")
            if source["id"] == "unusual-whales-blog" and not re.search(r"\b(stock|stocks|market|markets|nasdaq|s&p|bond|bonds|yield|interest|fed|inflation|econom\w*|earning\w*|revenue|profit|invest\w*|crypto\w*|bitcoin|tariff\w*|oil|bank\w*|ai|artificial intelligence|technology|google|nvidia|microsoft|openai|anthropic)\b", title, re.I):
                filtered += 1
                continue
            guid = fields.get("guid") or fields.get("id") or ""
            if not url and source["kind"] == "podcast_rss" and guid:
                url = source["home_url"]
            url = public_url(url)
            if source["kind"] == "youtube_rss":
                url = _youtube_url(url)
            raw_date = fields.get("pubDate") or fields.get("published") or fields.get("date")
            date, precision = parse_date(raw_date, now=date_value(observed_at))
            # Python treats RFC -0000 as a naive timestamp. Preserve the
            # publisher's calendar day without inventing intraday precision.
            if date is None and raw_date and re.search(r"\s-0000$", raw_date):
                try:
                    date = parsedate_to_datetime(raw_date).date().isoformat()
                    precision = "day" if date <= date_value(observed_at).date().isoformat() else "future_unverified"
                except (ValueError, TypeError, OverflowError):
                    pass
            if precision == "future_unverified":
                rejected += 1
                continue
            identity = source["id"] + "|" + (guid if source["kind"] == "podcast_rss" and guid else url)
            item_id = "wall-" + hashlib.sha256(identity.encode()).hexdigest()[:24]
            if item_id in seen:
                continue
            seen.add(item_id)
            row = {"id": item_id, "section": source["section"], "source_id": source["id"], "title": title, "url": url,
                   "published_at": date, "first_seen_at": observed_at, "updated_at": observed_at,
                   "format": "podcast" if source["kind"] == "podcast_rss" else "video" if source["kind"] == "youtube_rss" else "article", "topics": list(source["topics"]),
                   "summary": "", "analysis": None, "provenance_hash": hashlib.sha256(payload).hexdigest()}
            if source["id"] == "polymarket-news":
                # This source's short RSS description is a subtitle, not its
                # content:encoded article body. Never project that raw body.
                subtitle = plain_text(fields.get("description", ""))
                if 4 <= len(subtitle.split()) <= 45 and len(subtitle) <= 300:
                    row["title"] = subtitle
                    row["summary"] = ("Polymarket newsletter: " + title + ". Publisher commentary; forecasts are attributed claims, not verified probabilities.")[:350]
                else:
                    row["summary"] = "Polymarket newsletter commentary. The publisher supplied no descriptive subtitle; open the source for context. Forecasts are not verified probabilities."
            if source["id"] == "nba-communications" and re.search(r"\bWNBA\b", title, re.I):
                row["topics"] = (["NBA"] if re.search(r"\bNBA\b", title, re.I) else []) + ["WNBA"]
            if media:
                # This exact source-derived CDN route was independently checked.
                # Do not persist its signed redirect URL or load tracking wrappers.
                if source["id"] == "wall-street-skinny":
                    audio = re.search(r"(?:https?://)?traffic\.megaphone\.fm/(TTNSE\d+\.mp3)(?:[?&/]|$)", media)
                    if audio:
                        media = "https://traffic.megaphone.fm/" + audio.group(1)
                if urllib.parse.urlsplit(media).hostname in MEDIA_HOSTS:
                    row["media_url"] = media
            if fields.get("duration") and re.fullmatch(r"[\d:]{1,20}", fields["duration"]):
                row["duration"] = fields["duration"]
            row["content_hash"] = item_content_hash(row)
            result.append(row)
        except (ValueError, TypeError):
            rejected += 1
    if entries and not result and not filtered:
        raise ValueError("Feed entries had no usable public titles, dates or links")
    return result, {"rejected_count": rejected, "filtered_count": filtered, "window_truncated_count": max(0, len(entries) - MAX_FEED_ITEMS)}


def _write(path, value):
    path = Path(path)
    if path.is_symlink():
        raise ValueError("Refusing to replace a symlinked wall store")
    path.parent.mkdir(parents=True, exist_ok=True)
    path = path.parent.resolve() / path.name
    temporary = path.with_name(path.name + ".pending")
    if temporary.is_symlink():
        raise ValueError("Unexpected staged wall file")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _refresh_file(path, fetcher=None, now=None):
    """Refresh a separate local store; public projection requires a separate step."""
    value = load_file(path, strict=True)
    fetcher = fetcher or fetch_feed
    stamp = now or now_iso()
    current_time = date_value(stamp)
    rows = {item["id"]: deepcopy(item) for item in value["items"]}
    previous_sources = {s["id"]: s for s in value["source_status"]}
    statuses, receipts = [], []
    counts = {"new_count": 0, "changed_count": 0, "duplicate_count": 0, "error_count": 0, "skipped_count": 0, "rejected_count": 0}
    for source in SOURCES:
        previous = previous_sources.get(source["id"], {})
        status = {**source, "status": "pending", "last_attempt_at": stamp, "last_success_at": previous.get("last_success_at"), "item_count": 0}
        status["item_count"] = sum(i["source_id"] == source["id"] for i in rows.values())
        if previous.get("cooldown_until") and date_value(previous["cooldown_until"]) > current_time:
            status.update(status="cooldown", last_attempt_at=previous.get("last_attempt_at"), cooldown_until=previous["cooldown_until"], note=source["note"] + " A prior access or rate-limit response is cooling down; retained items may be old.")
            counts["skipped_count"] += 1
            statuses.append(status)
            receipts.append({"id": source["id"], "status": "cooldown"})
            continue
        try:
            payload = fetcher(source)
            items, stats = parse_feed(payload, source, stamp)
            counts["rejected_count"] += stats["rejected_count"]
            for item in items:
                old = rows.get(item["id"])
                if old:
                    item["first_seen_at"] = old["first_seen_at"]
                    if item["published_at"] is None and old["published_at"] is not None:
                        item["published_at"] = old["published_at"]
                    if source["kind"] == "podcast_rss" and item["url"] == source["home_url"] and old["url"] != source["home_url"]:
                        item["url"] = old["url"]
                    same_title = re.sub(r"\s+", " ", item["title"]).casefold() == re.sub(r"\s+", " ", old["title"]).casefold()
                    if not item["summary"] and same_title:
                        item["summary"] = old["summary"]
                    item["content_hash"] = item_content_hash(item)
                    same_content = item["content_hash"] == item_content_hash(old)
                    item["analysis"] = old["analysis"] if same_content else None
                    ignored = ("updated_at", "first_seen_at", "analysis", "content_hash", "provenance_hash")
                    material = {k: v for k, v in item.items() if k not in ignored}
                    before = {k: v for k, v in old.items() if k not in ignored}
                    if material == before:
                        item["updated_at"] = old["updated_at"]
                        if old.get("provenance_hash"):
                            item["provenance_hash"] = old["provenance_hash"]
                        counts["duplicate_count"] += 1
                    else:
                        _write(Path(path).parent / "wall-history" / old["id"] / (stamp.replace(":", "-") + ".json"), old)
                        counts["changed_count"] += 1
                else:
                    counts["new_count"] += 1
                rows[item["id"]] = item
            status.update(status="ok" if items else "empty", last_success_at=stamp, item_count=len(items))
            if not items:
                status["note"] += " Latest response was empty; previously stored items are retained."
            receipts.append({"id": source["id"], "status": status["status"], "response_sha256": hashlib.sha256(payload).hexdigest(), "item_count": len(items), **stats})
        except (OSError, ValueError, ET.ParseError, urllib.error.URLError) as exc:
            counts["error_count"] += 1
            status.update(status="error", note=source["note"] + " Latest fetch failed; previously stored items and last-success date are retained.")
            code = getattr(exc, "code", None)
            if code in (403, 429):
                status["cooldown_until"] = (current_time + timedelta(hours=24)).isoformat(timespec="seconds").replace("+00:00", "Z")
            receipts.append({"id": source["id"], "status": "error", "reason": "HTTP " + str(code) if code else "Public feed unavailable or invalid"})
        statuses.append(status)
    configured = {s["id"] for s in SOURCES}
    statuses += [s for s in value["source_status"] if s["id"] not in configured]
    known = {s["id"] for s in statuses}
    statuses += [s for s in empty_payload()["source_status"] if s["id"] not in known]
    value.update(updated_at=stamp, source_status=statuses, items=sorted(rows.values(), key=lambda i: (i["published_at"] or "", i["updated_at"] or ""), reverse=True))
    value = validate_public(value)
    _write(path, value)
    receipt = {"started_at": stamp, "finished_at": now_iso() if now is None else stamp, **counts, "sources": receipts, "stored_items": len(rows), "public_written": False}
    receipt_path = Path(path).parent / "wall-receipts" / (stamp.replace(":", "-") + ".json")
    _write(receipt_path, receipt)
    return receipt


def refresh_file(path, fetcher=None, now=None):
    path = Path(path)
    if path.is_symlink():
        raise ValueError("Refusing to update a symlinked wall store")
    path.parent.mkdir(parents=True, exist_ok=True)
    path = path.parent.resolve() / path.name
    with (path.parent / ".wall.lock").open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("A personal-wall refresh is already running")
        return _refresh_file(path, fetcher=fetcher, now=now)


def write_public(path, payload):
    path = Path(path)
    if path.name != "wall.json" or path.parent.name != "public":
        raise ValueError("Public output must explicitly target public/wall.json")
    value = public_projection(payload)
    _write(path, value)
    return {"items": len(value["items"]), "source_status": len(value["source_status"]), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
