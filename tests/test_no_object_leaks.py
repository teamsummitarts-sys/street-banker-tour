"""No Python object ever renders onto a public page.

This exists because it already happened: `BRAND_MEMORY["copy"]` and
`FAN_PANEL["copy"]` were read in a template as `brand.copy`, Jinja
resolved that to the dict's built-in `copy` method rather than the
string, and the public smart-link page shipped
`<built-in method copy of dict object at 0x000001...>` to visitors.

Two tests here. The first walks every public page and fails on any
rendered object string. The second is the cheaper guard: no config dict
may use a key that collides with a dict method, because the template that
reads it will look correct and render garbage.
"""
import glob
import re

import pytest

from app import create_app

# Every route a signed-out visitor can reach and read.
PUBLIC_ROUTES = [
    "/", "/product-tour", "/product-tour/smart-link", "/start",
    "/artist-control", "/plan", "/lanes", "/creative-studio", "/rollout",
    "/royalty-sweep", "/distribution", "/metadata", "/ai",
    "/artist-twin/start", "/catalog-sweep", "/services", "/remix-lab",
    "/press", "/about",
    "/contact", "/partners", "/terms", "/privacy", "/submit", "/login",
    "/signup", "/forgot",
]

# What a leaked object looks like once Jinja has escaped it.
LEAKS = [
    "<built-in method", "&lt;built-in method",
    "[object Object]", "object at 0x", "&lt;function", "<function ",
    "dict_keys(", "dict_values(", "dict_items(",
    "<bound method", "&lt;bound method",
    "<generator object", "&lt;generator object",
]

# Names that resolve to a dict method before they resolve to a key.
RESERVED = ("copy", "items", "keys", "values", "get", "pop", "update",
            "clear", "setdefault", "fromkeys", "popitem")


@pytest.fixture(scope="module")
def client():
    return create_app().test_client()


@pytest.mark.parametrize("route", PUBLIC_ROUTES)
def test_public_page_renders_no_python_objects(client, route):
    response = client.get(route)
    assert response.status_code == 200, "%s answered %s" % (route, response.status_code)
    body = response.get_data(as_text=True)
    for leak in LEAKS:
        assert leak not in body, "%s leaked %r" % (route, leak)


@pytest.mark.parametrize("route", PUBLIC_ROUTES)
def test_public_page_renders_no_bare_none_or_undefined(client, route):
    """`None` and `undefined` printed into visible text, not into markup.

    Checked against text content only: "None" is legitimate inside a
    script, an attribute or a word like "Nonetheless", and `undefined`
    appears in perfectly good JavaScript.
    """
    body = client.get(route).get_data(as_text=True)
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", body, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    assert not re.search(r"(?<![A-Za-z])None(?![A-Za-z])", text), route
    assert "undefined" not in text, route


def test_no_template_dot_accesses_a_dict_method_name():
    """The real hazard is dot-access in a template, not the key name.

    `thing.copy` in Jinja resolves to the dict's built-in method before it
    looks for the key, and renders `<built-in method copy of dict object
    at 0x...>` onto the page. Subscript access — `thing["copy"]` — is
    always safe, which is why configs may legitimately carry keys called
    copy, items, keys or values.

    This test therefore bans the dangerous *access*, not the name. It
    caught a live one: `clean_release.html` read `n.keys` on a dict that
    really did have a "keys" key, and shipped the built-in method into a
    data-cats attribute, silently breaking the hover-highlight it fed.
    """
    import glob
    import os

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pattern = re.compile(r"\{\{[^}]*?[a-z_][a-z0-9_]*\.(%s)" % "|".join(RESERVED),
                         re.IGNORECASE)
    offenders = []
    for path in glob.glob(os.path.join(root, "templates", "**", "*.html"),
                          recursive=True):
        source = open(path, encoding="utf-8").read()
        for match in pattern.finditer(source):
            line = source[:match.start()].count(chr(10)) + 1
            offenders.append("%s:%d %s" % (os.path.basename(path), line,
                                           match.group(0).strip()))
    assert not offenders, (
        "these render a dict method instead of the value — use subscript "
        "access instead: %s" % offenders)
