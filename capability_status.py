"""One source of truth for what is real.

Every public surface — homepage, product tour, product pages, partner
page, privacy language — reads its status from here. Before this, the
same capability could read Live on one page and Integration ready on
another, and nothing failed when they disagreed.

Six statuses and no others:

    LIVE                  working in the product today
    EXAMPLE               a worked example, nobody's real data
    PARTNER_DELIVERED     performed by a named partner, not by us
    INTEGRATION_READY     built here; the outside connection is not live
    COMING_SOON           not built yet
    REQUIRES_VERIFICATION a finding a person must check before it is acted on

The important part is `resolve()`. Some capabilities are only live when
credentials are actually present in the environment, and a hardcoded
"Live" on a marketing page is a claim that silently becomes false the
moment a key is missing. Those entries carry a `probe` instead of a fixed
status, so the page says what is true of the running deployment rather
than what was true when somebody wrote the copy.

Spotify pre-save is the case that forced this: the OAuth flow, token
storage and release-day save are all implemented, but every one of them
is gated on SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET. With those unset
the feature falls back to notify-me, and any page claiming Live is wrong.
"""
import os

LIVE = "live"
EXAMPLE = "example"
PARTNER_DELIVERED = "partner"
INTEGRATION_READY = "integration-ready"
COMING_SOON = "coming-soon"
REQUIRES_VERIFICATION = "verify"

LABELS = {
    LIVE: "Live",
    EXAMPLE: "Example",
    PARTNER_DELIVERED: "Partner delivered",
    INTEGRATION_READY: "Integration ready",
    COMING_SOON: "Coming soon",
    REQUIRES_VERIFICATION: "Requires verification",
}

MEANINGS = {
    LIVE: "Working in the product today.",
    EXAMPLE: "A worked example, not an artist's data.",
    PARTNER_DELIVERED: "Carried out through a named partner.",
    INTEGRATION_READY: "Built here; the outside connection is not live.",
    COMING_SOON: "Not built yet.",
    REQUIRES_VERIFICATION: "A finding a person must check before it is acted on.",
}


def _env(*names):
    """True only when every named variable is present and non-empty."""
    return all(os.environ.get(n) for n in names)


def _spotify_presave():
    return _env("SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET")


def _email_delivery():
    return _env("RESEND_API_KEY")


def _billing():
    return _env("STRIPE_SECRET_KEY")


def _remix_lab():
    """The Remix Lab engine reads a track for tempo, section boundaries and an
    energy curve. Both flags, because audio_policy.gate() checks both - the
    umbrella alone leaves the feature refusing."""
    return _env("AUDIO_INTELLIGENCE_ENABLED", "REMIX_LAB_AUDIO_ENGINE_ENABLED")


def _press_sending():
    """Stricter than the fan-email probe on purpose. A provider key alone
    leaves the shared test sender in place, and that one delivers only to
    the account owner's own inbox - so a press pitch would report success
    and reach no journalist. Both must be set before this claims Live."""
    return _env("RESEND_API_KEY", "EMAIL_FROM")


