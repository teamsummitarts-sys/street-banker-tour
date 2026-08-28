"""Section 7 — Creative Studio.

A backstage photograph and four words along the bottom edge. The picture
carries the section; the interface stays out of its way.

The capability list on the public tour is grouped by what is actually
true: what is in the app today, what is guided rather than automatic, and
what is not built. An artist deciding whether to hand over a release
needs that distinction more than another feature grid.
"""

EYEBROW = "Creative Studio"
NUMBER = "07"
# Two lines, set here rather than left to the wrap: the site face is
# not condensed, so "visual world." decides its own break otherwise
# and leaves "the" stranded.
HEADLINE = ["Build the", "Visual world."]
SUPPORT = ("Artwork, merch, campaign assets, and release content built around "
           "one clear artist identity.")

PRIMARY_CTA = {"label": "Open Creative Studio", "href": "/creative-studio"}
SECONDARY_CTA = {"label": "See the workflow"}

FEATURES = [
    {"id": "cover-art", "label": "Cover Art",
     "line": "Build the visual identity of the release."},
    {"id": "merch", "label": "Merch",
     "line": "Turn the campaign into wearable and collectible objects."},
    {"id": "campaign-assets", "label": "Campaign Assets",
     "line": "Create teasers, posters, social content, and launch materials."},
    {"id": "platform-formats", "label": "Platform Formats",
     "line": "Adapt approved creative for every required channel and dimension."},
]

WORKFLOW = [
    ("Brief", "The artist provides the release story, references, goals and "
              "available assets."),
    ("Directions", "Street Banker develops several coherent creative "
                   "directions."),
    ("Refine", "The artist reviews and requests targeted revisions."),
    ("Approve", "One visual direction becomes the campaign master."),
    ("Adapt", "The approved direction is converted into platform, merchandise, "
              "social, video and promotional formats."),
]

MEMORY_TITLE = "Built around your identity."
MEMORY_COPY = ("Creative Studio remembers approved visual directions, colours, "
               "logos, imagery and rejected styles so every release still feels "
               "like the same artist.")

IMAGE = {
    "wide": {"stem": "/static/img/creative-wide", "widths": [520, 830],
             "width": 830, "height": 980},
    "close": {"stem": "/static/img/creative-close", "widths": [400, 600],
              "width": 600, "height": 520},
    "alt": ("Touring artist and crew setting up a merchandise table backstage "
            "inside a small music venue."),
}

# The public tour, grouped by what is true rather than by feature.
CAPABILITIES = [
    ("In the app today", [
        ("Cover Studio", "Write the brief, get cover directions back, remix one, "
                         "set the title and artist type, and save the result to "
                         "your uploads."),
        ("Brand kit", "Save the colours, logo and type once and apply them across "
                      "covers so the next release matches the last one."),
        ("Format previews", "See an approved cover at the sizes the stores and "
                            "social platforms ask for."),
        ("Apparel and merch", "Put a direction on real garment mock-ups before "
                              "committing to a print run."),
        ("Rollout Engine", "The campaign the assets hang off: what goes out, "
                           "when, and in what order."),
        ("Smart links and EPK", "Where the approved artwork ends up in front of "
                                "somebody."),
    ]),
    ("Guided, not automatic", [
        ("Your brief, your call", "Directions come from what you write and what "
                                  "you reference. You choose one, ask for "
                                  "changes, and approve it - nothing is picked "
                                  "for you."),
        ("Editable outputs", "Everything saved is a file you own and can take "
                             "somewhere else."),
        ("Nothing published without you", "Sending artwork outward - to a store, "
                                          "a platform or a printer - takes your "
                                          "approval."),
    ]),
    ("Not built yet", [
        ("Motion and video assets", "Nothing here makes video. It is on the list; "
                                    "it is not in the app."),
        ("Print-ready separations", "Merch mock-ups are for deciding, not for "
                                    "handing to a printer."),
        ("Direct printer hand-off", "You take the approved files to your own "
                                    "supplier."),
    ]),
]


def get_creative_config():
    return {
        "number": NUMBER,
        "eyebrow": EYEBROW,
        "headline": HEADLINE,
        "support": SUPPORT,
        "primary_cta": PRIMARY_CTA,
        "secondary_cta": SECONDARY_CTA,
        "features": FEATURES,
        "workflow": WORKFLOW,
        "memory_title": MEMORY_TITLE,
        "memory_copy": MEMORY_COPY,
        "image": IMAGE,
        "capabilities": CAPABILITIES,
    }
