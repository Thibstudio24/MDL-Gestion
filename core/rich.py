"""Markdown → HTML, puis nettoyage par liste blanche (aucune balise active)."""
from __future__ import annotations

import re
from html.parser import HTMLParser

import markdown as md
from django.utils.safestring import mark_safe

ALLOWED_TAGS = {
    "p", "br", "strong", "b", "em", "i", "u", "s", "del", "ul", "ol", "li", "h1", "h2", "h3",
    "h4", "blockquote", "code", "pre", "a", "hr", "table", "thead", "tbody", "tr", "th", "td",
    "span", "div", "small", "sup", "sub",
}
ALLOWED_ATTRS = {"a": {"href", "title"}, "td": {"colspan", "rowspan"}, "th": {"colspan", "rowspan"}}
DROP_CONTENT = {"script", "style", "iframe", "object", "embed", "svg", "math"}
BAD_HREF = re.compile(r"^\s*(javascript|data|vbscript|file):", re.I)


class _Sanitizer(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self._drop_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in DROP_CONTENT:
            self._drop_depth += 1
            return
        if tag == "input":  # cases à cocher Markdown → ☐ / ☑
            checked = any(k == "checked" for k, _v in attrs)
            self.out.append("☑" if checked else "☐")
            return
        if tag not in ALLOWED_TAGS:
            return
        allowed = ALLOWED_ATTRS.get(tag, set())
        parts = []
        for key, value in attrs:
            if key not in allowed:
                continue
            if key == "href" and BAD_HREF.match(value or ""):
                continue
            parts.append(' %s="%s"' % (key, (value or "").replace('"', "&quot;")))
        self.out.append("<%s%s>" % (tag, "".join(parts)))

    def handle_startendtag(self, tag, attrs):
        if tag == "br":
            self.out.append("<br>")
        elif tag == "hr":
            self.out.append("<hr>")
        else:
            self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag in DROP_CONTENT:
            self._drop_depth = max(0, self._drop_depth - 1)
            return
        if tag in ALLOWED_TAGS:
            self.out.append("</%s>" % tag)

    def handle_data(self, data):
        if self._drop_depth == 0:
            self.out.append(
                data.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            )


def sanitize(html: str) -> str:
    parser = _Sanitizer()
    parser.feed(html or "")
    parser.close()
    return "".join(parser.out)


def render(text: str) -> str:
    """Markdown simplifié rendu puis nettoyé (corps de message, mentions, descriptions)."""
    if not text:
        return ""
    html = md.markdown(
        text,
        extensions=["extra", "sane_lists", "nl2br"],
        output_format="html5",
    )
    # Sortie passée par sanitize() : balises et attributs non autorisés retirés.
    return mark_safe(sanitize(html))  # nosec B308 B703


def plain(text: str) -> str:
    """Version texte brut (e-mails alternatifs, exports)."""
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text or "")
    text = re.sub(r"[*_`#>]+", "", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()
