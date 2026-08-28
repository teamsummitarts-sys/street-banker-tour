"""The public product tour.

Never name a content field `copy`, `items`, `keys`, `values` or `get`:
Jinja resolves `thing.copy` to the dict's built-in method and renders
`<built-in method copy of dict object at 0x...>` onto the public page.
Content fields here are `body`.

Twelve steps through one example artist journey, in the order the work
actually happens. Every step is labelled an example workspace, every one
says what it can and cannot do today, and none of them asks for an
account: the visitor is meant to be able to decide against Street Banker
from here without ever signing in.

Each step points at the public page for that module, so the tour is a
route through what already exists rather than a second copy of it.
"""

TITLE = "Public product tour"
LEAD = ("One example artist, one release, twelve steps. Everything shown is "
        "an example workspace — no artist's data appears anywhere in it, and "
        "nothing here needs an account.")

# status: live | example | partner | integration-ready | coming-soon
STEPS = [
    {
        "slug": "artist-eq", "module": "Artist EQ",
        "title": "The artist sets their priorities",
        "body": ("Six channels — release, creative, audience, rights, revenue, "
                 "growth. The console works out a lane, a set of modules and "
                 "three actions from where the faders sit, and recomputes it "
                 "server-side when you open the plan."),
        "status": "live", "href": "/plan",
        "link": "See the plan a mix produces",
    },
    {
        "slug": "artist-twin", "module": "AI Artist Twin",
        "title": "The Twin reads the release",
        "body": ("Release readiness, brand alignment, artwork strength, "
                 "audience fit and a next move — each one showing what it "
                 "looked at, how sure it is and what it is missing. It "
                 "forecasts nothing."),
        "status": "example", "href": "/artist-twin/start",
        "link": "Pick what you are working on",
    },
    {
        "slug": "release", "module": "Metadata Passport",
        "title": "The release gets organized",
        "body": ("Credits, ownership, identifiers, versions, agreements, "
                 "assets and history as one connected record. Adding a "
                 "songwriter under Credits asks something of four other "
                 "areas, and the record says so."),
        "status": "live", "href": "/metadata",
        "link": "Open the example passport",
    },
    {
        "slug": "creative", "module": "Creative Studio",
        "title": "The artwork and the campaign assets",
        "body": ("Brief, directions, revision, approval, adaptation. Cover "
                 "directions are generated from what you write; merch "
                 "mock-ups are for deciding rather than for printing, and "
                 "nothing here makes video."),
        "status": "live", "href": "/creative-studio",
        "link": "What it does, and what it does not",
    },
    {
        "slug": "rollout", "module": "Rollout Engine",
        "title": "The campaign gets built",
        "body": ("A 14, 21, 30, 60 or 90-day plan worked backwards from "
                 "release day: announcement, teaser, pre-save, artwork "
                 "reveal, release day, follow-up. Street Banker prepares the "
                 "posts. It does not publish them."),
        "status": "integration-ready", "href": "/rollout",
        "link": "See the 21-day example",
    },
    {
        "slug": "smart-link", "module": "Smart Links",
        "title": "The release gets one door",
        "body": ("One page per release: cover, streaming destinations, "
                 "pre-save before release and listen-now after it, email "
                 "capture with consent recorded, and a link per campaign so "
                 "you can tell where somebody came from."),
        "status": "live", "href": "/product-tour/smart-link",
        "link": "Open the example smart link",
    },
    {
        "slug": "fans", "module": "Fan Intelligence",
        "title": "The response gets attributed",
        "body": ("Where the visit came from, what device it was on, whether "
                 "they had been before, and whether they left an address. A "
                 "fan record the artist holds rather than rents."),
        "status": "example", "href": "/product-tour/smart-link#fans",
        "link": "See the example workspace",
    },
    {
        "slug": "distribution", "module": "Global Distribution",
        "title": "The package gets prepared",
        "body": ("Prepare, validate, deliver, monitor, maintain. Street "
                 "Banker assembles and checks the release; delivery goes out "
                 "through the distribution partnership rather than a direct "
                 "line from here."),
        "status": "partner", "href": "/distribution",
        "link": "What a release needs",
    },
    {
        "slug": "rights", "module": "Rights & Ownership",
        "title": "The splits get confirmed",
        "body": ("Shares that add up, signed by the people they name, with "
                 "identifiers attached. Incomplete or unsigned splits are a common reason royalty income becomes delayed or difficult to reconcile."),
        "status": "live", "href": "/metadata#used",
        "link": "Who can see what",
    },
    {
        "slug": "sweep", "module": "Royalty Sweep",
        "title": "A gap gets found",
        "body": ("Detect, match, verify, claim, track. A finding is a "
                 "question with evidence attached — it requires verification "
                 "before anything is submitted, and any figure is arithmetic "
                 "on your own statements."),
        "status": "example", "href": "/royalty-sweep",
        "link": "How the sweep works",
    },
    {
        "slug": "next", "module": "Street Banker",
        "title": "The next move gets recommended",
        "body": ("Everything above lands in one plan: a lane, the modules it "
                 "points at, the first three actions and an estimated setup "
                 "time. It is a starting point, not a placement."),
        "status": "live", "href": "/start",
        "link": "Open your starting plan",
    },
    {
        "slug": "lane", "module": "Three Street Banker Lanes",
        "title": "The artist picks a lane",
        "body": ("Distribution, Development or Partnership — release "
                 "infrastructure, deeper development, or long-term "
                 "partnership. Lanes move as the work does."),
        "status": "live", "href": "/lanes",
        "link": "Find the lane that fits",
    },
]

