"""Section 11 — Metadata Passport + Rights.

One release in the middle, seven connected records around it. The
photograph is a floor blueprint; every category name, description and
status on the page is markup, because the writing in the picture is set
dressing and a reader on a phone can see none of it.

The example passport is labelled an example everywhere it appears. The
health figure is completeness - fields filled, nothing more - and it is
named for that so it can never be read as a forecast.
"""

EYEBROW = "Metadata Passport + Rights"
NUMBER = "11"
HEADLINE = ["One release.", "Every detail connected."]
SUPPORT = ("Organise credits, splits, identifiers, ownership, agreements, "
           "assets, versions and release history in one living record.")
TRUST = "Your credits. Your rights. Your record."
TRUST_COPY = ("Street Banker organises the information. Artists and authorised "
              "collaborators control what is confirmed, shared or submitted.")

PRIMARY_CTA = {"label": "Open Metadata Passport", "href": "/metadata"}
SECONDARY_CTA = {"label": "See how it connects"}
TRUST_LINK = {"label": "How metadata is used", "href": "/metadata#used"}

EXAMPLE_LABEL = "Example metadata passport"

# Each zone is (left, top, right, bottom) as a fraction of the photograph,
# measured off the blueprint so a hotspot lands on its own area at every
# width rather than on a guessed rectangle.
CATEGORIES = [
    {
        "num": "01", "slug": "credits", "label": "Credits",
        "zone": (0.150, 0.105, 0.365, 0.325),
        "short": "Record every contributor and role attached to the release.",
        "stored": ["Primary artist", "Featured artist", "Songwriters",
                   "Producers", "Engineers", "Musicians", "Photographers",
                   "Designers", "Additional contributors"],
        "why": ("Credits are how a person gets paid and how they get found. A "
                "contributor with no role attached is invisible to every "
                "system downstream."),
        "status": "Needs Review",
        "missing": "Two performers are listed without a role.",
        "action": ("Assign a role to every contributor before the release is "
                   "confirmed."),
    },
    {
        "num": "02", "slug": "ownership", "label": "Ownership",
        "zone": (0.118, 0.335, 0.335, 0.545),
        "short": ("Document who controls the recording and composition, and "
                  "how ownership is divided."),
        "stored": ["Master owner", "Composition owners", "Publishing shares",
                   "Administration", "Territories", "Ownership percentages",
                   "Effective dates"],
        "why": ("Splits that do not add up are the most common reason money "
                "sits uncollected. Ownership is also the first thing anybody "
                "reviewing the catalog asks for."),
        "status": "Conflicts Detected",
        "missing": "Composition shares total 90%.",
        "action": ("Reconcile the composition split with the writers named in "
                   "Credits, then have it confirmed."),
    },
    {
        "num": "03", "slug": "identifiers", "label": "Identifiers",
        "zone": (0.058, 0.575, 0.312, 0.870),
        "short": ("Keep the identifiers that connect the release across "
                  "platforms, organisations and payment systems."),
        "stored": ["ISRC", "UPC or EAN", "ISWC", "IPI or CAE", "ISNI",
                   "Catalog number", "Internal release ID"],
        "why": ("Identifiers connect the release to platforms, registrations, "
                "statements and royalty sources. Incorrect or missing "
                "identifiers fragment reporting."),
        "status": "Needs Review",
        "missing": "ISWC and two contributor IPI numbers have not been added.",
        "action": ("Confirm the composition registration and complete "
                   "contributor identifiers before final delivery."),
    },
    {
        "num": "04", "slug": "versions", "label": "Versions",
        "zone": (0.383, 0.585, 0.612, 0.900),
        "short": "Track every approved version of the recording.",
        "stored": ["Original", "Clean", "Explicit", "Instrumental", "Acapella",
                   "Radio edit", "Extended", "Live", "Remix",
                   "Alternate master"],
        "why": ("Each version is its own recording with its own identifier. A "
                "version without a matching asset cannot be delivered, and a "
                "version delivered without its own ISRC splits the reporting."),
        "status": "Incomplete",
        "missing": "The clean version has no audio asset attached.",
        "action": "Attach the clean master or remove the version from the plan.",
    },
    {
        "num": "05", "slug": "agreements", "label": "Agreements",
        "zone": (0.618, 0.105, 0.882, 0.325),
        "short": ("Connect the documents that establish permissions, "
                  "obligations and chain of title."),
        "stored": ["Split sheets", "Producer agreements",
                   "Featured-artist agreements", "Work-for-hire agreements",
                   "Master-use licences", "Sample clearances",
                   "Publishing administration", "Distribution agreements"],
        "why": ("An agreement is what turns a claim into a right. Without the "
                "paperwork behind a split, the split is an intention."),
        "status": "Incomplete",
        "missing": "The split sheet has not been signed by one writer.",
        "action": "Send the split sheet for the outstanding signature.",
    },
    {
        "num": "06", "slug": "assets", "label": "Assets",
        "zone": (0.640, 0.335, 0.918, 0.560),
        "short": "Organise the media and files connected to the release.",
        "stored": ["Audio masters", "Stems", "Artwork", "Artist photography",
                   "Lyrics", "Videos", "Canvas clips", "Campaign files",
                   "Press materials", "Supporting documents"],
        "why": ("The files are the release. Keeping them against the record "
                "rather than in a folder somewhere is what makes a re-issue, "
                "a sync request or a transfer possible years later."),
        "status": "Ready for Confirmation",
        "missing": "Nothing outstanding.",
        "action": "Confirm the master and artwork as final.",
    },
    {
        "num": "07", "slug": "release-history", "label": "Release History",
        "zone": (0.648, 0.575, 0.932, 0.862),
        "short": "Preserve the complete timeline of the release.",
        "stored": ["Original release", "Metadata updates", "Artwork changes",
                   "New territories", "Clean version added", "Remix added",
                   "Deluxe version", "Distribution transfer",
                   "Rights corrections", "Catalog ownership updates"],
        "why": ("Catalog value is a paper trail. What changed, when and on "
                "whose authority is the difference between a catalog somebody "
                "can buy and one nobody can price."),
        "status": "Complete",
        "missing": "Nothing outstanding.",
        "action": "Keep recording changes as they happen.",
    },
]

