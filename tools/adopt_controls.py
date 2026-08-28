# -*- coding: utf-8 -*-
"""Put every button and status pill on the component library.

Design system v1, the rest of steps 5 and 6. Re-runnable and idempotent.

    python tools/adopt_controls.py --dry-run
    python tools/adopt_controls.py

Converting 158 templates by hand is not the job; making them compose
from the library is. Buttons and badges are what actually repeat - the
same control written forty different ways - so moving those onto
`sb-btn` and `sb-badge` is what makes a page look like it belongs to the
system without touching its structure.

Four button families were in the templates:

    gold fill                       -> sb-btn sb-btn-primary
    gold tint / gold border         -> sb-btn sb-btn-secondary
    neutral outline                 -> sb-btn sb-btn-secondary
    red outline or red tint         -> sb-btn sb-btn-danger

The gold-tinted family is the interesting one. It was an outlined button
wearing a 15% gold wash, which is why pages ended up with six things
competing to look primary. In the system it is simply secondary, and the
page gets its one gold fill back.

GUARDS
------
A card is not a button. Module tiles are also `<a>` elements with a
border and a radius, so the sweep requires px AND py padding (cards use
`p-4`), refuses anything whose contents include a block element, and
refuses long bodies of text. State-tinted action buttons (green, amber)
are reported, not converted: giving an action a state colour is a
decision about meaning, and the spec keeps state off actions.
"""
import io
import os
import re
import sys
import glob
import collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SKIP = {"templates/_gear.html", "templates/rack.html", "templates/artwork.html",
        "templates/_sb.html", "templates/base.html"}

# Public/print surfaces render on light grounds and have their own
# button treatments; the dark-UI variants would be invisible there.
LIGHT = re.compile(
    r'templates/(landing|.*_public|.*_share|public_page|deal_onesheet|'
    r'clean_certificate|licence_public|rider|sheet_public|report_executive|'
    r'press_release_public|start_public|plan|legal|signup|login|forgot|'
    r'reset|sign|showday|roster_join|team_join|link_landing|link_campaign|'
    r'beat_share|product_tour|sweep_method|release_check)')

GOLD_FILL = re.compile(r'\bbg-(?:sb-gold(?:-bright|-deep)?|amber-[3-6]\d{2})\b(?!/)')
GOLD_TINT = re.compile(r'\bbg-(?:sb-gold(?:-bright)?|amber-[3-6]\d{2})/')
GOLD_EDGE = re.compile(r'\bborder-(?:sb-gold(?:-bright|-deep)?|amber-[3-6]\d{2})\b')
CRIT = re.compile(r'\b(?:bg|border|text)-(?:sb-crit|red-[3-6]\d{2})\b')
STATE = re.compile(r'\b(?:bg|border|text)-(?:sb-good|sb-warn|green-[3-6]\d{2}|'
                   r'emerald-[3-6]\d{2}|orange-[3-6]\d{2})\b')
NEUTRAL_EDGE = re.compile(r'\bborder-(?:white|black|sb-line|sb-line-strong|gray)')

# Classes that describe where a thing sits, not what it looks like.
KEEP_PREFIX = ("w-", "h-", "min-w-", "min-h-", "max-w-", "max-h-",
               "mt-", "mb-", "ml-", "mr-", "mx-", "my-", "m-",
               "col-", "row-", "order-", "basis-", "grow", "shrink",
               "self-", "justify-", "items-", "gap-", "space-",
               "absolute", "relative", "fixed", "sticky", "inset-",
               "top-", "bottom-", "left-", "right-", "z-",
               "hidden", "block", "inline-block", "inline-flex", "flex",
               "grid", "truncate", "whitespace-", "overflow-",
               "sm:", "md:", "lg:", "xl:", "2xl:", "group", "peer",
               "sr-only", "not-sr-only", "aria-", "data-")
KEEP_EXACT = {"w-full", "block", "hidden", "flex", "grid", "relative",
              "absolute", "truncate", "grow", "shrink-0"}

BLOCKY = re.compile(r'<(?:div|p|h[1-6]|ul|ol|table|section|svg\s+class="[^"]*w-\d\d)', re.I)


def rel(p):
    return os.path.relpath(p, ROOT).replace("\\", "/")


# Every Tailwind utility that describes appearance. Anything matching
# these is the button's old look and is replaced by the variant.
VISUAL = re.compile(
    r'^(?:hover:|focus:|focus-visible:|focus-within:|active:|disabled:|'
    r'group-hover:|peer-|dark:|first:|last:|odd:|even:|has-\[|file:|'
    r'marker:|placeholder:)?'
    r'(?:text-(?:xs|sm|base|lg|[2-9]?xl|\[)|font-(?:thin|light|normal|medium|'
    r'semibold|bold|extrabold|black)|bg-|border|rounded|px-|py-|p-|'
    r'text-(?!left|right|center|wrap|nowrap|balance)[a-z]|ring|shadow|'
    r'uppercase|lowercase|capitalize|tracking-|leading-|transition|'
    r'duration-|ease-|opacity-|from-|via-|to-|decoration-|underline|'
    r'divide-|outline|accent-|caret-)')


