"""Section 12 — the closing statement, and the trust band above it.

The last frame: an empty room, one road case, the catalog on the floor.
The photograph carries the argument; the copy says the two sentences and
stops. No feature list, no figures, no recap.

The trust band that sits above it is four columns of text - what the
artist keeps, what happens to their data, what the Twin will and will not
claim, and what a royalty finding is worth before somebody checks it.
Every one of those is a promise made elsewhere on this homepage, gathered
in one place where it can be read at a glance.
"""

EYEBROW = "Street Banker"
NUMBER = "12"
HEADLINE = [("Your music is the ", "product."), ("Your catalog is the ", "asset.")]
SUPPORT = ("Street Banker helps artists build, protect, distribute, promote "
           "and grow the work from one connected system.")
TRUST_LINE = "Your music. Your data. Your decisions."

PRIMARY_CTA = {"label": "Build my Street Banker", "href": "/start"}
SECONDARY_CTA = {"label": "Explore the platform", "href": "/product-tour"}

IMAGE = {
    "wide": {"stem": "/static/img/closing-wide", "widths": [960, 1440, 1672],
             "width": 1672, "height": 941},
    "close": {"stem": "/static/img/closing-close", "widths": [520, 1070],
              "width": 1070, "height": 781},
    "alt": ("Worn touring road case inside an empty venue with records, tapes "
            "and hard drives creating a trail toward the stage."),
}

# --- the compact trust band (11.5) ---------------------------------------
BAND_TITLE = "Built for artist control."
BAND_LINK = {"label": "Read our artist control policy", "href": "/artist-control"}

BAND = [
    ("You own the work",
     "Your masters, catalog, creative assets and release information remain "
     "under your control according to your agreement."),
    ("Your data stays yours",
     "Artist data is not sold, and music or imagery is not used for AI "
     "training without explicit permission."),
    ("AI explains its reasoning",
     "Artist Twin recommendations show observations, confidence, missing "
     "inputs and recommended actions — not guaranteed outcomes."),
    ("Royalty findings are verified",
     "Royalty Sweep identifies potential gaps and organises recovery cases. "
     "Findings require evidence and verification before submission."),
]

# The public policy page behind the band.
POLICY = [
    ("Data ownership",
     "Uploading music, artwork, statements or catalog information to Street "
     "Banker transfers no right in any of it. The work is yours; the account "
     "is where it is organised."),
    ("AI training consent",
     "Your music and images are not used to train models without your "
     "explicit, separate permission. It is a choice you make, not a default "
     "you have to find and switch off."),
    ("Uploaded music and images",
     "Files are stored against your account and used to produce your own "
     "findings, previews and deliverables. They are not sold and not shared "
     "outside the work you asked for."),
    ("What a recommendation is",
     "Every Artist Twin reading shows what it looked at, how sure it is and "
     "what it is missing. It does not predict a hit, a signing or a sum of "
     "money, and it does not replace your judgement."),
    ("Royalty verification",
     "A finding is a question with evidence attached. It requires "
     "verification before anything is submitted anywhere, and the estimate "
     "attached to it is arithmetic on your own statements rather than a "
     "prediction."),
    ("Automated publishing",
     "Nothing leaves the workspace without your approval. Street Banker "
     "prepares releases, campaigns, registrations and claims; sending them "
     "outward is your action or one you authorise."),
    ("Deleting your data",
     "Remove an upload and the findings drawn from it go with it. Close the "
     "account and the record goes with that."),
    ("Export",
     "The catalog record is structured to be portable: export it and take it "
     "somewhere else. The design goal is that leaving is possible, not "
     "expensive."),
    ("Collaborator permissions",
     "Access is per release and per role. Somebody invited to confirm a split "
     "sees that release and nothing else in the catalog."),
    ("Audit history",
     "Changes are recorded with a date and an author. Nothing is overwritten "
     "silently, which is what makes the record worth anything in a dispute."),
]


def get_closing_config():
    return {
        "number": NUMBER,
        "eyebrow": EYEBROW,
        "headline": HEADLINE,
        "support": SUPPORT,
        "trust_line": TRUST_LINE,
        "primary_cta": PRIMARY_CTA,
        "secondary_cta": SECONDARY_CTA,
        "image": IMAGE,
        "band_title": BAND_TITLE,
        "band": BAND,
        "band_link": BAND_LINK,
    }
