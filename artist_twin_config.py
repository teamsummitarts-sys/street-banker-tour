"""Section 5 — the AI Artist Twin.

An example assessment, labelled as one. Every row says what was looked
at, why it matters, how sure it is and what is missing, because a reader
who cannot see the reasoning has no way to judge whether to trust it.

Nothing here forecasts. There is no hit probability, no percentage, no
projected revenue: the confidence scale is three words and the language
is "review", "test", "compare". The Twin is a second opinion with its
working shown, not an oracle.
"""

EYEBROW = "AI Artist Twin"
HEADLINE = ["Know the artist.", "Test the move."]
SUPPORT = ("The Artist Twin learns your music, visuals, audience, catalog and "
           "goals—then helps evaluate releases, artwork, campaigns and "
           "opportunities before you commit.")
EXAMPLE_LABEL = "Example Artist Twin assessment"
MICROCOPY = ("Your Artist Twin supports your decisions. It does not replace "
             "your judgement.")

# Line icons, drawn as stroke paths so there is no icon dependency and
# nothing to load. Split on the pipe.
_ICONS = {
    "release": "M4 9v2|M8 6.5v7|M12 4.5v11|M16 8v4",
    "brand": ("M10 3.2a6.8 6.8 0 1 0 0 13.6a6.8 6.8 0 1 0 0-13.6|"
              "M10 7.6a2.4 2.4 0 1 0 0 4.8a2.4 2.4 0 1 0 0-4.8"),
    "artwork": "M3.6 4.6h12.8v10.8H3.6z|M3.6 12.2l3.4-3.3 2.9 2.9 3-2.5 3.5 3.4",
    "audience": ("M7.4 9.1a2.4 2.4 0 1 0 0-4.8a2.4 2.4 0 1 0 0 4.8|"
                 "M3.1 16c0-2.2 1.9-3.9 4.3-3.9s4.3 1.7 4.3 3.9|"
                 "M13.2 8.6a1.9 1.9 0 1 0 0-3.8|M13.6 12.4c1.9.4 3.3 1.9 3.3 3.6"),
    "next": "M6.2 13.8L13.8 6.2|M8.6 6.2h5.2v5.2",
}

# One shape, five rows. Everything the panel and its detail area show
# comes from here - there is no second copy of this in the template.
ASSESSMENT = [
    {
        "id": "release-readiness",
        "title": "Release Readiness",
        "summary": ("Strong foundation. Review sequencing, metadata and final "
                    "delivery requirements."),
        "status": "Good",
        "tone": "good",
        "confidence": "Strong",
        "observation": ("Masters, artwork and credits are present for every track, "
                        "and the release date leaves room for a normal delivery "
                        "window. Two tracks are still missing songwriter splits."),
        "why": ("Stores reject or hold deliveries on missing metadata, and unsigned "
                "splits are the most common reason royalties sit unclaimed later."),
        "missing": "Signed splits on two tracks; final track order.",
        "action": ("Complete the metadata passport, then lock the sequence before "
                   "delivery."),
        "icon": _ICONS["release"],
    },
    {
        "id": "brand-alignment",
        "title": "Brand Alignment",
        "summary": ("The visual direction and campaign language consistently "
                    "reflect the artist identity."),
        "status": "Strong",
        "tone": "strong",
        "confidence": "Strong",
        "observation": ("Artwork, press copy and the last three campaigns use the "
                        "same vocabulary and the same restrained palette. Nothing "
                        "in this release reads as borrowed from somewhere else."),
        "why": ("An audience recognises an artist before it reads a name. "
                "Consistency is what makes a catalog feel like one body of work."),
        "missing": "Nothing material.",
        "action": "Carry the same language into the release-week assets.",
        "icon": _ICONS["brand"],
    },
    {
        "id": "artwork-strength",
        "title": "Artwork Strength",
        "summary": ("The direction is cohesive. Test stronger thumbnail contrast "
                    "before approval."),
        "status": "Solid",
        "tone": "solid",
        "confidence": "Moderate",
        "observation": ("Artwork and campaign materials use a consistent visual "
                        "language, but the focal subject becomes difficult to read "
                        "at small streaming-thumbnail sizes."),
        "why": ("Most listeners first meet the artwork at a small scale on a "
                "phone."),
        "missing": "Final streaming-platform crop tests.",
        "action": ("Compare two higher-contrast thumbnail versions before final "
                   "approval."),
        "icon": _ICONS["artwork"],
    },
    {
        "id": "audience-fit",
        "title": "Audience Fit",
        "summary": ("The release aligns with the core audience and shows potential "
                    "in adjacent listener groups."),
        "status": "Good",
        "tone": "good",
        "confidence": "Moderate",
        "observation": ("The tempo range and features sit inside what the existing "
                        "audience already saves. Two adjacent scenes share playlist "
                        "neighbours but have never been targeted directly."),
        "why": ("Reaching an adjacent audience is cheaper than building a new one, "
                "and it is easier to judge before a campaign than after it."),
        "missing": "Recent audience geography; current playlist placements.",
        "action": "Pick one adjacent scene and test it with a single asset.",
        "icon": _ICONS["audience"],
    },
    {
        "id": "next-move",
        "title": "Recommended Next Move",
        "summary": ("Compare the strongest artwork direction, finalise the rollout "
                    "and run a preliminary Royalty Sweep."),
        "status": "Suggested",
        "tone": "suggested",
        "confidence": "Moderate",
        "observation": ("The two open items on this release - artwork contrast and "
                        "the missing splits - are both cheap to close now and "
                        "expensive to fix after release."),
        "why": ("Sequence matters more than speed: artwork and splits are decided "
                "once, and everything downstream inherits them."),
        "missing": "Your decision on the artwork direction.",
        "action": ("Pick the artwork, close the splits, then build the rollout "
                   "around the confirmed date."),
        "icon": _ICONS["next"],
    },
]

