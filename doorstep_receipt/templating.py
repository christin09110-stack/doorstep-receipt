"""A 40-line template renderer, and why this app does not use a real one.

The first build used ``str.format()`` on one HTML file. That meant every brace
in the stylesheet had to be doubled, which is the kind of thing that works until
somebody adds a CSS rule and the page throws a KeyError on a colour.

This replaces it with ``{{name}}`` placeholders, which CSS never produces, and
adds the property that matters more: **everything is HTML-escaped by default**.
Tracking numbers, carrier status lines and letter bodies are all third-party
text on a page this app signs. A key ending in ``_html`` opts out, which makes
every raw insertion visible in the call site as well as here.

A missing key raises rather than rendering an empty gap, because a blank field
on an evidence document is worse than an error page.
"""

from __future__ import annotations

import html
import re
from pathlib import Path

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
_PLACEHOLDER = re.compile(r"\{\{([a-z0-9_]+)\}\}")


class MissingTemplateValue(KeyError):
    pass


def render_string(template: str, **context) -> str:
    def substitute(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in context:
            raise MissingTemplateValue(key)
        value = context[key]
        if value is None:
            return ""
        # quote=True, which is html.escape's default. Twelve placeholders in
        # these templates sit inside HTML attributes (`value="{{query}}"` and
        # friends), and a bare " closes the attribute and opens an event
        # handler. In a text node &quot; renders as ", so nothing a reader
        # sees changes.
        #
        # The injection path that matters is the model: `status_text` is
        # Bedrock's transcription of a tracking page somebody photographed,
        # and guard.py has opinions about accusations, not about quotation
        # marks. Model output is third-party input, and it reaches templates.
        return str(value) if key.endswith("_html") else html.escape(str(value))

    return _PLACEHOLDER.sub(substitute, template)


def render(name: str, **context) -> str:
    return render_string((TEMPLATE_DIR / name).read_text(encoding="utf-8"), **context)


def page(title: str, body_html: str, nav_html: str = "", subtitle: str = "") -> str:
    """Wrap a body in the shared parchment shell."""
    return render("_shell.html", title=title, subtitle=subtitle, body_html=body_html, nav_html=nav_html)
