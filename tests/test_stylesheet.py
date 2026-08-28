"""The stylesheet is built, committed, and therefore able to go stale.

Swapping the Tailwind Play CDN for a built file trades 120 kB of runtime
compiler for 14 kB of static CSS. The cost of that trade is a new failure
mode: add a class to a template, forget to rebuild, and the page renders
without it. Nothing crashes. Nothing logs. It just looks wrong, and only
on the page you were last editing.

So the suite samples the classes actually used across the templates and
fails when the stylesheet does not carry them. Rebuild from the repo root:

    npm install tailwindcss@3
    npx tailwindcss -c tools/tailwind.config.js \\
        -i tools/tailwind-input.css \\
        -o static/css/tailwind.css --minify

Then bump the ?v= on the <link> and VERSION in static/js/sw.js, or
browsers keep serving the old sheet.
"""
import io
import os
import re

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSS = os.path.join(HERE, "static", "css", "tailwind.css")

# Enough of Tailwind's vocabulary to tell "this page uses utilities" from
# "this page is styled entirely by its own CSS".
TW_PREFIXES = ("flex", "grid", "text-", "bg-", "border-", "rounded",
               "w-", "h-", "p-", "px-", "py-", "m-", "mx-", "my-", "gap-",
               "font-", "items-", "justify-", "space-", "max-w-", "min-h-")
TW_BARE = {"block", "inline", "hidden", "relative", "absolute", "fixed",
           "truncate", "uppercase", "italic", "underline"}


def _css():
    return io.open(CSS, encoding="utf8").read()


def test_the_stylesheet_is_committed():
    assert os.path.exists(CSS), "static/css/tailwind.css is missing"
    assert os.path.getsize(CSS) > 20000, "stylesheet looks truncated"


def test_no_template_still_pulls_the_cdn_compiler():
    """cdn.tailwindcss.com is the JIT compiler, not a stylesheet - it is
    120 kB of JavaScript that generates CSS in the browser on every page
    load, and Tailwind's own docs say not to ship it."""
    import glob
    offenders = []
    for p in glob.glob(os.path.join(HERE, "templates", "**", "*.html"),
                       recursive=True):
        if "cdn.tailwindcss.com" in io.open(p, encoding="utf8").read():
            offenders.append(os.path.basename(p))
    assert not offenders, "still loading the CDN compiler: %s" % offenders


def test_every_template_that_needs_styles_links_the_stylesheet():
    """A page that loaded the CDN before must link the built file now, or
    it renders unstyled."""
    import glob
    missing = []
    for p in glob.glob(os.path.join(HERE, "templates", "**", "*.html"),
                       recursive=True):
        s = io.open(p, encoding="utf8").read()
        # Only pages that carry their own <head>; the rest inherit it.
        if "<head>" not in s:
            continue
        # A page using no Tailwind utilities does not need the sheet.
        # login.html is styled entirely by its own lsr-* stylesheet.
        # Anchor on the token start: "w-" matches inside "lsr-row-title"
        # otherwise, and every custom class looks like a utility.
        if not any(t.startswith(TW_PREFIXES) or t in TW_BARE
                   for blob in re.findall(r'class="([^"]*)"', s)
                   for t in blob.split()):
            continue
        if "/static/css/tailwind.css" not in s:
            missing.append(os.path.basename(p))
    assert not missing, "no stylesheet link: %s" % missing


# --- staleness -----------------------------------------------------------

def _used_classes():
    """Classes appearing in class="..." across every template."""
    import glob
    used = set()
    for p in glob.glob(os.path.join(HERE, "templates", "**", "*.html"),
                       recursive=True):
        s = io.open(p, encoding="utf8").read()
        for blob in re.findall(r'class="([^"]*)"', s):
            # Skip Jinja expressions - the class list inside them is
            # conditional and often split across branches.
            if "{" in blob:
                continue
            for c in blob.split():
                used.add(c)
    return used


_HEX = re.compile(r'\\([0-9a-fA-F]{1,6}) ?')


def _unescaped_css():
    """Tailwind escapes selectors two different ways: simple characters
    get a backslash (text-[9px] -> .text-\\[9px\\]) but others become hex
    escapes (a comma is \\2c followed by a space). Reversing both is more
    reliable than trying to reproduce the escaping."""
    css = _HEX.sub(lambda m: chr(int(m.group(1), 16)), _css())
    return css.replace("\\", "")


def test_the_stylesheet_is_not_stale():
    """Checks the arbitrary-value classes used in the templates against
    the build. Those are unambiguously Tailwind's to generate - nothing
    else in the project produces a class with brackets in it - so any one
    of them missing means the build predates the template.

    This is the test that fails when somebody adds a class and forgets to
    rebuild."""
    css = _unescaped_css()
    missing = [c for c in _used_classes()
               if "[" in c and "]" in c and "." + c not in css]
    assert not missing, (
        "%d arbitrary-value classes are in the templates but not the built "
        "stylesheet - it is stale, rebuild it. Sample: %s"
        % (len(missing), sorted(missing)[:10]))


