"""Section 6 — the three Street Banker lanes.

One unit, three channels. The hardware carries the idea; the words carry
the meaning, and they live here rather than inside the photograph, so a
reader on a phone, a screen reader and a search engine all get the same
copy the picture is illustrating.

Nothing in this section is a price list. A lane is a level of support,
and the only claim made about any of them is what is in it.
"""

EYEBROW = "Three lanes. One system."
HEADLINE = ["Choose your lane.", "Build your career."]
SUPPORT = ("Street Banker meets artists where they are—whether they need "
           "release infrastructure, deeper development, or long-term "
           "strategic partnership.")

# Where each channel sits across the unit, measured off the asset. The
# overlays that light a lane on hover use these, so the highlight lands
# on the right channel at every width instead of on a guessed third.
SEAMS = [0.3370, 0.6553]

LANES = [
    {
        "num": "01",
        "slug": "distribution",
        "name": "Distribution",
        "subline": "Release the Record",
        "description": ("Get your music released with the core infrastructure: "
                        "delivery, release tools, metadata support, smart links "
                        "and launch essentials."),
        "includes": ["Delivery to the stores and services",
                     "Metadata and credits kept release-ready",
                     "Smart links and pre-save pages",
                     "Statements read and reported back to you"],
        "for_you_if": ("You have the record and you need it out, correctly and "
                       "on time."),
        "cta": "Explore Distribution",
    },
    {
        "num": "02",
        "slug": "development",
        "name": "Development",
        "subline": "Build the Artist",
        "description": ("Add deeper creative, strategic and growth support "
                        "through Artist Twin guidance, rollout planning, "
                        "audience development and artist-building tools."),
        "includes": ["Everything in Distribution",
                     "Artist Twin guidance on releases and artwork",
                     "Rollout planning built backwards from release day",
                     "Audience and fan development, read from your own data"],
        "for_you_if": ("The releases are landing and the next thing you need is "
                       "a plan around them."),
        "cta": "Explore Development",
    },
    {
        "num": "03",
        "slug": "partnership",
        "name": "Partnership",
        "subline": "Build the Asset",
        "description": ("For artists with momentum who are building long-term "
                        "value through catalog strategy, higher-touch support "
                        "and partnership-level opportunities."),
        "includes": ["Everything in Development",
                     "Catalog strategy and rights work",
                     "Higher-touch support on the decisions that compound",
                     "Partnership-level opportunities, case by case"],
        "for_you_if": ("There is a catalog behind you and the question is what "
                       "it is worth in five years."),
        "cta": "Explore Partnership",
    },
]

# The public matcher. Five situations, each pointing at one lane, and the
# page says why - a selector that will not explain itself is a quiz, not
# an answer.
SITUATIONS = [
    {"id": "first-release", "label": "Releasing my first music",
     "lane": "distribution",
     "why": ("The first thing to get right is the release itself: delivered "
             "clean, registered properly, and pointing somewhere.")},
    {"id": "growing", "label": "Actively growing an audience",
     "lane": "development",
     "why": ("Growth is a plan, not a post. Development is where the rollout "
             "and the audience work sit.")},
    {"id": "royalties", "label": "I need royalty help",
     "lane": "distribution",
     "why": ("Start by reading the statements you already have. That runs on "
             "the Distribution lane and does not need anything above it.")},
    {"id": "hands-on", "label": "I want hands-on development",
     "lane": "development",
     "why": ("Hands-on shaping of releases, artwork and campaigns is what "
             "Development is for.")},
    {"id": "catalog", "label": "Building long-term catalog value",
     "lane": "partnership",
     "why": ("Catalog value is a rights and strategy question, and it is worth "
             "the higher-touch lane.")},
]

IMAGE = {
    "stem": "/static/img/lanes-unit",
    "widths": [760, 1100, 1626],
    "width": 1626,
    "height": 892,
    "alt": ("Street Banker hardware-style unit with three channels representing "
            "Distribution, Development and Partnership."),
}

PRIMARY_CTA = {"label": "Find my lane", "href": "/lanes"}
SECONDARY_CTA = {"label": "Compare the lanes"}


def get_lanes_config():
    return {
        "eyebrow": EYEBROW,
        "headline": HEADLINE,
        "support": SUPPORT,
        "lanes": LANES,
        "seams": SEAMS,
        "image": IMAGE,
        "primary_cta": PRIMARY_CTA,
        "secondary_cta": SECONDARY_CTA,
        "situations": SITUATIONS,
    }