# One source of truth. Statuses used to be written out here as well as
# on the homepage and the product pages, and nothing failed when the
# three disagreed.
from capability_status import LABELS as STATUS_LABELS, MEANINGS as STATUS_MEANINGS  # noqa: E402
import capability_status  # noqa: E402

# --- the public smart-link example ---------------------------------------
SMART_LINK = {
    "label": "Example smart link",
    "artist": "Example Artist",
    "release": "Example Single",
    "state": "Pre-save",
    # Resolved at call time: with Spotify credentials set this reads Live
    # and with them unset it reads Integration ready, on every page at once.
    "destinations": [
        ("Spotify pre-save", None),
        ("Apple Music", "streaming_destinations"),
        ("YouTube Music", "streaming_destinations"),
        ("Bandcamp", "streaming_destinations"),
    ],
    "capture": [
        ("Email capture", "email_capture"),
        ("Consent text recorded with every signup", "email_capture"),
        ("Release-day email", "release_emails"),
        ("SMS capture", "sms_capture"),
        ("QR code for the printed run", "qr_codes"),
    ],
    "note": ("An example page. The destination buttons are not connected to a "
             "platform here — on a real release they carry the links you add. "
             "Nothing on this page collects anything."),
}

FAN_PANEL = {
    "label": "Example fan intelligence workspace",
    "positioning": "Own the relationship, not just the stream.",
    "body": ("Street Banker helps artists capture permission-based fan "
             "information, understand where listeners come from, and build "
             "direct audience relationships outside individual platforms."),
    "trust": ("Fan information is collected only with consent and remains "
              "controlled by the artist."),
    "rows": [
        ("Campaign source", "Example: link shared in a story", "smart_links"),
        ("Device and platform", "Example: mobile, iOS", "smart_links"),
        ("Return visitor", "Example: second visit", "smart_links"),
        ("Fan signup", "Example: address captured with consent", "email_capture"),
        ("Geographic response", "Example: grouped by country", "geographic_response"),
        ("Conversion event", "Example: pre-save confirmed", "conversion_events"),
    ],
    "note": ("Example rows, not a real campaign. Where a row says integration "
             "ready, the interface is built and the connection is not live."),
}

# --- the Creative Studio workflow preview --------------------------------
CREATIVE_STEPS = [
    ("Creative brief", "The release story, references, goals and what already "
                       "exists."),
    ("Artwork directions", "Several coherent directions, generated from the "
                           "brief rather than picked from a library."),
    ("Revision", "Targeted changes on the direction you want, keeping the "
                 "concept."),
    ("Approval", "One direction becomes the campaign master."),
    ("Platform adaptation", "The approved direction converted into the sizes "
                            "and formats each channel asks for."),
]

CREATIVE_OUTPUTS = [
    ("Single and album covers", "artwork_generator"),
    ("Alternate cover versions", "artwork_generator"),
    ("Explicit and clean variants", "artwork_generator"),
    ("Merchandise concepts", "creative_studio"),
    ("Posters and tour flyers", "creative_studio"),
    ("Social campaign assets", "creative_studio"),
    ("Story and vertical formats", "creative_studio"),
    ("Thumbnails and smart-link backgrounds", "creative_studio"),
    ("Press-kit graphics", "creative_studio"),
    ("Motion and video assets", "motion_assets"),
    ("Print-ready separations", "print_separations"),
]

BRAND_MEMORY = {
    "title": "Built around your identity.",
    "body": ("Creative Studio remembers approved colors, logos, image "
             "direction, wardrobe language, recurring symbols and rejected "
             "styles so each release still feels like the same artist."),
    "states": ["Approved direction", "Needs revision", "Rejected",
               "Master direction", "Platform adaptation"],
    "trust": ("Artist assets are not used for AI training without explicit "
              "permission."),
}


def resolved(key):
    """Status label for a capability key, or None to hide the chip."""
    return capability_status.label(key) if key else None


def get_tour_config():
    return {
        "title": TITLE, "lead": LEAD, "steps": STEPS,
        "status_labels": STATUS_LABELS,
        "smart_link": SMART_LINK, "fan_panel": FAN_PANEL,
        "creative_steps": CREATIVE_STEPS, "creative_outputs": CREATIVE_OUTPUTS,
        "brand_memory": BRAND_MEMORY,
    }
