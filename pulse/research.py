"""Local manual leads and reviewed research; source URLs are stored, never fetched."""
from datetime import datetime, timezone
import hashlib
import json
import re
import sqlite3
from urllib.parse import urlsplit, urlunsplit


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def initialize(db_path):
    with sqlite3.connect(str(db_path), timeout=20) as db:
        db.execute("CREATE TABLE IF NOT EXISTS manual_leads (id TEXT PRIMARY KEY, url TEXT UNIQUE NOT NULL, note TEXT NOT NULL, created_at TEXT NOT NULL, status TEXT NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS research_records (section TEXT NOT NULL, id TEXT NOT NULL, payload TEXT NOT NULL, updated_at TEXT NOT NULL, PRIMARY KEY(section,id))")
        db.execute("CREATE TABLE IF NOT EXISTS research_versions (id INTEGER PRIMARY KEY, section TEXT NOT NULL, record_id TEXT NOT NULL, payload TEXT NOT NULL, imported_at TEXT NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS article_reviews (article_id TEXT PRIMARY KEY, review_status TEXT NOT NULL, reviewed_at TEXT NOT NULL)")
        if "reviewed_hash" not in {row[1] for row in db.execute("PRAGMA table_info(article_reviews)")}:
            db.execute("ALTER TABLE article_reviews ADD COLUMN reviewed_hash TEXT")


def url(value, x_only=False):
    if not isinstance(value, str) or len(value) > 2048 or any(ord(c) < 32 for c in value):
        raise ValueError("A valid HTTPS source URL is required")
    try:
        p = urlsplit(value.strip())
        if p.scheme != "https" or not p.hostname or p.username or p.password or p.port not in (None, 443):
            raise ValueError()
    except ValueError:
        raise ValueError("Use a public HTTPS URL without credentials or custom ports")
    host = p.hostname.lower()
    if host in ("localhost", "127.0.0.1", "::1") or host.endswith(".local"):
        raise ValueError("Use a public source URL")
    if x_only:
        if host not in ("x.com", "www.x.com", "twitter.com", "www.twitter.com", "mobile.twitter.com") or not re.fullmatch(r"/[A-Za-z0-9_]{1,30}/status/[0-9]+/?", p.path):
            raise ValueError("Paste an HTTPS X or Twitter post URL, including /status/ and the post ID")
        return urlunsplit(("https", "x.com", p.path.rstrip("/"), "", ""))
    return urlunsplit(("https", host, p.path or "/", p.query, ""))


def add_lead(db_path, link, note=""):
    link = url(link, x_only=True)
    if not isinstance(note, str) or len(note) > 2000:
        raise ValueError("Lead notes must be text, up to 2,000 characters")
    initialize(db_path)
    lead = {"id": hashlib.sha256(link.encode()).hexdigest()[:20], "url": link, "note": note.strip(), "created_at": now_iso(), "status": "unverified"}
    with sqlite3.connect(str(db_path), timeout=20) as db:
        cur = db.execute("INSERT OR IGNORE INTO manual_leads VALUES (:id,:url,:note,:created_at,:status)", lead)
        duplicate = cur.rowcount == 0
        if duplicate:
            db.row_factory = sqlite3.Row
            lead = dict(db.execute("SELECT * FROM manual_leads WHERE url=?", (link,)).fetchone())
    return {**lead, "duplicate": duplicate}


def required(record, fields):
    for field in fields:
        if field not in record or record[field] is None or record[field] == "":
            raise ValueError("Missing required field: " + field)


def date(value, field):
    if not isinstance(value, str):
        raise ValueError(field + " must be an ISO date")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        parsed = parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except ValueError:
        raise ValueError(field + " must be an ISO date")
    if parsed > datetime.now(timezone.utc):
        raise ValueError(field + " cannot be in the future")
    return value


