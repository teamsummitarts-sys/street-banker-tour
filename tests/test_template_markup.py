"""Structural checks on the templates themselves.

Jinja renders whatever it is given and a browser parses whatever it gets,
so a template can be structurally wrong and still serve a 200 with no error
anywhere. The checks here are for the damage that is invisible until
somebody looks at the page.
"""
import glob
import io
import os
import re

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_TAG_START = re.compile(r'<[a-zA-Z][a-zA-Z0-9-]*\b')


def _templates():
    return sorted(glob.glob(os.path.join(HERE, "templates", "**", "*.html"),
                            recursive=True))


def _unclosed_tags(src):
    """Opening tags whose '>' is missing.

    Walks each tag from its name to its terminator, stepping over quoted
    attribute values so a '<' or '>' inside one is not mistaken for
    structure. A '<' reached before any '>' means the tag never closed.
    """
    out = []
    for m in _TAG_START.finditer(src):
        i, n = m.end(), len(src)
        while i < n:
            ch = src[i]
            if ch == ">":
                break
            if ch == "<":
                out.append((src.count("\n", 0, m.start()) + 1,
                            src[m.start():i].replace("\n", " ")[:120]))
                break
            if ch in "\"'":
                j = src.find(ch, i + 1)
                if j < 0:
                    break
                i = j + 1
                continue
            # `class="a"{% if x < y %}...{% endif %}>` is valid, and the
            # comparison inside it is not the start of a tag.
            if src.startswith("{%", i) or src.startswith("{{", i):
                close = "%}" if src.startswith("{%", i) else "}}"
                j = src.find(close, i + 2)
                if j < 0:
                    break
                i = j + 2
                continue
            i += 1
    return out


def test_no_opening_tag_is_missing_its_closing_bracket():
    """The design-system-v1 sweep (90754c4) ate the '>' off nineteen
    opening tags - `<div class="..." style="width: 40%;"</div>`.

    Nothing caught it for four days. Flask served the page, Jinja rendered
    it, and the HTML parser silently treated the stray `</div` as an
    attribute name, so the element never closed and every following sibling
    nested inside it. On the royalty and analytics pages that collapsed
    whole stacks of rows onto one line.

    A parser cannot report this because HTML has no way to be invalid. So
    the check has to happen here.
    """
    offenders = []
    for p in _templates():
        src = io.open(p, encoding="utf8", errors="replace").read()
        for line, snippet in _unclosed_tags(src):
            offenders.append("  %s:%d\n      %s"
                             % (os.path.basename(p), line, snippet))
    assert not offenders, (
        "%d opening tags never close - the element swallows everything "
        "after it:\n%s" % (len(offenders), "\n".join(offenders)))
