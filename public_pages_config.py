"""About, Contact and Partner Network — the three public pages the footer
promised and did not have.

Before this, About pointed at /services (the label-services page),
Contact pointed at /submit (the A&R submission form) and Partner Network
pointed at /network, which bounced a signed-out visitor to a login wall.
Three different destinations, none of them the thing named on the link.

Nothing here invents a company. No headcount, no founding date, no
offices, no client list, no partner logos — none of that is verified, so
none of it appears. What is written down is what the product does and how
to reach somebody, which is all a visitor came for.
"""

# --- About ----------------------------------------------------------------
ABOUT = {
    "eyebrow": "About",
    "headline": ["Built for the part", "nobody sees."],
    "lead": ("Street Banker is an operating system for artists who own "
             "their work. Release, campaign, rights, distribution and "
             "royalties in one place, run by the artist rather than on "
             "their behalf."),
    "sections": [
        ("Why it exists",
         "Most of what decides whether a release earns is decided before "
         "it comes out, and most of it is admin: splits that were never "
         "signed, credits nobody filled in, registrations that were never "
         "filed. The work is dull, it is invisible, and it is where the "
         "money goes missing. Street Banker puts it in one place and makes "
         "it legible."),
        ("What we believe",
         "The artist owns the work. The system explains itself. A finding "
         "is a question until somebody verifies it. Nothing leaves the "
         "workspace without approval. Those four sentences decide most of "
         "the product arguments we have."),
        ("How we make money",
         "Subscriptions to the platform, and services on the lanes that "
         "include them. We do not sell artist data and we do not take a "
         "cut of a recovery we did not work."),
        ("What we are not",
         "Not a label unless you enter a partnership that says so. Not a "
         "distributor — delivery runs through our distribution "
         "partnership. Not a prediction engine: nothing here tells you "
         "whether a record will do well."),
    ],
    "cta": {"label": "Walk the product tour", "href": "/product-tour"},
}

# --- Contact --------------------------------------------------------------
CONTACT = {
    "eyebrow": "Contact",
    "headline": ["Talk to a person."],
    "lead": ("One address, read by people who work on the product. Tell us "
             "what you are trying to do and we will point you at the right "
             "part of it."),
    "email": "team.summitarts@gmail.com",
    "routes": [
        ("Support and account questions",
         "Something is broken, or you cannot get into your account.",
         None),
        ("Submitting music",
         "A&R submissions have their own form so they reach the right "
         "people with the right information attached.",
         {"label": "Open the submission form", "href": "/submit"}),
        ("Labels and managers",
         "Roster-level questions, catalog migrations and label services.",
         {"label": "Label services", "href": "/services"}),
        ("Partnerships and integrations",
         "Distribution, data and platform partnerships.",
         {"label": "Partner network", "href": "/partners"}),
        ("Rights, privacy and data requests",
         "Deletion, export, or a question about how your data is handled.",
         {"label": "Artist control policy", "href": "/artist-control"}),
    ],
    "note": ("We are a small team. Expect a reply from a person rather than "
             "a ticket number, and expect it to take a day or two."),
}

# --- Partner Network ------------------------------------------------------
# Only the partnership that exists is described. No logo wall.
PARTNERS = {
    "eyebrow": "Partner network",
    "headline": ["Who does what."],
    "lead": ("Street Banker does not do everything itself, and the parts it "
             "does not do are worth naming so you know who is holding what."),
    "current": [
        ("Distribution", "Partner delivered",
         "Releases are assembled and validated inside Street Banker, then "
         "delivered through our distribution partnership rather than a "
         "direct line from this application. Your agreement governs the "
         "masters and the metadata."),
    ],
    "wanted": [
        ("Audio analysis",
         "A provider for the Release Signal read: sound, mood, arrangement "
         "and market adjacency."),
        ("Market data",
         "Catalog and audience data to sit behind the Artist Twin's "
         "reasoning, with commercial display rights."),
        ("Publishing administration",
         "Registration and collection for works whose splits are already "
         "locked in the Metadata Passport."),
        ("Social publishing",
         "The connection that turns a prepared Rollout Engine campaign "
         "into scheduled posts."),
    ],
    "note": ("Integrations are listed on the product tour with an honest "
             "status. Where a connection is built but not live it says "
             "Integration ready, not Live."),
    "cta": {"label": "Talk to us about a partnership", "href": "/contact"},
}


def get_about():
    return ABOUT


def get_contact():
    return CONTACT


def get_partners():
    return PARTNERS
