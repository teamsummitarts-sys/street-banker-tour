# -*- coding: utf-8 -*-
"""Put the module heading systems on the display face.

Design system v1. Re-runnable and idempotent.

    python tools/adopt_module_headings.py --dry-run
    python tools/adopt_module_headings.py

Six modules carry their own class vocabulary because their JavaScript
binds to it - Tour OS (`to-`), Signal (`sg-`), Operator Desk (`dk-`),
Press Desk (`pd-`), Beats (`bt-`), and the two already done by hand,
Light Studio (`lx-`) and the Team-Up Board (`tb-`). Rewriting their
markup would mean rewriting their scripts, so the CSS moves instead:
their h1 becomes the 28px display step with the width axis, and their h2
becomes the 12px mono label. Same class names, same bindings, the system's
typography.
"""
import io
import os
import re
import sys
import collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

H1 = ("font-family: var(--sb-display); font-size: 28px; font-weight: 800; "
      "font-stretch: 112%; line-height: 1.1; text-transform: uppercase; "
      "letter-spacing: 0; margin: 0;")
H2 = ("font-family: var(--sb-mono); font-size: 12px; font-weight: 500; "
      "letter-spacing: 0.13em; text-transform: uppercase;")

# (file, selector, which step, declarations to preserve from the original)
TARGETS = [
    ("static/css/tour-os.css", ".to-h1", "h1"),
    ("static/css/tour-os.css", ".to-h2", "h2"),
    ("static/css/signal.css", ".sg-h1", "h1"),
    ("static/css/signal.css", ".sg-h2", "h2"),
    ("static/css/operator-desk.css", ".dk-h1", "h1"),
    ("static/css/operator-desk.css", ".dk-h2", "h2"),
    ("static/css/press-desk.css", ".pd-h1", "h1"),
    ("static/css/press-desk.css", ".pd-h2", "h2"),
    ("static/css/beats.css", ".bt-h1", "h1"),
    ("static/css/beats.css", ".bt-h2", "h2"),
]

# Declarations that describe placement, not type - kept as they were.
KEEP = ("margin", "padding", "color", "display", "grid", "flex", "gap",
        "border", "background", "width", "max-width", "min-width", "align",
        "justify", "position", "top", "left", "right", "bottom", "overflow")

REPLACE = ("font-size", "font-weight", "font-family", "font-stretch",
           "letter-spacing", "text-transform", "line-height")


def main():
    dry = "--dry-run" in sys.argv
    done = collections.Counter()

    for path, sel, step in TARGETS:
        full = os.path.join(ROOT, path)
        s = io.open(full, encoding="utf8").read()
        m = re.search(re.escape(sel) + r'\s*\{([^}]*)\}', s)
        if not m:
            print("  ?? %s not found in %s" % (sel, path))
            continue
        body = m.group(1)
        if "--sb-display" in body or "--sb-mono" in body:
            continue                      # already adopted
        kept = []
        for decl in body.split(";"):
            d = decl.strip()
            if not d:
                continue
            prop = d.split(":")[0].strip()
            if prop.startswith(REPLACE):
                continue
            if prop.startswith(KEEP):
                kept.append(d)
        new_body = " " + (H1 if step == "h1" else H2)
        if kept:
            new_body += " " + "; ".join(kept) + ";"
        new = "%s {%s }" % (sel, new_body)
        s = s[:m.start()] + new + s[m.end():]
        done[path] += 1
        if not dry:
            io.open(full, "w", encoding="utf8", newline="").write(s)

    print("%s %d selectors across %d stylesheets"
          % ("WOULD CHANGE" if dry else "CHANGED", sum(done.values()), len(done)))
    for p, n in done.most_common():
        print("  %d  %s" % (n, p))


if __name__ == "__main__":
    main()
