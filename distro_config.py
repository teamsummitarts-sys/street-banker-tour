"""Section 10 — Global Distribution.

Every claim here was checked against the app and against the business
terms already published on /services/distribution before it was written.

What is true: releases are prepared and validated inside Street Banker -
the Metadata Passport, the Clean Release checklist and the Release
Scheduler are real and in the app - and delivery goes out through
SummitArts on Symphonic Distribution, which is the partnership the
services page already states. The partner's own published terms are the
source for the platform count and the set-up fees, and they are
attributed rather than claimed as Street Banker's.

What the reference image claimed and this does not: 200+ countries (the
partner says platforms, not countries), every major platform, keep 100%,
real-time reports, no hidden fees, free to get started, no credit card
required, cancel anytime. None of those is supported by anything in this
codebase or in the terms on file, so none of them is on the page.
"""

EYEBROW = "Global Distribution"
NUMBER = "10"
HEADLINE = ["Your music. Everywhere.", "On your terms."]
SUPPORT = ("Prepare and deliver your release to supported platforms while "
           "keeping control of your masters, metadata, timing, territories "
           "and release information.")
TRUST = "Your masters. Your metadata. Your release plan."

# Two buttons need two destinations. Both pointed at /distribution,
# which made the primary CTA a no-op next to the guide button. The
# release checklist that used to be printed on the homepage lives at
# /release-check, where it can actually be ticked - so that is what
# "Distribute now" opens.
PRIMARY_CTA = {"label": "Distribute now", "href": "/release-check"}
GUIDE_CTA = {"label": "View distribution guide", "href": "/distribution#guide"}

# "copy" would resolve to dict.copy in a Jinja attribute lookup and print
# the bound method, so the key is named for what it is.

# The partner, named, because "supported platforms" means nothing without
# saying who supports them.
PARTNER = {
    "name": "SummitArts on Symphonic Distribution",
    "line": ("Street Banker prepares and validates the release. Delivery to "
             "stores and streaming platforms goes out through SummitArts on "
             "Symphonic Distribution — the partnership on the services page."),
}

CAPABILITIES = [
    ("01", "Platform Delivery",
     "Prepare and deliver releases to supported streaming platforms and "
     "digital stores through the Street Banker distribution partnership."),
    ("02", "Ownership Control",
     "Keep ownership and control of masters and catalog information according "
     "to your agreement and the Street Banker lane you are on."),
    ("03", "Release Control",
     "Manage release dates, territories, versions, metadata, credits, artwork "
     "and delivery status from one release workspace."),
    ("04", "Reporting",
     "Organise available performance reports, royalty statements, delivery "
     "updates and release activity in one place."),
    ("05", "Splits and Credits",
     "Confirm contributors, ownership splits, identifiers, performer roles, "
     "publishing information and required release credits."),
]

WORKFLOW = [
    ("Prepare", "Add audio, artwork, metadata, contributors, ownership "
                "details, territories and release timing."),
    ("Validate", "Check required fields, audio specifications, artwork "
                 "dimensions, metadata consistency, rights confirmation and "
                 "delivery readiness."),
    ("Deliver", "Submit the approved package to the distribution partner for "
                "delivery to supported platforms."),
    ("Monitor", "Track delivery status, platform availability, processing "
                "issues and available reporting."),
    ("Maintain", "Manage corrections, updated metadata, new versions, "
                 "territory changes, takedowns and catalog history."),
]

# The example package. Grouped the way a release actually gets assembled.
CHECKLIST = [
    ("Audio", ["Final audio master", "Clean version, when needed",
               "Instrumental, when needed"]),
    ("Artwork", ["Cover artwork"]),
    ("Names and titles", ["Artist and release names", "Track titles",
                          "Featured artists"]),
    ("Credits", ["Producer and contributor credits", "Songwriter information",
                 "Publishing information"]),
    ("Rights", ["Ownership splits", "Copyright information",
                "Rights confirmation"]),
    ("Identifiers", ["ISRC information", "UPC information"]),
    ("Release settings", ["Explicit-content status", "Release date",
                          "Territories"]),
    ("Extras", ["Lyrics", "Platform links or artist profiles", "Final review"]),
]

