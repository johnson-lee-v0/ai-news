"""Pure oldest-first selection for the public market snapshot, never its archive."""
from copy import deepcopy
from datetime import datetime, timezone
import re
from urllib.parse import urldefrag

MAX_ARTICLES = 49
MAX_SOURCES = 168
URL = re.compile(r'https://[^\s<>"\[\]{}]+')


def _date(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None
    return stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp.astimezone(timezone.utc)


def publication_order(article):
    """Oldest first. Review/fetch timestamps and editorial rank never promote a post."""
    stamp = next((parsed for key in ('published_at', 'event_date', 'event_start')
                  if (parsed := _date(article.get(key))) is not None), None)
    return stamp or datetime.min.replace(tzinfo=timezone.utc), article['id']


def referenced_sources(value, sources):
    """Resolve structured IDs and evidence URLs, including URLs in context text."""
    ids = {source['id'] for source in sources}
    by_url = {}
    for source in sources:
        by_url.setdefault(urldefrag(source['url'])[0], set()).add(source['id'])
    found = set()

    def visit(item, field=None):
        if isinstance(item, dict):
            for key, child in item.items():
                visit(child, key)
        elif isinstance(item, list):
            for child in item:
                visit(child, field)
        elif isinstance(item, str):
            if field in ('source_id', 'source_ids') and item in ids:
                found.add(item)
            # Check literal URL fields first, then prose with sentence punctuation.
            found.update(by_url.get(urldefrag(item)[0], ()))
            for match in URL.findall(item):
                found.update(by_url.get(urldefrag(match.rstrip('.,;:!?)\''))[0], ()))
    visit(value)
    return found


def rotate_snapshot(raw, max_articles=MAX_ARTICLES, max_sources=MAX_SOURCES):
    """Retire only an oldest prefix; preserve records and intentional source rosters.

    Content/review validation belongs to the caller and must run BEFORE selection.
    Source ownership is computed once from the full input. Unowned roster sources,
    global references and financial-record references are keepers, never a purge list.
    """
    if type(max_articles) is not int or max_articles < 1 or type(max_sources) is not int or max_sources < 1:
        raise ValueError('Rotation limits must be positive integers')
    value = deepcopy(raw)
    articles, sources = value['articles'], value['sources']
    if len({a['id'] for a in articles}) != len(articles) or len({s['id'] for s in sources}) != len(sources):
        raise ValueError('Rotation requires unique article and source IDs')
    owners = {source['id']: set() for source in sources}
    references = {}
    for article in articles:
        refs = referenced_sources(article, sources)
        references[article['id']] = refs
        for source_id in refs:
            owners[source_id].add(article['id'])
    global_content = {key: child for key, child in value.items() if key not in ('articles', 'sources')}
    global_refs = referenced_sources(global_content, sources)
    # Source notes can themselves carry a distinct access-route citation.
    source_context = [{key: child for key, child in source.items() if key not in ('id', 'url')}
                      for source in sources]
    global_refs |= referenced_sources(source_context, sources)
    keepers = global_refs | {key for key, article_ids in owners.items() if not article_ids}
    retired = set()
    kept_sources = list(sources)
    retirement_order = []
    for article in sorted(articles, key=publication_order):
        if len(articles) - len(retired) <= max_articles and len(kept_sources) <= max_sources:
            break
        if len(articles) - len(retired) <= 1:
            raise ValueError('Rotation cannot fit the source cap without losing keeper evidence or every post')
        retired.add(article['id'])
        retirement_order.append(article['id'])
        kept_sources = [source for source in sources
                        if source['id'] in keepers or owners[source['id']] - retired]
    if len(articles) - len(retired) > max_articles or len(kept_sources) > max_sources:
        raise ValueError('Rotation cannot satisfy the public snapshot limits')
    # Preserve every retained record byte-for-byte at the JSON-value level and its
    # editorial display order. Selection recency is independent of that order.
    value['articles'] = [article for article in articles if article['id'] not in retired]
    value['sources'] = kept_sources
    kept_ids = {source['id'] for source in kept_sources}
    needed = global_refs | set().union(*(references[a['id']] for a in value['articles']))
    if not needed <= kept_ids:
        raise ValueError('Rotation would leave a dangling evidence reference')
    removed_sources = [source['id'] for source in sources if source['id'] not in kept_ids]
    report = {
        'policy': 'oldest-first-publication-event-id',
        'limits': {'articles': max_articles, 'sources': max_sources},
        'input_counts': {'articles': len(articles), 'sources': len(sources)},
        'retained_counts': {'articles': len(value['articles']), 'sources': len(kept_sources)},
        'retired_article_ids': retirement_order,
        'removed_source_ids': removed_sources,
        'keeper_source_ids': sorted(keepers),
        'retained_article_ids': [a['id'] for a in value['articles']],
        'source_owners': {key: sorted(ids) for key, ids in owners.items()},
        'retained_provenance_complete': True,
        'input_mutated': False,
    }
    return value, report