# Capability -> fixed status, or a probe that decides at request time.
#
# `probe` entries take the first status when the probe passes and the
# second when it does not. That is the whole mechanism: a missing key
# demotes the claim instead of leaving a false one on the page.
CAPABILITIES = {
    # --- the artist's own workspace ---
    "artist_eq": {"status": LIVE, "name": "Artist EQ"},
    "starting_plan": {"status": LIVE, "name": "Starting plan"},
    "metadata_passport": {"status": LIVE, "name": "Metadata Passport"},
    "rights_ownership": {"status": LIVE, "name": "Rights & Ownership"},
    "creative_studio": {"status": LIVE, "name": "Creative Studio"},
    "artwork_generator": {"status": LIVE, "name": "Artwork generator"},
    "smart_links": {"status": LIVE, "name": "Smart Links"},
    "email_capture": {"status": LIVE, "name": "Email capture with consent"},
    "rollout_plans": {"status": LIVE, "name": "Rollout plans"},
    "press_desk": {"status": LIVE, "name": "Press Desk"},
    "lanes": {"status": LIVE, "name": "Three Street Banker Lanes"},
    # TOUR. The module is live end to end on your own data. Two parts are
    # deliberately labelled for what they are: the advance-inbox extractor
    # is pattern-based (no language model on this deployment) and always
    # routes through a review step; the route view orders the run and
    # computes straight-line distances from coordinates you entered, with
    # no map tiles or drive-time provider connected.
    "tour_os": {"status": LIVE, "name": "TOUR (tour operating system)"},
    "tour_extraction": {"status": LIVE,
                        "name": "Advance inbox extraction (rule-based, reviewed before it writes)"},
    "tour_offline": {"status": LIVE,
                     "name": "My Day and Show Command readable offline after a visit"},
    "tour_map": {"status": INTEGRATION_READY,
                 "name": "Route map with drive times",
                 "note": ("Route order, gaps and straight-line distances are live; "
                          "map tiles and drive-time estimates need a provider.")},

    # --- things that depend on the environment ---
    "spotify_presave": {
        "name": "Spotify pre-save",
        "probe": _spotify_presave,
        "when_true": LIVE,
        "when_false": INTEGRATION_READY,
        "note_true": ("Fans authorize Spotify directly. The token is "
                      "encrypted at rest and deleted once the release-day "
                      "save completes."),
        "note_false": ("The flow is built and not connected on this "
                       "deployment. Pre-save buttons collect a notify-me "
                       "instead, and no Spotify token is requested, stored "
                       "or processed."),
    },
    "release_emails": {
        "name": "Release-day email",
        "probe": _email_delivery,
        "when_true": LIVE,
        "when_false": INTEGRATION_READY,
        "note_true": "Consented fans are emailed the listen link on release day.",
        "note_false": "Built, and no email provider is connected on this deployment.",
    },
    "press_sending": {
        "name": "Sending press pitches from Street Banker",
        "probe": _press_sending,
        "when_true": LIVE,
        "when_false": INTEGRATION_READY,
        "note_true": ("Each contact is emailed separately from the "
                      "configured sending domain."),
        "note_false": ("Built, and no sending domain is configured on this "
                       "deployment. The Press Desk prepares every message "
                       "and refuses to send rather than report a delivery "
                       "that did not happen."),
    },
    "billing": {
        "name": "Subscriptions and billing",
        "probe": _billing,
        "when_true": LIVE,
        "when_false": COMING_SOON,
        "note_true": "Checkout and plan changes run through Stripe.",
        "note_false": "No payment provider is connected on this deployment.",
    },

    # --- somebody else performs these ---
    "distribution_delivery": {
        "status": PARTNER_DELIVERED, "name": "Delivery to platforms",
        "note": ("Street Banker assembles and validates the package; "
                 "delivery goes out through the distribution partnership."),
    },

    # --- built here, outside connection not live ---
    "social_publishing": {"status": INTEGRATION_READY,
                          "name": "Social publishing"},
    "streaming_destinations": {"status": INTEGRATION_READY,
                               "name": "Streaming destination links"},
    "geographic_response": {"status": INTEGRATION_READY,
                            "name": "Geographic response"},
    "conversion_events": {"status": INTEGRATION_READY,
                          "name": "Conversion events"},

    # --- not built ---
    "sms_capture": {"status": COMING_SOON, "name": "SMS capture"},
    # Real since smart links shipped: /links/<cid>/qr.svg renders a segno QR
    # pointing at the campaign with ?src=qr, and every scan writes a qr_scan
    # row to ml_events. No external dependency, so no probe - it either
    # generates or the request fails.
    "qr_codes": {"status": LIVE, "name": "QR codes",
                 "note": ("Every smart link has a QR. Scans arrive tagged, so "
                          "they are counted separately from ordinary visits.")},
    "motion_assets": {"status": COMING_SOON, "name": "Motion and video assets"},
    "print_separations": {"status": COMING_SOON, "name": "Print-ready separations"},
    "release_signal": {"status": COMING_SOON, "name": "Release Signal"},
    "remix_lab": {
        "name": "Remix Lab generation",
        "probe": _remix_lab,
        "when_true": LIVE,
        "when_false": COMING_SOON,
        "note_true": ("A track is read for tempo, section boundaries and an "
                      "energy curve, and the brief is composed from those "
                      "measurements plus the choices made on the page. Every "
                      "line is marked measured, convention or chosen. It does "
                      "not detect key and makes no musical judgement."),
        "note_false": ("The brief builder, rights gate and likeness screen "
                       "are built; the engine is not switched on for this "
                       "deployment, and the page shows a worked example "
                       "labelled as one."),
    },

    # --- never asserted without a person ---
    "royalty_finding": {"status": REQUIRES_VERIFICATION,
                        "name": "Royalty Sweep finding"},

    # --- worked examples ---
    "artist_twin_reading": {"status": EXAMPLE, "name": "Artist Twin assessment"},
    "fan_intelligence": {"status": EXAMPLE, "name": "Fan Intelligence"},
}


def resolve(key):
    """The status of one capability on the running deployment."""
    spec = CAPABILITIES[key]
    if "probe" in spec:
        ok = spec["probe"]()
        status = spec["when_true"] if ok else spec["when_false"]
        note = spec.get("note_true" if ok else "note_false")
    else:
        status = spec["status"]
        note = spec.get("note")
    return {"key": key, "name": spec["name"], "status": status,
            "label": LABELS[status], "meaning": MEANINGS[status], "note": note}


def label(key):
    return resolve(key)["label"]


def status(key):
    return resolve(key)["status"]


def is_live(key):
    return status(key) == LIVE


def all_statuses():
    """Every capability, for the product tour and the audit documents."""
    return [resolve(k) for k in CAPABILITIES]


def get_status_config():
    return {"labels": LABELS, "meanings": MEANINGS,
            "capabilities": {k: resolve(k) for k in CAPABILITIES}}