def test_chart_js_is_not_loaded_on_every_page():
    """69 kB for six pages that draw a chart. The other 274 routes should
    not pay for it."""
    base = io.open(os.path.join(HERE, "templates", "base.html"),
                   encoding="utf8").read()
    # Match the script tag, not the words - the comment explaining why it
    # is absent naturally contains the name.
    assert "npm/chart.js" not in base, \
        "Chart.js is back in base.html - every route pays 69 kB for it"
    assert "{% block head_scripts %}" in base


def test_the_pages_that_draw_charts_still_load_chart_js():
    # Valuation and Recovery draw their own bars from the artist's
    # statement months now - no Chart.js, so nothing to keep in step.
    for name in ("royalties", "overview", "stats", "audience"):
        s = io.open(os.path.join(HERE, "templates", name + ".html"),
                    encoding="utf8").read()
        assert "new Chart(" in s, name
        assert "chart.js" in s.lower(), \
            "%s draws a chart but no longer loads Chart.js" % name


# --- utilities that resolve to nothing -----------------------------------
#
# test_the_stylesheet_is_not_stale above only looks at arbitrary-value
# classes, on the reasoning that nothing but Tailwind produces a class with
# brackets in it. That is true, and it is also why the check missed the
# worst stylesheet regression this repo has had.
#
# The design-system-v1 sweep (90754c4) rewrote every raw hex in the markup
# into a token class. Where it could not resolve one it wrote a class that
# does not exist - bg-transparent-bright, border-sb-line-strong-bright,
# text-sb-ink-deep - and in 27 places that class was the fill of a
# proportion bar, so every bar in the royalty, capital and analytics pages
# rendered as an empty outline. The raw-hex lock passed, because the hex
# really was gone. The staleness check passed, because none of the broken
# classes had brackets. Nothing else looked.
#
# So: a class in the markup that looks like a utility must resolve to a
# rule somewhere. Hand-written class names are out of scope - one with no
# rule may be a JavaScript hook rather than a defect, and telling those
# apart is a lint concern, not a question about whether the build is
# current.

_SELECTOR = re.compile(r'\.((?:\\[0-9a-fA-F]{1,6} ?|\\.|[A-Za-z0-9_-])+)')
_SCRIPT = re.compile(r"<script[^>]*>.*?</script>", re.S)
_STYLE = re.compile(r"<style[^>]*>(.*?)</style>", re.S)


def _templates():
    import glob
    return glob.glob(os.path.join(HERE, "templates", "**", "*.html"),
                     recursive=True)


def _unescape_selector(tok):
    """Recover a class name from its CSS selector spelling.

    Tailwind escapes / [ ] # . % and : one way and commas another, so both
    forms have to be reversed to get back to what the template wrote.
    """
    out, i = [], 0
    while i < len(tok):
        if tok[i] == "\\":
            m = re.match(r'\\([0-9a-fA-F]{1,6}) ?', tok[i:])
            if m:
                out.append(chr(int(m.group(1), 16)))
                i += m.end()
                continue
            if i + 1 < len(tok):
                out.append(tok[i + 1])
                i += 2
                continue
            i += 1
            continue
        out.append(tok[i])
        i += 1
    return "".join(out)


def _defined_classes():
    """Every class name carrying a rule: the built sheet, the hand-written
    stylesheets, and the <style> blocks a few pages inline."""
    import glob
    blobs = [io.open(p, encoding="utf8", errors="replace").read()
             for p in glob.glob(os.path.join(HERE, "static", "css", "*.css"))]
    for p in _templates():
        blobs += _STYLE.findall(io.open(p, encoding="utf8",
                                        errors="replace").read())
    names = set()
    for b in blobs:
        for m in _SELECTOR.finditer(b):
            names.add(_unescape_selector(m.group(1)))
    return names


def _looks_like_a_utility(token):
    base = token.split(":")[-1].lstrip("!")
    return (base.startswith(TW_PREFIXES) or base in TW_BARE
            or ("[" in base and "]" in base))


def _class_tokens(blob):
    """The class names a class="..." attribute can put on the element.

    A conditional attribute - class="{{ 'bg-good' if ok else 'bg-crit' }}" -
    still names real classes, and skipping those attributes outright is how
    two dead `bg-white/8` meters survived the first pass of this check. Only
    the quoted literals inside the expression are read; the surrounding
    Jinja is not a class name and reading it as one invents orphans.
    """
    if "{" not in blob:
        return blob.split()
    out = []
    for lit in re.findall(r"'([^']*)'", blob):
        out += lit.split()
    return out


def test_no_utility_class_in_the_markup_resolves_to_nothing():
    defined = _defined_classes()
    orphans = {}
    for p in _templates():
        s = _STYLE.sub("", _SCRIPT.sub(
            "", io.open(p, encoding="utf8", errors="replace").read()))
        for blob in re.findall(r'class="([^"]*)"', s):
            for t in _class_tokens(blob):
                if not _looks_like_a_utility(t):
                    continue
                if t in defined or t.split(":")[-1].lstrip("!") in defined:
                    continue
                orphans.setdefault(t, set()).add(os.path.basename(p))
    assert not orphans, (
        "%d utility classes in the markup have no rule in any stylesheet - "
        "either the class name is wrong or the build is stale:\n%s"
        % (len(orphans), "\n".join(
            "  %-32s %s" % (c, ", ".join(sorted(f)))
            for c, f in sorted(orphans.items()))))
