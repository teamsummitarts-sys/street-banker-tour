# -*- coding: utf-8 -*-
"""Gold is brand and primary action only.

Design system v1, the rest of step 3. Re-runnable and idempotent.

    python tools/gold_discipline.py --dry-run
    python tools/gold_discipline.py

The colour sweep put every gold on one ramp. It did not change what gold
was being asked to *mean*, and gold was carrying six jobs: the brand, the
primary button, the hover, the active nav, the metric, and the warning.
When one colour carries six jobs, nothing on screen can claim priority.

Two rules, both mechanical:

  1. A METRIC VALUE IS NOT GOLD. The spec draws `.kpi-num` in ink and
     tints it only when the number means something is wrong. A score
     rendered in brass is competing with the Save button for attention.
     Gold text on a large or monospaced number becomes ink.

  2. GOLD IS NEVER A STATUS. A gold-filled pill on a non-interactive
     element is a status chip, and a gold pill cannot mean "warning" if
     gold is also the Save button. Those become the idle treatment -
     outlined, ink-3 - which is what the badge component does.

Gold on an <a> or a <button> is left alone: that is the primary action,
which is the one job gold keeps. Pages carrying more than one gold fill
are reported rather than edited, because which one is primary is a
judgement about the page, not about the markup.

NOT SWEPT
---------
Public and print surfaces (landing, press kits, one-sheets, certificates,
riders). Those render on light grounds, where "ink" is a near-white and
gold-deep is the readable colour - the dark-UI rule would make them
unreadable. They already sit on the token ramp from the colour sweep.
"""
import io
import os
import re
import sys
import glob
import collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Light-ground surfaces: public pages, press kits, print.
LIGHT = re.compile(
    r'templates/(landing|.*_public|.*_share|public_page|deal_onesheet|'
    r'clean_certificate|licence_public|rider|sheet_public|report_executive|'
    r'press_release_public|epk_public|start_public|plan|legal|signup|login|'
    r'forgot|reset|sign|showday|roster_join|team_join|link_landing|'
    r'link_campaign|beat_share|product_tour|sweep_method|release_check)')

SKIP = {"templates/_gear.html", "templates/rack.html", "templates/artwork.html",
        "templates/_sb.html"}

GOLD_TEXT = re.compile(
    r'\btext-(?:sb-gold(?:-bright)?|amber-[3-5]\d{2}|yellow-[3-5]\d{2})\b')
GOLD_FILL = re.compile(
    r'\bbg-(?:sb-gold(?:-bright|-deep)?|amber-[3-6]\d{2}|yellow-[3-6]\d{2})\b(?!/)')
GOLD_BORDER = re.compile(
    r'\bborder-(?:sb-gold(?:-bright|-deep)?|amber-[3-6]\d{2})\b(?!/)')
BIG = re.compile(r'\btext-(?:2xl|3xl|4xl|5xl|6xl|7xl|8xl|9xl)\b')
NUMERIC = ("sb-num", "tabular-nums")
PILL = ("rounded-full", "rounded-pill")
ON_GOLD = re.compile(r'\btext-(?:sb-on-gold|black)\b')


def rel(p):
    return os.path.relpath(p, ROOT).replace("\\", "/")


def is_metric(cls):
    """Gold sitting on a number that is large or monospaced."""
    if not GOLD_TEXT.search(cls):
        return False
    if GOLD_FILL.search(cls):
        return False          # gold text on gold fill is a different bug
    return bool(BIG.search(cls)) or any(n in cls.split() for n in NUMERIC)


def demote_metric(cls):
    return GOLD_TEXT.sub("text-sb-ink", cls)


def is_status_chip(tag, cls):
    """A gold-filled pill that is not a link or a button."""
    if tag.lower() in ("a", "button"):
        return False
    if not GOLD_FILL.search(cls):
        return False
    return any(p in cls.split() for p in PILL)


def demote_chip(cls):
    cls = GOLD_FILL.sub("bg-transparent", cls)
    cls = GOLD_BORDER.sub("border-sb-line-strong", cls)
    cls = ON_GOLD.sub("text-sb-ink-3", cls)
    if "border" not in cls.split():
        cls = cls + " border"
    return cls


def main():
    dry = "--dry-run" in sys.argv
    counts = collections.Counter()
    touched = collections.Counter()
    fills = collections.Counter()

    for p in sorted(glob.glob(os.path.join(ROOT, "templates", "**", "*.html"),
                              recursive=True)):
        r = rel(p)
        if r in SKIP:
            continue
        s = orig = io.open(p, encoding="utf8", errors="ignore").read()
        light = bool(LIGHT.search(r))

        # rule 1 - metric values, dark surfaces only
        if not light:
            def metric_sub(m):
                cls = m.group(1)
                if not is_metric(cls):
                    return m.group(0)
                counts["metric value: gold -> ink"] += 1
                touched[r] += 1
                return 'class="%s"' % demote_metric(cls)
            s = re.sub(r'class="([^"{]*)"', metric_sub, s)

        # rule 2 - gold-filled status chips, dark surfaces only
        if not light:
            def chip_sub(m):
                tag, pre, cls, post = m.group(1), m.group(2), m.group(3), m.group(4)
                if not is_status_chip(tag, cls):
                    return m.group(0)
                counts["status chip: gold fill -> idle"] += 1
                touched[r] += 1
                # The '>' matters: the regex consumes it, so the
                # replacement has to put it back. Leaving it off turns
                # every demoted chip into an unterminated tag, which the
                # browser then swallows the following content into.
                return '<%s%sclass="%s"%s>' % (tag, pre, demote_chip(cls), post)
            s = re.sub(r'<(\w+)([^>]*?)class="([^"{]*)"([^>]*?)>', chip_sub, s)

        # report: gold fills left per page
        n = len(GOLD_FILL.findall(s))
        if n:
            fills[r] = n

        if s != orig and not dry:
            io.open(p, "w", encoding="utf8", newline="").write(s)

    print("%s %d templates" % ("WOULD CHANGE" if dry else "CHANGED", len(touched)))
    for k, n in counts.most_common():
        print("  %5d  %s" % (n, k))
    over = [(p, n) for p, n in fills.most_common() if n > 1]
    print("\nSTILL MORE THAN ONE GOLD FILL (a judgement per page, not a sweep):")
    print("  %d templates, %d fills" % (len(over), sum(n for _, n in over)))
    for p, n in over[:15]:
        print("    %3d  %s" % (n, p))


if __name__ == "__main__":
    main()
