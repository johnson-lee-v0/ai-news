"""Local durable evidence store. Every write is confined to the supplied database."""
import json
import sqlite3
from pathlib import Path


def connect(db_path):
    connection = sqlite3.connect(str(db_path), timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize(db_path):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS sources (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, url TEXT NOT NULL,
            kind TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'never',
            last_attempt_at TEXT, last_success_at TEXT, last_error TEXT,
            item_count INTEGER NOT NULL DEFAULT 0, cooldown_until TEXT,
            latest_response_hash TEXT, latest_snapshot TEXT
        );
        CREATE TABLE IF NOT EXISTS articles (
            id TEXT PRIMARY KEY, title TEXT NOT NULL, url TEXT NOT NULL UNIQUE,
            published_at TEXT, date_precision TEXT NOT NULL,
            observed_at TEXT NOT NULL, first_seen_at TEXT NOT NULL,
            source_id TEXT NOT NULL REFERENCES sources(id), kind TEXT NOT NULL,
            summary TEXT NOT NULL, entities TEXT NOT NULL, tags TEXT NOT NULL,
            content_hash TEXT NOT NULL, source_date_raw TEXT,
            filing_form TEXT, report_date TEXT, accession_number TEXT
        );
        CREATE INDEX IF NOT EXISTS articles_hash ON articles(content_hash);
        CREATE INDEX IF NOT EXISTS articles_date ON articles(published_at);
        CREATE TABLE IF NOT EXISTS article_provenance (
            article_id TEXT NOT NULL REFERENCES articles(id),
            source_id TEXT NOT NULL REFERENCES sources(id),
            original_url TEXT NOT NULL, first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL, response_hash TEXT NOT NULL,
            PRIMARY KEY(article_id, source_id, original_url)
        );
        CREATE TABLE IF NOT EXISTS article_versions (
            article_id TEXT NOT NULL REFERENCES articles(id),
            content_hash TEXT NOT NULL, observed_at TEXT NOT NULL,
            record_json TEXT NOT NULL,
            PRIMARY KEY(article_id,content_hash)
        );
        CREATE TABLE IF NOT EXISTS refreshes (
            id INTEGER PRIMARY KEY AUTOINCREMENT, started_at TEXT NOT NULL,
            finished_at TEXT, new_count INTEGER NOT NULL DEFAULT 0,
            duplicate_count INTEGER NOT NULL DEFAULT 0,
            error_count INTEGER NOT NULL DEFAULT 0, skipped_count INTEGER NOT NULL DEFAULT 0
        );
        """)
        # Additive migrations preserve articles, curated research and old receipts.
        additions = {
            "sources": {"role": "TEXT NOT NULL DEFAULT 'primary'", "topics": "TEXT NOT NULL DEFAULT '[]'", "entities": "TEXT NOT NULL DEFAULT '[]'",
                        "quality_note": "TEXT NOT NULL DEFAULT ''", "coverage_note": "TEXT NOT NULL DEFAULT ''", "cadence_hint": "TEXT NOT NULL DEFAULT ''",
                        "rejected_count": "INTEGER NOT NULL DEFAULT 0", "window_truncated_count": "INTEGER", "max_items": "INTEGER NOT NULL DEFAULT 40"},
            "articles": {"publisher_name": "TEXT", "publisher_url": "TEXT", "verification_status": "TEXT NOT NULL DEFAULT 'publisher_metadata'", "discovered_via": "TEXT", "revised_at": "TEXT", "date_kind": "TEXT NOT NULL DEFAULT 'source_metadata'"},
            "refreshes": {"changed_count": "INTEGER NOT NULL DEFAULT 0", "rejected_count": "INTEGER NOT NULL DEFAULT 0"},
        }
        for table, columns in additions.items():
            existing = {row["name"] for row in db.execute("PRAGMA table_info(" + table + ")")}
            for column, declaration in columns.items():
                if column not in existing:
                    db.execute("ALTER TABLE " + table + " ADD COLUMN " + column + " " + declaration)
        db.execute("""UPDATE articles SET date_kind=CASE WHEN kind='sec_filing' THEN 'filing_date'
            WHEN source_id IN (SELECT id FROM sources WHERE role='discovery') THEN 'search_feed_date'
            ELSE 'feed_date' END WHERE date_kind='source_metadata'""")


def register_sources(db_path, sources):
    initialize(db_path)
    with connect(db_path) as db:
        for source in sources:
            db.execute("""INSERT INTO sources(id,name,url,kind,role,topics,entities,quality_note,coverage_note,cadence_hint,max_items)
                VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,
                url=excluded.url,kind=excluded.kind,role=excluded.role,topics=excluded.topics,entities=excluded.entities,
                quality_note=excluded.quality_note,coverage_note=excluded.coverage_note,cadence_hint=excluded.cadence_hint,max_items=excluded.max_items""",
                (source["id"], source["name"], source["url"], source["kind"], source.get("role", "primary"),
                 json.dumps(source.get("topics", [])), json.dumps(source.get("entities", [source["entity"]] if source.get("entity") else [])),
                 source.get("quality_note", ""), source.get("coverage_note", ""), source.get("cadence_hint", ""), source.get("max_items", 40)))


def save_article(db, article, response_hash, return_status=False):
    """Deduplicate appearances without mixing text with another source's identity.

    A source may revise its own record. Across sources the selected origin is
    stable unless a more direct role arrives (primary > secondary > discovery).
    This selects feed metadata; it does not establish that a claim is verified.
    Every appearance and distinct content version remains in the evidence store.
    """
    selection = """SELECT a.id,a.url,a.content_hash,a.source_id,s.role AS source_role
        FROM articles a JOIN sources s ON s.id=a.source_id """
    row = db.execute(selection + "WHERE a.url=?", (article["url"],)).fetchone()
    if row is None:
        # A preferred source may have changed the selected URL after an exact
        # content match. Keep recognizing the URLs of earlier appearances.
        row = db.execute(selection + """JOIN article_provenance p ON p.article_id=a.id
            WHERE p.source_id=? AND p.original_url=?""",
            (article["source_id"], article["url"])).fetchone()
    if row is None:
        row = db.execute(selection + "WHERE a.content_hash=?",
                         (article["content_hash"],)).fetchone()
    is_new = row is None
    same_source = not is_new and row["source_id"] == article["source_id"]
    preferred_source = False
    if not is_new and not same_source:
        incoming_source = db.execute("SELECT role FROM sources WHERE id=?",
                                     (article["source_id"],)).fetchone()
        preference = {"primary": 3, "secondary": 2, "discovery": 1}
        preferred_source = (incoming_source is not None and
                            preference.get(incoming_source["role"], 0) >
                            preference.get(row["source_role"], 0))
    changed = (not is_new and (same_source or preferred_source) and
               (row["content_hash"] != article["content_hash"] or preferred_source))
    status = "new" if is_new else "changed" if changed else "duplicate"
    article_id = article["id"] if is_new else row["id"]
    fields = ("id", "title", "url", "published_at", "date_precision", "observed_at",
              "first_seen_at", "source_id", "kind", "summary", "entities", "tags",
              "content_hash", "source_date_raw", "filing_form", "report_date", "accession_number",
              "publisher_name", "publisher_url", "verification_status", "discovered_via", "revised_at", "date_kind")

    def value(field):
        if field in ("entities", "tags"):
            return json.dumps(article.get(field, []))
        default = "publisher_metadata" if field == "verification_status" else "feed_date" if field == "date_kind" else None
        return article.get(field, default)

    if is_new:
        db.execute("INSERT INTO articles (" + ",".join(fields) + ") VALUES (" +
                   ",".join("?" for _ in fields) + ")", [value(field) for field in fields])
    elif changed:
        # Replace the complete origin tuple together, including role-bearing
        # source_id, publisher identity, date semantics and verification status.
        # Stable article ID and earliest discovery time survive promotion.
        mutable_fields = [field for field in fields if field not in ("id", "first_seen_at", "revised_at")]
        db.execute("UPDATE articles SET " + ",".join(field + "=?" for field in mutable_fields) +
                   ",revised_at=? WHERE id=?",
                   [value(field) for field in mutable_fields] + [article["observed_at"], article_id])
    elif same_source:
        db.execute("UPDATE articles SET observed_at=? WHERE id=?",
                   (article["observed_at"], article_id))
    # A lower/equal-role appearance cannot revise the selected record or make
    # its own observation timestamp look like a fresh check of that origin.
    db.execute("""INSERT OR IGNORE INTO article_versions
        (article_id,content_hash,observed_at,record_json) VALUES(?,?,?,?)""",
        (article_id, article["content_hash"], article["observed_at"],
         json.dumps(article, ensure_ascii=False)))
    db.execute("""INSERT INTO article_provenance
        (article_id,source_id,original_url,first_seen_at,last_seen_at,response_hash)
        VALUES(?,?,?,?,?,?) ON CONFLICT(article_id,source_id,original_url)
        DO UPDATE SET last_seen_at=excluded.last_seen_at,response_hash=excluded.response_hash""",
        (article_id, article["source_id"], article["url"], article["first_seen_at"],
         article["observed_at"], response_hash))
    return status if return_status else is_new


def dashboard_data(db_path):
    initialize(db_path)
    with connect(db_path) as db:
        articles = [dict(row) for row in db.execute("""SELECT a.*,s.name AS source_name,s.role AS source_role,s.topics AS source_topics,
            s.entities AS source_entities,s.quality_note AS source_quality
            FROM articles a JOIN sources s ON s.id=a.source_id
            ORDER BY COALESCE(published_at,first_seen_at) DESC LIMIT 500""")]
        total_count = db.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        sources = [dict(row) for row in db.execute("SELECT * FROM sources ORDER BY kind,name")]
        refreshes = [dict(row) for row in db.execute("SELECT * FROM refreshes ORDER BY id DESC LIMIT 30")]
        provenance = {}
        for row in db.execute("""SELECT p.*,s.name AS source_name FROM article_provenance p
            JOIN sources s ON p.source_id=s.id"""):
            provenance.setdefault(row["article_id"], []).append(dict(row))
    for article in articles:
        article["entities"] = json.loads(article["entities"])
        article["tags"] = json.loads(article["tags"])
        article["provenance"] = provenance.get(article["id"], [])
        article["source_topics"] = json.loads(article["source_topics"])
        article["source_entities"] = json.loads(article["source_entities"])
    for source in sources:
        source["topics"] = json.loads(source["topics"])
        source["entities"] = json.loads(source["entities"])
    return {"articles": articles, "sources": sources, "refreshes": refreshes, "total_count": total_count, "displayed_count": len(articles), "article_window_limit": 500}