def keep(tok):
    """Keep anything that is not the button's old appearance.

    This used to be an allowlist of layout prefixes, which quietly threw
    away every class it did not recognise - including `kit-copy` and
    `add-to-catalog`, which are how the scripts on those pages find
    their buttons. Dropping a hook class breaks a feature and nothing
    says so. Strip what is demonstrably visual; keep the rest."""
    if tok in DISPLAY:
        return False
    if tok in KEEP_EXACT:
        return True
    if tok.startswith(KEEP_PREFIX):
        return True
    return not VISUAL.match(tok)


# `sb-btn` sets display itself; a leftover `block` or `inline-block` would
# fight its inline-flex and break the icon/label centring.
DISPLAY = {"block", "inline-block", "inline-flex", "flex", "grid",
           "inline-grid", "inline"}

# Destructive by name. A Remove button that was only red on hover still
# belongs on the danger variant - that is what the variant is for.
# Deletions only. "Cancel" and "Clear" dismiss something rather than
# destroy it, and the spec draws those as ghost buttons.
DESTRUCTIVE = re.compile(
    r'^\s*(?:remove|delete|revoke|discard|unlink|disconnect|'
    r'×|✕|&times;|&#215;)', re.I)


def base_state(cls):
    """Classification looks at the resting state only: `hover:text-red-400`
    describes what happens under the pointer, not what the control is."""
    return " ".join(t for t in cls.split() if ":" not in t or t.startswith(
        ("sm:", "md:", "lg:", "xl:", "2xl:")))


def variant(cls, label=""):
    """Which button is this? None means leave it alone."""
    toks = cls.split()
    if any(t.startswith("sb-btn") for t in toks):
        return None
    if not any(t.startswith("rounded") for t in toks):
        return None
    if not (any(t.startswith("px-") for t in toks)
            and any(t.startswith("py-") for t in toks)):
        return None
    base = base_state(cls)
    if STATE.search(base):
        return None                      # a decision about meaning, not shape
    if DESTRUCTIVE.match(label) and not GOLD_FILL.search(base):
        return "danger"
    if CRIT.search(base):
        return "danger"
    if GOLD_FILL.search(base):
        return "primary"
    if GOLD_TINT.search(base) or GOLD_EDGE.search(base):
        return "secondary"
    if NEUTRAL_EDGE.search(base):
        return "secondary"
    return None


def size_of(cls):
    toks = cls.split()
    if "text-xs" in toks or any(t.startswith("py-1") and t != "py-1.5" for t in toks):
        return "sb-btn-sm"
    if "py-1.5" in toks or "py-1" in toks:
        return "sb-btn-sm"
    return None


def rebuild(cls, var):
    kept = [t for t in cls.split() if keep(t)]
    out = ["sb-btn", "sb-btn-" + var]
    sz = size_of(cls)
    if sz:
        out.append(sz)
    return " ".join(out + kept)


def main():
    dry = "--dry-run" in sys.argv
    counts = collections.Counter()
    touched = collections.Counter()
    state_btns = collections.Counter()

    pat = re.compile(
        r'<(a|button)((?:(?!<)[^>])*?)class="([^"{]*)"((?:(?!<)[^>])*?)>(.*?)</\1>',
        re.S | re.I)

    for p in sorted(glob.glob(os.path.join(ROOT, "templates", "**", "*.html"),
                              recursive=True)):
        r = rel(p)
        if r in SKIP or LIGHT.search(r):
            continue
        s = orig = io.open(p, encoding="utf8", errors="ignore").read()

        def sub(m):
            tag, pre, cls, post, inner = m.groups()
            if len(inner) > 160 or BLOCKY.search(inner):
                return m.group(0)        # a card, not a control
            if STATE.search(cls) and any(t.startswith("rounded") for t in cls.split()):
                state_btns[r] += 1
            var = variant(cls, re.sub(r"<[^>]*>", "", inner).strip())
            if not var:
                return m.group(0)
            counts["button -> sb-btn-" + var] += 1
            touched[r] += 1
            return '<%s%sclass="%s"%s>%s</%s>' % (
                tag, pre, rebuild(cls, var), post, inner, tag)

        s = pat.sub(sub, s)
        if s != orig and not dry:
            io.open(p, "w", encoding="utf8", newline="").write(s)

    print("%s %d templates" % ("WOULD CHANGE" if dry else "CHANGED", len(touched)))
    for k, n in counts.most_common():
        print("  %5d  %s" % (n, k))
    print("\nleft alone - state-coloured action buttons (%d in %d templates):"
          % (sum(state_btns.values()), len(state_btns)))
    for p, n in state_btns.most_common(8):
        print("    %3d  %s" % (n, p))
    print("\nbusiest:")
    for p, n in touched.most_common(12):
        print("  %5d  %s" % (n, p))


if __name__ == "__main__":
    main()
