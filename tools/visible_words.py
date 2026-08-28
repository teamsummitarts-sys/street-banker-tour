"""Count what a visitor actually reads on the homepage.

Phase 7 of the homepage brief sets a target on *visible* words, so three
kinds of text have to come out of the count or the number is fiction:

  1. closed <details> bodies — on the page, one click away, not read
  2. [hidden] elements
  3. visually-hidden elements — the screen-reader fallbacks this codebase
     uses for every hover-driven panel, which restate their visible
     content verbatim

The third is the one that bites. Global Distribution carries a complete
<dl> repeating every workflow stage for readers without a pointer;
counting it makes the section look twice as wordy as it reads. The
visually-hidden class names are discovered from the built stylesheets
rather than hardcoded, so a new one cannot silently inflate the count.

    python tools/visible_words.py
    python tools/visible_words.py --compare <before.html>
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402

CSS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "static", "css")

# How this codebase writes "present for assistive tech, invisible on screen".
_HIDDEN_SIGNS = ("clip-path:inset(50%)", "clip:rect(0000)", "clip:rect(0,0,0,0)")


def visually_hidden_classes():
    """Class names the stylesheets render invisible."""
    found = {"sr-only"}
    for name in sorted(os.listdir(CSS_DIR)):
        if not name.endswith(".css"):
            continue
        css = open(os.path.join(CSS_DIR, name), encoding="utf-8").read()
        for match in re.finditer(r"\.([A-Za-z0-9_-]+)\s*\{([^}]*)\}", css):
            block = match.group(2).replace(" ", "")
            if any(sign in block for sign in _HIDDEN_SIGNS):
                found.add(match.group(1))
    return found


def visible_words(html, hidden_classes=None):
    hidden_classes = hidden_classes or visually_hidden_classes()
    body = re.sub(r"<(script|style|svg|template)[^>]*>.*?</\1>", " ", html,
                  flags=re.S | re.I)
    body = re.sub(r"<!--.*?-->", " ", body, flags=re.S)
    body = re.sub(r"<details(?![^>]*\bopen\b)[^>]*>.*?</details>", " ", body,
                  flags=re.S | re.I)
    body = re.sub(r"<(\w+)[^>]*\shidden[^>]*>.*?</\1>", " ", body, flags=re.S | re.I)
    for cls in hidden_classes:
        body = re.sub(
            r'<(\w+)[^>]*class="[^"]*\b%s\b[^"]*"[^>]*>.*?</\1>' % re.escape(cls),
            " ", body, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", body)
    text = re.sub(r"&[a-z]+;", " ", text)
    return [w for w in text.split() if any(c.isalpha() for c in w)]


def _render(path="/"):
    return create_app().test_client().get(path).get_data(as_text=True)


if __name__ == "__main__":
    classes = visually_hidden_classes()
    if len(sys.argv) > 2 and sys.argv[1] == "--compare":
        before = open(sys.argv[2], encoding="utf-8").read()
        b = len(visible_words(before, classes))
        a = len(visible_words(_render(), classes))
        print("before %d  after %d  reduction %.1f%%" % (b, a, 100 * (b - a) / b))
    else:
        print("visible words: %d" % len(visible_words(_render(), classes)))
        print("visually-hidden classes excluded: %d" % len(classes))