# Completion only. Named for what it measures.
HEALTH_STATUSES = ["Incomplete", "Needs Review", "Conflicts Detected",
                   "Ready for Confirmation", "Complete", "Verified"]
HEALTH_LABEL = "Metadata completeness"
HEALTH_NOTE = ("Completeness counts the required fields that are filled in on "
               "this example. It is not a prediction, not a valuation and not "
               "a confirmation - a record is verified when a person has "
               "checked it.")

# What a change in one place asks for everywhere else. The point of the
# section: a passport is a connected record, not a form.
CONNECTED = {
    "trigger": "A songwriter is added under Credits.",
    "effects": [
        ("Ownership", "The composition split has to be reopened and the new "
                      "share agreed."),
        ("Identifiers", "Their IPI or CAE number is needed, or the "
                        "registration cannot name them."),
        ("Agreements", "The split sheet has to be reissued and signed."),
        ("Versions", "Every version of the recording inherits the change."),
        ("Release History", "The correction is recorded, with the date and "
                            "who made it."),
    ],
    "note": ("One entry, five consequences. That is why this is a record "
             "rather than a form."),
}

# The shape a conflict takes. Nothing here is claimed to be verified.
ISSUES = [
    {"issue": "Composition shares total 90%", "category": "Ownership",
     "severity": "High",
     "evidence": "Three writer shares on file: 40%, 30%, 20%.",
     "action": "Confirm the missing 10% with the writers named in Credits.",
     "status": "Open"},
    {"issue": "Contributor listed without a role", "category": "Credits",
     "severity": "Medium",
     "evidence": "Two performers have no role assigned.",
     "action": "Assign a role to each before confirmation.",
     "status": "Open"},
    {"issue": "Version missing a corresponding asset", "category": "Versions",
     "severity": "Medium",
     "evidence": "A clean version is listed with no audio file attached.",
     "action": "Attach the clean master or remove the version.",
     "status": "Open"},
    {"issue": "Agreement not signed", "category": "Agreements",
     "severity": "High",
     "evidence": "The split sheet has one outstanding signature.",
     "action": "Send for signature before delivery.",
     "status": "Awaiting Signature"},
]

IMAGE = {
    "wide": {"stem": "/static/img/passport-wide", "widths": [900, 1300, 1672],
             "width": 1672, "height": 941},
    "close": {"stem": "/static/img/passport-close", "widths": [520, 1037],
              "width": 1037, "height": 734},
    "alt": ("One album release arranged at the centre of a floor blueprint "
            "connecting credits, ownership, identifiers, versions, "
            "agreements, assets and release history."),
}

# The public page.
USE = [
    ("Who can see it",
     "You, and the collaborators you invite. A collaborator sees the release "
     "they were invited to and nothing else in the catalog."),
    ("How permissions work",
     "Access is per release and per role. Somebody added to confirm a split "
     "does not get the agreements, and somebody sent an agreement does not "
     "get the masters."),
    ("What goes to a partner",
     "Only what a delivery or collection actually requires, and only when you "
     "submit it: the release information, the identifiers, the credits and "
     "the splits. Documents stay with the record unless a partner needs one "
     "for a specific claim."),
    ("How changes are tracked",
     "Every change is a release-history event with a date and an author. "
     "Nothing is overwritten silently, which is what makes the record worth "
     "anything in a dispute."),
    ("How documents are handled",
     "Agreements and supporting files are stored against the release and are "
     "not shared outside it without your action."),
    ("Export and removal",
     "The record is yours: export it, or remove it and the derived findings "
     "go with it. The structure is built to be portable rather than to hold "
     "you in place."),
]

STANDARDS = ("The record is built as structured, export-ready release "
             "information so it can move: portable metadata design, and an "
             "architecture ready for standards work including future DDEX "
             "integration. Street Banker is not DDEX-certified today, and "
             "nothing here claims otherwise.")


def get_passport_config():
    return {
        "number": NUMBER,
        "eyebrow": EYEBROW,
        "headline": HEADLINE,
        "support": SUPPORT,
        "trust": TRUST,
        "trust_copy": TRUST_COPY,
        "trust_link": TRUST_LINK,
        "primary_cta": PRIMARY_CTA,
        "secondary_cta": SECONDARY_CTA,
        "example_label": EXAMPLE_LABEL,
        "categories": CATEGORIES,
        "health_label": HEALTH_LABEL,
        "health_note": HEALTH_NOTE,
        "health_statuses": HEALTH_STATUSES,
        "connected": CONNECTED,
        "issues": ISSUES,
        "image": IMAGE,
    }


def completeness():
    """Deterministic: the share of example categories with nothing
    outstanding. Fields filled, and nothing else."""
    done = sum(1 for c in CATEGORIES if c["missing"] == "Nothing outstanding.")
    return round(100 * done / len(CATEGORIES))
