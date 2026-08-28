"""Section 9 — Royalty Sweep.

Catalog investigation, not banking. The section is a header, one archive
photograph, five stages and a way in; the picture carries the feeling and
the words carry the meaning.

The language here is deliberate. Nothing is recovered, found or
guaranteed - things are possible, suspected, potential, and every one of
them requires verification. Where a figure could ever appear it is
labelled an estimated value range and said to need checking.
"""

EYEBROW = "Royalty Sweep"
NUMBER = "09"
HEADLINE = ["Find what's yours.", "Keep what's earned."]
SUPPORT = ("Connect the catalog, trace missing registrations and income "
           "sources, and turn every potential gap into a trackable recovery "
           "case.")

PRIMARY_CTA = {"label": "Run a Royalty Sweep", "href": "/catalog-sweep"}
SECONDARY_CTA = {"label": "See how the sweep works"}
METHOD_LINK = {"label": "How Royalty Sweep works", "href": "/royalty-sweep"}

TRUST = "Your catalog. Your data. Your approval."
TRUST_COPY = ("Royalty Sweep identifies potential gaps and organises recovery "
              "work. Every finding requires verification before submission.")

WORKFLOW = [
    ("01", "Detect", "Scan the catalog for missing registrations, metadata "
                     "conflicts, duplicate records and unexplained reporting "
                     "gaps."),
    ("02", "Match", "Cross-reference recordings, compositions, contributors, "
                    "identifiers, ownership information and royalty sources."),
    ("03", "Verify", "Review evidence, confirm ownership and identify the "
                     "information required before a case can move forward."),
    ("04", "Claim", "Prepare and track the appropriate registration "
                    "correction, inquiry or recovery case."),
    ("05", "Track", "Monitor progress, requests for information, resolutions "
                    "and verified recovered income."),
]

# What the sweep can read from, and how. "Connected" is reserved for a
# live connection this app actually holds; everything else says so.
SOURCES = [
    ("Uploaded royalty statements", "Upload Supported"),
    ("Distributors", "Upload Supported"),
    ("Labels", "Upload Supported"),
    ("Publishers", "Upload Supported"),
    ("Performing-rights organisations", "Integration Ready"),
    ("Mechanical-rights organisations", "Integration Ready"),
    ("Neighbouring-rights organisations", "Integration Ready"),
    ("Digital-performance organisations", "Integration Ready"),
    ("YouTube and UGC systems", "Coming Soon"),
    ("Sync administrators", "Coming Soon"),
    ("International collection societies", "Coming Soon"),
]

# One example, labelled as one, with no money in it at all.
EXAMPLE = {
    "label": "Example recovery opportunity",
    "fields": [
        ("Opportunity", "Possible missing songwriter registration"),
        ("Affected release", "Example Single"),
        ("Source", "Mechanical royalty coverage"),
        ("Confidence", "Moderate"),
        ("Potential issue", "Composition ownership appears incomplete across "
                            "available records."),
    ],
    "needed": ["Writer names", "Ownership splits", "IPI or CAE identifiers",
               "Publishing administrator", "Existing registration confirmation"],
    "action": ("Complete the missing information before submitting a "
               "registration review."),
    "status": "Needs Information",
    "note": ("An example of the shape a case takes. It is not an artist's case "
             "and it carries no figure: an estimated value range is only "
             "produced once there is something real to estimate from, and it "
             "still requires verification."),
}

IMAGE = {
    "wide": {"stem": "/static/img/sweep-wide", "widths": [900, 1400, 1672],
             "width": 1672, "height": 555},
    "close": {"stem": "/static/img/sweep-close", "widths": [430, 860],
              "width": 860, "height": 465},
    "alt": ("Archive table covered with master tapes, hard drives, test "
            "pressings, notebooks and music-rights documents."),
}

# The public methodology page.
METHOD = [
    ("What gets reviewed",
     "Whatever you give it: royalty statements you upload, the catalog you "
     "enter or import, the identifiers attached to it, and the registrations "
     "you record. Nothing is read from an organisation Street Banker is not "
     "connected to, and no connection is implied that does not exist."),
    ("What counts as a potential opportunity",
     "A gap between what your catalog says and what the paperwork shows: a "
     "recording with no registration on file, a composition whose splits do "
     "not add up, a source that reports on one release and not its sibling, a "
     "duplicate that splits one work in two. Each is a question to answer, "
     "not a sum of money."),
    ("How estimates are calculated",
     "From what your own statements report for comparable work over a "
     "comparable period. Any figure appears as an estimated value range, "
     "labelled as one, and it is arithmetic on your data rather than a "
     "prediction. It changes when the data does, and it requires "
     "verification before anybody acts on it."),
    ("How cases are verified",
     "A case does not leave the workspace until the missing information is "
     "supplied and the ownership is confirmed. Registration corrections and "
     "inquiries are prepared for you to check and approve; the submission is "
     "yours to make or to authorise."),
    ("Which steps need a person",
     "Verification, approval and submission. The detection and matching work "
     "is automatic; deciding that a finding is real, and acting on it, is "
     "not."),
    ("How your data is handled",
     "Statements and catalog data are stored against your account and used to "
     "produce your own findings. They are not sold, and they are not used to "
     "train models without your explicit permission. You can remove an upload "
     "and the findings drawn from it go with it."),
]


def get_sweep_config():
    return {
        "number": NUMBER,
        "eyebrow": EYEBROW,
        "headline": HEADLINE,
        "support": SUPPORT,
        "primary_cta": PRIMARY_CTA,
        "secondary_cta": SECONDARY_CTA,
        "method_link": METHOD_LINK,
        "trust": TRUST,
        "trust_copy": TRUST_COPY,
        "workflow": WORKFLOW,
        "example": EXAMPLE,
        "image": IMAGE,
    }
