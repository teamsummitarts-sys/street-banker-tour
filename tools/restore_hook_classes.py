# -*- coding: utf-8 -*-
"""Put back the JavaScript hook classes the control sweep dropped.

`tools/adopt_controls.py` originally rebuilt a button's class list from
an allowlist of layout utilities, which silently discarded everything it
did not recognise. Twelve of those were not styles at all - they were how
the page's own script finds the button:

    document.querySelectorAll(".copy-caption").forEach(...)

Drop the class and the feature is dead. Nothing throws, nothing logs, the
button just stops working. The tool is fixed (it now strips what is
demonstrably visual and keeps the rest), but the templates it already
rewrote need repairing, which is what this does.

Matching is by tag plus visible label against the same element at HEAD,
so the class goes back on the button it came off rather than on every
button that happens to look similar.

    python tools/restore_hook_classes.py --dry-run
    python tools/restore_hook_classes.py
"""
import io
import os
import re
import sys
import glob
import subprocess
import collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SELECTOR = re.compile(r'querySelectorAll?\(\s*["\']\.([A-Za-z][\w-]*)["\']')
ELEMENT = re.compile(r'<(a|button)\b([^>]*)>(.*?)</\1>', re.S | re.I)


def rel(p):
    return os.path.relpath(p, ROOT).replace("\\", "/")


def text_of(html):
    return re.sub(r'\s+', " ", re.sub(r'<[^>]*>', "", html)).strip()


def classes_of(attrs):
    m = re.search(r'class="([^"]*)"', attrs)
    return m.group(1).split() if m else []


def main():
    dry = "--dry-run" in sys.argv
    fixed = collections.Counter()
    unmatched = []

    for p in sorted(glob.glob(os.path.join(ROOT, "templates", "**", "*.html"),
                              recursive=True)):
        r = rel(p)
        cur = io.open(p, encoding="utf8", errors="ignore").read()
        wanted = set(SELECTOR.findall(cur))
        if not wanted:
            continue
        present = set()
        for m in re.finditer(r'class="([^"]*)"', cur):
            present.update(m.group(1).split())
        missing = {c for c in wanted if c not in present}
        if not missing:
            continue

        head = subprocess.run(["git", "show", "HEAD:" + r], cwd=ROOT,
                              capture_output=True, text=True,
                              encoding="utf8", errors="ignore").stdout
        if not head:
            continue

        # label -> hook class, taken from HEAD
        want_by_label = {}
        for m in ELEMENT.finditer(head):
            cls = classes_of(m.group(2))
            hooks = [c for c in cls if c in missing]
            if hooks:
                want_by_label.setdefault(
                    (m.group(1).lower(), text_of(m.group(3))), hooks[0])

        def sub(m):
            tag, attrs, inner = m.group(1), m.group(2), m.group(3)
            key = (tag.lower(), text_of(inner))
            hook = want_by_label.get(key)
            if not hook:
                return m.group(0)
            cls = classes_of(attrs)
            if hook in cls:
                return m.group(0)
            fixed[r] += 1
            if cls:
                new_attrs = re.sub(r'class="([^"]*)"',
                                   lambda a: 'class="%s %s"' % (hook, a.group(1)),
                                   attrs, count=1)
            else:
                new_attrs = attrs + ' class="%s"' % hook
            return "<%s%s>%s</%s>" % (tag, new_attrs, inner, tag)

        new = ELEMENT.sub(sub, cur)
        still = {c for c in missing
                 if not any(c in mm.group(1).split()
                            for mm in re.finditer(r'class="([^"]*)"', new))}
        for c in sorted(still):
            unmatched.append("%s .%s" % (r, c))
        if new != cur and not dry:
            io.open(p, "w", encoding="utf8", newline="").write(new)

    print("%s %d hook classes across %d templates"
          % ("WOULD RESTORE" if dry else "RESTORED",
             sum(fixed.values()), len(fixed)))
    for p, n in fixed.most_common():
        print("   %2d  %s" % (n, p))
    if unmatched:
        print("\nnot matched by label - check these by hand "
              "(may be built by JS at runtime):")
        for u in unmatched:
            print("   %s" % u)


if __name__ == "__main__":
    main()