# Completion only. Never performance.
READINESS = ["Setup Incomplete", "Needs Information", "Ready for Review",
             "Delivery Ready"]

# Only what is true. Nothing here implies a direct Street Banker
# integration with a platform, because there is not one.
INTEGRATIONS = [
    ("Streaming platforms and digital stores", "Delivered through partner"),
    ("Physical: CD and vinyl", "Delivered through partner"),
    ("Music video", "Delivered through partner"),
    ("UGC and Content ID", "Delivered through partner"),
    ("Royalty statements you upload", "Supported"),
    ("Metadata, identifiers and splits", "Supported"),
    ("Release scheduling and lead-time checks", "Supported"),
    ("Direct platform connections from Street Banker", "Coming soon"),
]

IMAGE = {
    "wide": {"stem": "/static/img/distro-wide", "widths": [760, 1180, 1402],
             "width": 1402, "height": 462},
    "close": {"stem": "/static/img/distro-close", "widths": [480, 740],
              "width": 740, "height": 422},
    "alt": ("Road cases and release materials arranged around a release "
            "passport, audio masters, stems drive, cables and release "
            "checklist."),
}

# The public guide.
GUIDE = [
    ("Audio", "A final master per track, in the highest quality you have. "
              "Keep a clean version and an instrumental where the release "
              "needs one - they are separate deliverables, not edits made "
              "later."),
    ("Artwork", "Square cover art at the largest size you have, with no "
                "store logos, no URLs and no text the platforms reject. "
                "Check it at thumbnail size before approving it."),
    ("Metadata", "Artist and release names spelled the way they will appear "
                 "everywhere else, track titles, version names in brackets, "
                 "and featured artists in the artist field rather than the "
                 "title."),
    ("Credits", "Producers, writers, performers and their roles. The "
                "Metadata Passport in the app holds these against the track "
                "so the next release starts from them."),
    ("Ownership", "Splits that add up, confirmed by the people they name. "
                  "This is the single most common reason money sits "
                  "uncollected later."),
    ("ISRC and UPC", "Bring your own or have them assigned at delivery. Once "
                     "a recording has an ISRC it keeps it - a new one on a "
                     "re-release splits the history in two."),
    ("Release date", "Pick it early and work backwards. Playlist "
                     "consideration and store processing both need lead time, "
                     "and the Release Scheduler warns when there is not "
                     "enough."),
    ("Territories", "Worldwide unless there is a reason not to be. A "
                    "territory restriction is easy to set and easy to forget."),
    ("Delivery timelines", "Delivery is a queue, not a switch. Allow time "
                           "between approval and the date you want it live; "
                           "the partner's processing window sits inside that."),
    ("Changes after delivery", "Metadata corrections and artwork changes are "
                               "possible after release and take time to "
                               "propagate. Audio replacements are not routine "
                               "- get the master right first."),
    ("Reporting", "Statements arrive from the partner on their own schedule. "
                  "Street Banker organises what you upload or receive; it "
                  "does not read a platform directly."),
    ("Takedowns and updates", "A takedown removes availability, not history. "
                              "Plan it as a release step of its own rather "
                              "than an afterthought."),
]


def get_distro_config():
    return {
        "number": NUMBER,
        "eyebrow": EYEBROW,
        "headline": HEADLINE,
        "support": SUPPORT,
        "trust": TRUST,
        "primary_cta": PRIMARY_CTA,
        "guide_cta": GUIDE_CTA,
        "partner": PARTNER,
        "capabilities": CAPABILITIES,
        "workflow": WORKFLOW,
        "checklist": CHECKLIST,
        "readiness": READINESS,
        "image": IMAGE,
    }
