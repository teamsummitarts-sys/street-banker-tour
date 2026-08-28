"""Sandbox mode — a deployed copy of the site that cannot reach anything real.

Set SANDBOX=1 on the throwaway deployment and nothing else. Every function
here is a no-op unless that variable is set, so production runs the exact
code path it ran before this file existed: `active()` returns False, the
provider gates fall through to their normal env checks, and the response
hook returns the response object untouched. That is the point — a safety
feature that changes the site it is protecting is not a safety feature.

What it switches off, and why those three:

    email      A sandbox holding a live Resend key could mail real
               journalists from the Press Desk during a test. There is no
               undo for a sent email.
    payments   A live Stripe key could charge a real card.
    R2         A live bucket key would write test junk into the same
               object store production reads from.

Each is switched off by making the provider's own `configured()` report
False, rather than by intercepting calls further down. The whole app
already knows how to behave with an unconfigured provider — it degrades,
says so on the page, and refuses to claim a delivery it did not make. So
sandbox mode reuses a path that is already tested instead of inventing a
second one that is not.

It does NOT switch off the database. The sandbox has its own, and on a
free instance that database is erased whenever the service restarts.
"""
import os
import re

_TRUE = ("1", "true", "yes", "on")


def active():
    return (os.environ.get("SANDBOX") or "").strip().lower() in _TRUE


def label():
    """What the strip calls this deployment. Lets a second or third
    sandbox name itself rather than all of them reading 'Sandbox'."""
    return (os.environ.get("SANDBOX_NAME") or "Sandbox").strip()[:40]


# Fixed to the bottom of the viewport and outside the document flow on
# purpose: a banner that pushes content down would change the very layout
# the sandbox exists to let somebody judge, and this site has sticky
# headers whose offsets are computed. Nothing here can move a pixel of
# the page it sits on.
_BAR = (
    '<div role="status" aria-label="Sandbox deployment" style="'
    'position:fixed;left:0;right:0;bottom:0;z-index:2147483647;'
    'background:#E05C4A;color:#F2ECE0;'
    'font:600 12px/1.45 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;'
    'letter-spacing:0.06em;text-align:center;padding:6px 12px;'
    'border-top:2px solid #E05C4A;pointer-events:none;'
    'text-transform:uppercase">'
    '%s — experiments only. Email, payments and file storage are off. '
    'Nothing here reaches the live site.'
    '</div>'
)

_TITLE = re.compile(r"<title>(.*?)</title>", re.S | re.I)


def mark(html):
    """Add the strip and prefix the tab title. Returns the input unchanged
    when there is nothing to mark, so the caller can skip set_data()."""
    if not active() or not html or "<body" not in html:
        return html
    out = html
    if "</body>" in out:
        out = out.replace("</body>", (_BAR % label()) + "</body>", 1)
    # The tab title matters as much as the strip: two identical-looking
    # tabs is exactly how somebody does real work in the sandbox, or
    # experiments on production believing it is the copy.
    out = _TITLE.sub(
        lambda m: "<title>[%s] %s</title>" % (label().upper(), m.group(1).strip()),
        out, count=1)
    return out