# What the Twin reads from. States are honest about an example account:
# a real one would show what that artist has actually connected.
INPUT_SOURCES = [
    {"name": "Music", "state": "Connected"},
    {"name": "Visuals", "state": "Added"},
    {"name": "Audience", "state": "Connected"},
    {"name": "Catalog", "state": "Connected"},
    {"name": "Campaign History", "state": "Added"},
    {"name": "Goals", "state": "Needs Input"},
]

PRIMARY_CTA = {"label": "Build my Artist Twin", "href": "/artist-twin/start"}
SECONDARY_CTA = {"label": "See how it thinks"}
TRUST_LINK = {"label": "How Street Banker uses AI", "href": "/ai"}

IMAGE = {
    "stem": "/static/img/artist-twin",
    "widths": [480, 700, 893],
    "width": 893,
    "height": 941,
    "alt": ("Artist reviewing release photographs and campaign materials while "
            "team members move through a creative studio."),
}

# The public start flow: a visitor picks what they are working on and
# gets the route Street Banker would take, before any account exists.
GOALS = [
    {
        "id": "release",
        "label": "Preparing a release",
        "route": ["Complete the metadata passport for every track",
                  "Lock the sequence and the delivery date",
                  "Build the rollout backwards from release day"],
        "reads": "Masters, credits, artwork, release date",
    },
    {
        "id": "artwork",
        "label": "Improving artwork",
        "route": ["Compare directions at thumbnail size, not full size",
                  "Test contrast against a dark and a light interface",
                  "Keep the chosen direction across every campaign asset"],
        "reads": "Artwork, campaign visuals, brand direction",
    },
    {
        "id": "rollout",
        "label": "Building a rollout",
        "route": ["Fix the release date first, then work backwards",
                  "Decide the three assets that carry the campaign",
                  "Leave the last week for the things that always slip"],
        "reads": "Release plan, past campaigns, audience activity",
    },
    {
        "id": "audience",
        "label": "Growing an audience",
        "route": ["Read where the existing audience already listens",
                  "Pick one adjacent scene rather than five",
                  "Capture the fans you reach instead of renting them"],
        "reads": "Streaming performance, geography, fan behaviour",
    },
    {
        "id": "rights",
        "label": "Reviewing rights",
        "route": ["List every track with an unsigned split",
                  "Register works and recordings where they are missing",
                  "Keep one file per track that a lawyer could read"],
        "reads": "Catalog, splits, registrations, agreements",
    },
    {
        "id": "royalties",
        "label": "Checking royalty opportunities",
        "route": ["Upload the statements you already receive",
                  "Compare what each source reports against your catalog",
                  "Chase the gaps that have a paper trail"],
        "reads": "Royalty statements, catalog, distribution history",
    },
]

# The trust page. Short on purpose: five statements a person can hold in
# their head, not a policy document.
TRUST_POINTS = [
    ("Your catalog stays yours.",
     "Uploading music, artwork or statements to Street Banker does not transfer "
     "any right in them. You can remove an input and the Twin stops reading it."),
    ("Your work is not training data.",
     "Your music and images are not used to train models without your explicit, "
     "separate permission. Turning that permission on is a choice you make, not "
     "a default you have to find and switch off."),
    ("The recommendations are estimates.",
     "The Artist Twin reads what you have given it and reasons out loud about it. "
     "It does not predict a hit, a signing or a sum of money, and where it is "
     "unsure it says so."),
    ("Nothing is published without you.",
     "The Twin can prepare a release, a rollout or a claim. Sending any of it "
     "outward - to a store, a platform or a partner - takes your approval."),
    ("You can change your mind.",
     "Every input can be updated or deleted, and the assessment is rebuilt from "
     "whatever is there at the time."),
]


def get_artist_twin_config():
    return {
        "eyebrow": EYEBROW,
        "headline": HEADLINE,
        "support": SUPPORT,
        "example_label": EXAMPLE_LABEL,
        "microcopy": MICROCOPY,
        "assessment": ASSESSMENT,
        "sources": INPUT_SOURCES,
        "primary_cta": PRIMARY_CTA,
        "secondary_cta": SECONDARY_CTA,
        "trust_link": TRUST_LINK,
        "image": IMAGE,
        "goals": GOALS,
    }