def validate(section, raw):
    if not isinstance(raw, dict):
        raise ValueError("Each research record must be an object")
    record = dict(raw)
    required(record, ("id",))
    if not isinstance(record["id"], str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", record["id"]):
        raise ValueError("Record id must contain 1–100 letters, numbers, hyphens or underscores")
    if len(json.dumps(record)) > 50000:
        raise ValueError("Research record too large")
    if section == "notes":
        required(record, ("title", "observation", "implication", "as_of", "sources", "uncertainty"))
        date(record["as_of"], "as_of")
        if not isinstance(record["sources"], list) or not record["sources"]:
            raise ValueError("A curated note needs dated sources")
        for source in record["sources"]:
            required(source, ("url", "title", "date"))
            source["url"] = url(source["url"])
            date(source["date"], "source date")
    else:
        required(record, ("source_url", "source_date", "as_of"))
        record["source_url"] = url(record["source_url"])
        date(record["source_date"], "source_date")
        date(record["as_of"], "as_of")
        if section == "ledger":
            required(record, ("from_entity", "to_entity", "instrument", "status", "note"))
            allowed = ("equity", "customer_contract", "cloud_credits", "debt", "guarantee", "capacity", "investment", "other")
            if record["instrument"] not in allowed:
                raise ValueError("Unknown financing instrument; use " + ", ".join(allowed))
            # No aggregation: face values, contingencies and overlapping commitments are not additive.
            record.setdefault("overlap_group", "unassessed")
        elif section == "earnings":
            required(record, ("company", "period", "metric", "unit"))
            if all(record.get(k) is None for k in ("reported", "guidance", "consensus")):
                raise ValueError("An earnings record needs a reported, guidance or consensus value")
            if record.get("guidance") is not None:
                required(record, ("guidance_period",))
            if record.get("consensus") is not None:
                required(record, ("consensus_source_url", "consensus_as_of", "consensus_period"))
                record["consensus_source_url"] = url(record["consensus_source_url"])
                date(record["consensus_as_of"], "consensus_as_of")
    return record


def import_records(db_path, payload):
    if not isinstance(payload, dict) or set(payload) - {"ledger", "earnings", "notes"}:
        raise ValueError("Expected object with only ledger, earnings and/or notes arrays")
    checked = []
    for section, rows in payload.items():
        if not isinstance(rows, list):
            raise ValueError(section + " must be an array")
        for row in rows:
            checked.append((section, validate(section, row)))
    initialize(db_path)
    changed = 0
    with sqlite3.connect(str(db_path), timeout=20) as db:
        for section, record in checked:
            encoded = json.dumps(record, sort_keys=True, ensure_ascii=False)
            old = db.execute("SELECT payload FROM research_records WHERE section=? AND id=?", (section, record["id"])).fetchone()
            if old and old[0] == encoded:
                continue
            stamp = now_iso()
            db.execute("INSERT INTO research_versions(section,record_id,payload,imported_at) VALUES (?,?,?,?)", (section, record["id"], encoded, stamp))
            db.execute("INSERT OR REPLACE INTO research_records VALUES (?,?,?,?)", (section, record["id"], encoded, stamp))
            changed += 1
    return {"validated": len(checked), "changed": changed}


def read(db_path):
    initialize(db_path)
    result = {"leads": [], "ledger": [], "earnings": [], "notes": [], "reviews": {}}
    with sqlite3.connect(str(db_path), timeout=20) as db:
        db.row_factory = sqlite3.Row
        result["leads"] = [dict(r) for r in db.execute("SELECT * FROM manual_leads ORDER BY created_at DESC")]
        result["reviews"] = {r["article_id"]: {"review_status": r["review_status"], "reviewed_at": r["reviewed_at"], "reviewed_hash": r["reviewed_hash"]} for r in db.execute("SELECT * FROM article_reviews")}
        for row in db.execute("SELECT section,payload,updated_at FROM research_records ORDER BY updated_at DESC"):
            result[row["section"]].append({**json.loads(row["payload"]), "imported_at": row["updated_at"]})
    return result


def review_article(db_path, article_id, status):
    result = review_articles(db_path, [article_id], status)
    return {**result, "article_id": article_id}


def review_articles(db_path, article_ids, status):
    if (not isinstance(article_ids, list) or not 1 <= len(article_ids) <= 100
            or any(not isinstance(a, str) or not a for a in article_ids)
            or status not in ("unreviewed", "reviewed", "dismissed")):
        raise ValueError("Choose unreviewed, reviewed or dismissed for a stored article")
    article_ids = list(dict.fromkeys(article_ids))
    initialize(db_path)
    stamp = now_iso()
    with sqlite3.connect(str(db_path), timeout=20) as db:
        marks = ",".join("?" for _ in article_ids)
        rows = db.execute("SELECT id,content_hash FROM articles WHERE id IN (" + marks + ")", article_ids).fetchall()
        if len(rows) != len(article_ids):
            raise ValueError("Article is not in this local evidence store")
        db.executemany("INSERT OR REPLACE INTO article_reviews (article_id,review_status,reviewed_at,reviewed_hash) VALUES (?,?,?,?)",
                       [(article_id, status, stamp, content_hash) for article_id, content_hash in rows])
    return {"article_ids": article_ids, "count": len(article_ids), "review_status": status, "reviewed_at": stamp,
            "note": "Read status is local triage, not independent factual verification."}
