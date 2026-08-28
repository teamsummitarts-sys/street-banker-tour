"""Section 4 — one system, six departments.

Six parts of one career, laid across one photograph rather than six.
The picture is a single documentary frame; the slices, the dividers, the
tonal steps and every word are markup, so the photograph is never cut up
into six files that could drift apart.

Destinations: each department points at the section of this homepage
that covers it, or - where the homepage has no surface for it - at the
public example workspace in the product tour. Nothing here points at a
login wall: a stranger asking what a department does must never be handed
a password field.
"""

# Tone per slice, left to right. These are washes at very low alpha laid
# over the photograph, not filters: the brief for this section asks for a
# progression a reader feels rather than sees, and anything heavier turns
# a documentary frame into six coloured panels.
DEPARTMENTS = [
    {
        "num": "01",
        "slug": "artist-twin",
        "name": "AI Artist Twin",
        "desc": "Evaluate and plan.",
        "href": "#artist-twin-section",
        "tone": "graphite neutral",
        "wash": "rgba(150, 156, 168, 0.05)",
    },
    {
        "num": "02",
        "slug": "creative-studio",
        "name": "Creative Studio",
        "desc": "Build the visual world.",
        "href": "#creative-studio",
        "tone": "warm charcoal",
        "wash": "rgba(126, 100, 74, 0.07)",
    },
    {
        "num": "03",
        "slug": "rollout-engine",
        "name": "Rollout Engine",
        "desc": "Turn the release into a campaign.",
        "href": "#rollout-engine",
        "tone": "muted brown",
        "wash": "rgba(112, 82, 56, 0.08)",
    },
    {
        "num": "04",
        "slug": "royalty-sweep",
        "name": "Royalty Sweep",
        "desc": "Find potential missing income.",
        "href": "#royalty-sweep-section",
        "tone": "soft amber",
        "wash": "rgba(190, 142, 72, 0.07)",
    },
    {
        "num": "05",
        "slug": "rights",
        "name": "Rights",
        "desc": "Protect ownership and metadata.",
        "href": "#metadata-passport",
        "tone": "olive charcoal",
        "wash": "rgba(112, 116, 82, 0.07)",
    },
    {
        "num": "06",
        "slug": "fan-intelligence",
        "name": "Fan Intelligence",
        "desc": "Understand and grow the audience.",
        "href": "/product-tour/smart-link#fans",
        "tone": "cool slate",
        "wash": "rgba(118, 138, 166, 0.08)",
    },
]

# The one photograph, and the sizes generated from it. The width and
# height are the master's, so the browser reserves the right box before a
# byte of image arrives and the section never shifts the page.
IMAGE = {
    "stem": "/static/img/departments",
    "widths": [900, 1200, 1553],
    "width": 1553,
    "height": 676,
    "alt": ("Band performing inside a raw studio with artwork and equipment "
            "surrounding the musicians."),
}

EYEBROW = "One system. Six departments."
SUPPORT = "Everything behind the artist, working together."


def get_departments_config():
    return {
        "eyebrow": EYEBROW,
        "support": SUPPORT,
        "departments": DEPARTMENTS,
        "image": IMAGE,
        "count": len(DEPARTMENTS),
    }
