"""Synthetic, offline browser-test support. Never imports or copies user data."""
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from pulse import analysis, ingest, research, server, storage  # noqa: E402


SOURCES = [
    {"id": "ui-primary", "name": "Synthetic primary source", "url": "https://example.com/synthetic/primary",
     "kind": "company_ir", "role": "primary", "topics": ["capacity"], "entities": ["Synthetic Compute"]},
    {"id": "ui-reporting", "name": "Synthetic reporting source", "url": "https://example.com/synthetic/reporting",
     "kind": "news_report", "role": "secondary", "topics": ["funding"], "entities": []},
    {"id": "ui-discovery", "name": "Synthetic discovery source", "url": "https://example.com/synthetic/discovery",
     "kind": "discovery_lead", "role": "discovery", "topics": ["earnings"], "entities": []},
]


def test_database(folder):
    """Require the launcher's temporary marker; refuse repository destinations."""
    folder = Path(folder).resolve()
    if (folder / ".ui-smoke-only").read_text() != "synthetic-ui-test":
        raise ValueError("Use only the smoke-test launcher's temporary directory")
    try:
        folder.relative_to(ROOT)
    except ValueError:
        return folder / "pulse.sqlite3"
    raise ValueError("UI fixture databases must be outside the checkout")


def dashboard(db_path):
    storage.register_sources(db_path, SOURCES)
    return analysis.compose({**storage.dashboard_data(db_path), **research.read(db_path),
                             "accounts": [], "x_access": {"status": "not_checked", "automatic": False,
                             "detail": "Synthetic offline test. No X session is connected."}})


def offline_refresh(_db_path):
    raise RuntimeError("Synthetic offline failure; no public endpoint was contacted")


def seed(db_path):
    storage.register_sources(db_path, SOURCES)
    research.initialize(db_path)
    now = datetime.now(timezone.utc)
    stamp = now.isoformat()
    published = (now - timedelta(hours=1)).isoformat()
    rows = [
        (0, "Synthetic Compute AI data center megawatt capacity delay", "capacity-primary", "First synthetic appearance.", ["Synthetic Compute"]),
        (1, "Synthetic Compute AI data center megawatt capacity delay", "capacity-report", "Second synthetic appearance, same headline.", ["Synthetic Compute"]),
        (1, "Synthetic Finance AI funding and debt terms", "funding", "Synthetic funding metadata, not a real transaction.", ["Synthetic Finance"]),
        (2, "Synthetic Models AI financial results and guidance", "earnings", "Synthetic discovery metadata; no real issuer claim.", ["Synthetic Models"]),
    ]
    with storage.connect(db_path) as db:
        for source_index, title, slug, summary, entities in rows:
            source = SOURCES[source_index]
            article = ingest.make_article(source, title, "https://example.com/synthetic/" + slug,
                                          summary, published, stamp)
            article["entities"] = entities
            article["date_kind"] = "search_feed_date" if source["role"] == "discovery" else "feed_date"
            storage.save_article(db, article, "synthetic-response-" + slug)
        db.execute("UPDATE sources SET status='ok',last_attempt_at=?,last_success_at=?,item_count=1", (stamp, stamp))
        db.execute("UPDATE sources SET status='error',last_error=? WHERE id='ui-discovery'",
                   ("Synthetic fetch failure <script>window.testInjection=true</script>",))
        db.execute("INSERT INTO refreshes(started_at,finished_at,new_count,error_count) VALUES(?,?,4,1)",
                   ((now - timedelta(minutes=1)).isoformat(), stamp))


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in ("serve", "seed"):
        raise SystemExit("Usage: ui_fixture.py serve|seed TEMPORARY_TEST_DIRECTORY")
    db_path = test_database(sys.argv[2])
    if sys.argv[1] == "seed":
        seed(db_path)
        return
    storage.initialize(db_path)
    research.initialize(db_path)
    # Test-process overrides keep both API refresh and dashboard entirely offline.
    server.dashboard = dashboard
    server.refresh = offline_refresh
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(db_path))
    print("http://127.0.0.1:%s" % httpd.server_address[1], flush=True)
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
