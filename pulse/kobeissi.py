"""Check ordinary public product pages, never member indexes or issue bodies.

The publisher's unauthenticated browser redirects its issue indexes to account
creation/subscription. HTML returned before that redirect is not a public feed.
These checks record the access boundary; they do not manufacture issue cards.
"""
from html.parser import HTMLParser
import re


PRODUCTS = {
    "kobeissi-newsletter": {
        "url": "https://www.thekobeissiletter.com/analysis/newsletters",
        "title": "Newsletters",
        "required": ("subscription-based weekly newsletter", "The Kobeissi Letter"),
    },
    "kobeissi-chart-week": {
        "url": "https://www.thekobeissiletter.com/analysis/chart-of-the-week",
        "title": "Chart of the Week",
        "required": ("FREE weekly chart", "create an account"),
    },
}


class _PublicProductText(HTMLParser):
    """Read displayed marketing text only, ignoring scripts and gated markup."""
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.text = []
        self.title = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        hidden = (bool(self.stack and self.stack[-1][1]) or tag in {"script", "style", "template", "noscript"}
                  or "hidden" in values or values.get("aria-hidden") == "true"
                  or "w-condition-invisible" in values.get("class", "").split()
                  or bool(re.search(r"display\s*:\s*none|visibility\s*:\s*hidden", values.get("style", ""), re.I))
                  or "data-ms-content" in values)
        if tag not in self.VOID:
            self.stack.append((tag, hidden))

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break

    def handle_data(self, text):
        if not self.stack or not self.stack[-1][1]:
            self.text.append(text)
            if any(tag == "title" for tag, _ in self.stack):
                self.title.append(text)


def check_public_product(payload, source):
    product = PRODUCTS.get(source.get("id"))
    if not product or source.get("feed_url") != product["url"]:
        raise ValueError("Only the verified public Kobeissi product pages are supported")
    parser = _PublicProductText()
    parser.feed(payload.decode("utf-8", errors="replace"))
    title = " ".join(" ".join(parser.title).split())
    text = " ".join(" ".join(parser.text).split()).casefold()
    if title != product["title"] or any(phrase.casefold() not in text for phrase in product["required"]):
        raise ValueError("Public product identity or access wording changed; review access again")
    return [], {"rejected_count": 0, "filtered_count": 0, "window_truncated_count": 0,
                "access_status": "not_connected", "verification_scope": "public_product_access_notice"}
