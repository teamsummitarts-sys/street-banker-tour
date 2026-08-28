"""Fingerprint monitoring — the slot, built dark.

Real detection of a beat being used somewhere means audio fingerprinting
against a vendor's index: ACRCloud, Audible Magic, Pex. All three are
paid, all three need an account this project does not have, and none of
them can be faked into existence. So this is the same pattern as Stripe,
Spotify and Shopify: an env-gated provider that says plainly it is off,
and that the producers desk asks before claiming anything.

    ACRCLOUD_HOST           identify-eu-west-1.acrcloud.com
    ACRCLOUD_ACCESS_KEY     project access key
    ACRCLOUD_ACCESS_SECRET  project secret

When those exist, matches would arrive as usage cases with
`found_via='fingerprint'` beside the ones a human logged - the case desk
already stores that distinction, so the day it turns on nothing about
the page has to change.

Until then `configured()` is False and the desk says: nothing here
scans, and a use appears only when somebody logs it.
"""

import os


def configured():
    return bool(os.environ.get("ACRCLOUD_HOST")
                and os.environ.get("ACRCLOUD_ACCESS_KEY")
                and os.environ.get("ACRCLOUD_ACCESS_SECRET"))


def status():
    """What the producers desk tells the truth with."""
    if configured():
        return {
            "on": True,
            "headline": "Fingerprint monitoring is connected",
            "detail": "Matches arrive as usage cases marked 'fingerprint' "
                      "beside the ones you log by hand.",
        }
    return {
        "on": False,
        "headline": "Nothing here scans for you",
        "detail": "This desk does not listen to audio or crawl platforms, "
                  "and no part of it is Content ID - that is YouTube's, and "
                  "it is granted to rights administrators, not applied for. "
                  "A use appears here when somebody logs it. Connecting a "
                  "fingerprinting vendor (ACRCloud, Audible Magic, Pex) is "
                  "what would change that, and it is a paid account.",
    }
