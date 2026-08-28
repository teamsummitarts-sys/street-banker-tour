"""The Ecosystem Hub model: five core hubs that group every tool.

Single source of truth for the sidebar navigation AND the /desk/<hub>
landing pages, so the two can never drift apart. Each item is
(key, href, icon_path, label, one_line_desc). Icon paths are pipe-joined
SVG path lists rendered by base.html.
"""

HUBS = [
    ("command", "Command Center", "Your whole operation on one screen — scores, actions, and the strategist read.", [
        ("command-center", "/command-center", "M4 4h5v5H4zM11 4h5v3h-5zM11 9h5v7h-5zM4 11h5v5H4z", "Command Center", "Every module's live status on one board."),
        ("actions", "/actions", "M8 4h8M8 10h8M8 16h8|M4 4l1 1 2-2M4 10l1 1 2-2M4 16l1 1 2-2", "Actions", "The prioritized to-do list your data generates."),
        ("qualification", "/qualification", "M4 16V9M9 16V5M14 16v-8|M3 16h14M14 4l1.5 1.5L18 3", "Growth Score", "Release readiness scored from real signals."),
        ("trust-score", "/trust-score", "M10 3l6 3v5c0 3-2.5 5-6 6-3.5-1-6-3-6-6V6z|M10 8v3M10 13v.5", "Trust Score", "How complete and verifiable your record is."),
        ("insights", "/insights", "M10 3a5 5 0 00-3 9v2h6v-2a5 5 0 00-3-9z|M8 16h4M9 18h2", "AI Insights", "Rule-based observations from your own numbers."),
        ("benchmark", "/benchmark", "M4 16V9M9 16V5M14 16v-8|M3 16h14", "Benchmark", "Where you stand against comparable catalogs."),
        ("artist-twin", "/artist-twin", "M10 3a4 4 0 100 8 4 4 0 000-8z|M4 17c0-3 2.5-5 6-5s6 2 6 5M14 4l1 1 2-2", "Artist Twin", "The strategist read on your next best moves."),
    ]),
    ("studio", "Studio & Assets", "Make the record and keep its paperwork straight — audio, art, files, and passports.", [
        ("rack", "/rack", "M3 4h14v4H3z|M3 12h14v4H3z|M6 6h.01|M6 14h.01|M13 6h2|M13 14h2", "The Rack", "Real browser DSP: EQ, tube, comp, hooks, WAV export."),
        ("remix-lab", "/remix-lab", "M15.5 6.5A6 6 0 004.9 8.2|M4.5 13.5A6 6 0 0015.1 11.8|M16 3v4h-4|M4 17v-4h4", "Remix Lab", "One master in, a measured remix brief back."),
        ("audio-studio", "/audio-studio", "M4 10h2v4H4z|M8 6h2v12H8z|M12 8h2v8h-2z|M16 11h2v2h-2z", "Audio Studio", "Dub a release, cut campaign audio, split stems, register a voice."),
        ("artwork", "/artwork", "M4 4h12v12H4z|M4 13l4-4 3 3 2-2 3 3M13 7.5a.5.5 0 100-1 .5.5 0 000 1z", "Cover Art", "Generate and manage release artwork."),
        ("vault", "/vault", "M4 5h12v11H4z|M4 8h12M7 5V3h6v2M10 11v2", "Asset Vault", "Stems, bounces, and press assets in one place."),
        ("beats", "/beats", "M5 14a3 3 0 106 0 3 3 0 00-6 0z|M11 14V4l5 2v8|M14 12a2 2 0 104 0 2 2 0 00-4 0z", "Beats", "Beat registry, licences, cleared list, usage cases."),
        ("tracks", "/tracks", "M4 3h12v14H4z|M7 7h6|M7 10h6|M7 13h4", "Track Passports", "Per-track rights, metadata, and lockbox sign-offs."),
        ("catalog", "/catalog", "M7 4v10a2 2 0 11-2-2h2M7 4l9-1v9a2 2 0 11-2-2h2", "Catalog", "Every song you own, with its status."),
        ("identifiers", "/identifiers", "M4 6h12M4 10h12M4 14h7|", "Identifiers", "ISRCs, UPCs, and codes in one registry."),
        ("documents", "/documents", "M6 3h6l3 3v11a1 1 0 01-1 1H6a1 1 0 01-1-1V4a1 1 0 011-1z|M8 11h5M8 14h3", "Documents", "Contracts and licenses, uploaded and filed."),
        ("profile", "/artist-profile", "M10 4a3 3 0 100 6 3 3 0 000-6z|M4 17c0-3 2.5-5 6-5s6 2 6 5", "Artist Profile", "The profile powering your public pages."),
    ]),
    ("launch", "Launch Engine", "From finished master to the world — prepare, release, promote, and measure.", [
        ("autopilot", "/releases/autopilot", "M10 3l7 7-7 7-7-7z|M10 7v6M7 10h6", "Release Autopilot", "Eight stages from intake to catalog follow-up."),
        ("clean-release", "/releases/clean-release", "M10 3l6 3v5c0 3-2.5 5-6 6-3.5-1-6-3-6-6V6z|M7.5 10l2 2 3.5-4", "Clean Release", "17-point score; red rights issues block submission."),
        ("releases", "/releases", "M5 4h10a1 1 0 011 1v11a1 1 0 01-1 1H5a1 1 0 01-1-1V5a1 1 0 011-1z|M4 8h12M8 3v3M12 3v3", "Release Scheduler", "Your calendar of what drops when."),
        ("registration", "/registration", "M4 10l4 4 8-9|M3 6h6", "Registration", "Step-by-step society and platform registrations."),
        ("links", "/links", "M8 11a3 3 0 004 0l2-2a3 3 0 00-4-4l-1 1M12 9a3 3 0 00-4 0l-2 2a3 3 0 004 4l1-1", "Smart Links", "One link per release with real click analytics."),
        ("rollout", "/rollout-studio", "M4 4h12v9H4z|M4 13l3 4M16 13l-3 4M7 8l2 2 4-4", "Rollout Engine", "Generated captions, briefs, and rollout plans."),
        ("epk", "/epk", "M5 3h7l3 3v11a1 1 0 01-1 1H5a1 1 0 01-1-1V4a1 1 0 011-1z|M7 9h6M7 12h6M7 15h3", "Press Kit", "Your public EPK, always current."),
        ("press-desk", "/press-desk", "M4 4h9v12H4z|M13 7h3v7a2 2 0 11-2-2h2|M6 7h5M6 10h5M6 13h3", "Press Desk", "Media list, announcements, and who opened which pitch."),
        ("playlists", "/playlists", "M4 5h9M4 9h9M4 13h5|M15 11v5a2 2 0 11-2-2", "Playlists", "Pitch tracking for curator outreach."),
        ("pulse", "/pulse", "M2 10h3l2-5 3 10 3-8 2 3h3", "Artist Pulse", "Daily follower and popularity snapshots."),
        ("audience", "/audience", "M7 8a2.5 2.5 0 100-5 2.5 2.5 0 000 5zM13 8a2.5 2.5 0 100-5 2.5 2.5 0 000 5z|M3 16c0-2.2 1.8-4 4-4M13 12c2.2 0 4 1.8 4 4", "Audience", "Who's listening, and where."),
        ("stats", "/stats", "M4 16V10M9 16V4M14 16v-4|M3 16h14", "Streaming Stats", "Growth curves from your Pulse history."),
    ]),
    ("stage", "Live Stage Suite", "Everything between the booking and the encore — shows, plots, lights, and the rider.", [
        ("tours", "/tours", "M3 4h14v12H3z|M3 8h14|M6 12h3|M12 12h2|M7 2v4|M13 2v4", "TOUR", "The whole run: My Day, Show Command, advance, travel, rooms, guests, money."),
        ("tour", "/tour", "M3 5h14v11H3z|M3 9h14|M7 3v4|M13 3v4", "Tour Hub", "Shows from hold to settled, advanced by rules."),
        ("stage-plot", "/stage-plot", "M4 4h12v8H4z|M2 16h16|M7 12v4|M13 12v4", "Stage Plot", "Drag-and-drop plot with an auto input list."),
        ("lights", "/lights", "M10 2v4|M4 6l2 2|M16 6l-2 2|M6 12a4 4 0 118 0v4H6z", "Light Studio", "Cue programming with real DMX output."),
        ("tour-board", "/tour-board", "M7 8a3 3 0 116 0 3 3 0 01-6 0z|M2 17c1-3 4-4 8-4s7 1 8 4", "Team-Up Board", "Artists and venues finding each other."),
    ]),
    ("money", "Royalty Sweep & Banking", "The money side — find it, claim it, value it, and keep the books straight.", [
        ("overview", "/overview", "M4 5a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1H5a1 1 0 01-1-1V5z|M14 5h2M14 8h3", "Overview", "Your recovery desk at a glance."),
        ("royalties", "/royalties", "M4 7l6-3 6 3v6l-6 3-6-3z|M4 7l6 3 6-3M10 10v6", "Royalties", "Income by source from your statements."),
        ("statements", "/statements", "M6 3h6l3 3v11a1 1 0 01-1 1H6a1 1 0 01-1-1V4a1 1 0 011-1z|M8 9h5M8 12h5M8 15h3M10 3v4h4", "Statements", "Upload or email statements; rows become data."),
        ("recovery", "/recovery", "M10 4a6 6 0 100 12 6 6 0 000-12z|M10 7v3l2 2", "Recovery", "Findings pulled from your own uploads."),
        ("royalty-lanes", "/royalty-lanes", "M3 5h14|M3 9h14|M3 13h14|M3 17h9", "Royalty Lanes", "Nine income lanes per song, claimed or missing."),
        ("money-queue", "/money-queue", "M4 4h12l-2 5 2 5H4z|M4 14v3", "Money Queue", "Missing-money actions, criticals first."),
        ("cases", "/royalty-recovery/cases", "M4 5h12v10H4z|M4 8h12M8 5V3h4v2M10 11v2", "Recovery Cases", "Tracked claims from open to paid."),
        ("disputes", "/disputes", "M10 3l7 4v5c0 3-3 5-7 5s-7-2-7-5V7z|M10 8v3M10 13v0", "Disputes", "Log and track conflicts on your catalog."),
        ("publishing", "/publishing", "M5 4h7a2 2 0 012 2v10H7a2 2 0 00-2 2V4z|M14 6h1a1 1 0 011 1v11a2 2 0 00-2-2", "Publishing", "Composition-side income and registrations."),
        ("mechanicals", "/mechanicals", "M10 6a4 4 0 100 8 4 4 0 000-8z|M10 2v2M10 16v2M2 10h2M16 10h2M4.5 4.5l1.5 1.5M14 14l1.5 1.5", "Mechanicals", "MLC-side collection status."),
        ("neighboring", "/neighboring-rights", "M10 3a7 7 0 100 14 7 7 0 000-14z|M3 10h14M10 3c2 2 2 12 0 14M10 3c-2 2-2 12 0 14", "Neighboring Rights", "Performance royalties on the master side."),
        ("territories", "/territories", "M10 3a7 7 0 100 14 7 7 0 000-14z|M3 10h14M10 3c2 2 2 12 0 14M10 3c-2 2-2 12 0 14M4 6h12M4 14h12", "Territories", "Where your income actually comes from."),
        ("connections", "/connections", "M8 11a3 3 0 004 0l2-2a3 3 0 00-4-4l-1 1M12 9a3 3 0 00-4 0l-2 2a3 3 0 004 4l1-1", "Connections", "What's wired up, honestly."),
        ("valuation", "/valuation", "M10 3l6 4v6l-6 4-6-4V7z|M10 8v4", "Valuation", "Catalog value from your real history."),
        ("revenue-os", "/revenue-os", "M4 16V4h12v12z|M7 13V9M10 13V7M13 13v-3", "Revenue OS", "Income structure across your whole operation."),
        ("funding", "/funding", "M3 6h14v8H3z|M10 8a2 2 0 100 4 2 2 0 000-4zM6 6v0M14 14v0", "Funding", "Advance eligibility from your Capital Score."),
        ("capital", "/capital", "M10 3v14M6 7h6a2 2 0 010 4H8a2 2 0 000 4h6", "Capital", "Monetization hub for what you own."),
        ("sync", "/sync", "M4 6h9l-2-2M16 14H7l2 2|M4 6v0M16 14v0", "Sync / Licensing", "Pitches and placements for film, TV, and games."),
        ("sync-packs", "/sync/clearance-packs", "M4 4h12v9H4z|M8 7v4l3-2zM4 16h12", "Sync Packs", "Cleared-and-ready pitch bundles."),
        ("deal-simulator", "/sync/deal-simulator", "M4 10h5M11 10h5|M10 3v14M6 6l-2 4h4zM14 12l-2 4h4z", "Deal Simulator", "Run a deal's numbers before signing."),
        ("deal-room", "/deal-room", "M7 9l3-3 3 3M10 6v8|M4 16h12M4 4h4M12 4h4", "Deal Room", "Your export-ready story for partners."),
        ("conflicts", "/conflicts", "M10 3l7 13H3z|M10 8v3M10 13.5v.5", "Conflicts", "Rights conflicts that need attention."),
        ("reports", "/reports", "M6 3h6l3 3v11a1 1 0 01-1 1H6a1 1 0 01-1-1V4a1 1 0 011-1z|M8 10h5M8 13h5", "Reports", "Exports and summaries of everything above."),
        ("hours", "/hours", "M10 3a7 7 0 100 14 7 7 0 000-14z|M10 6v4l3 2|M3 3l2 2M17 3l-2 2", "Hours Desk", "Bill your time, take bookings, approve collaborators."),
        ("tax", "/tax", "M6 3h8a1 1 0 011 1v13l-2-1.5L11 17l-2-1.5L7 17l-2-1.5V4a1 1 0 011-1z|M8 7h4M8 10h4", "Tax Center", "Income summarized for tax season."),
    ]),
]

# Groups outside the five hubs.
LABEL_GROUP = ("Label Services", [
    ("services", "/services", "M4 6h12v10H4z|M4 9h12M8 6V4h4v2", "Services", "Art Is War Records label services."),
    ("apparel", "/apparel", "M6 6l4-2 2 2 2-2 4 2-2 4h-1v6H9v-6H8L6 6z", "Apparel & Merch", "The store's own checkout, on the page you are on."),
    ("submit", "/submit", "M10 4v9M6 8l4-4 4 4|M4 15h12", "Submit Music", "Send music to the label desk."),
    ("review", "/admin/review", "M4 5h12v10H4z|M7 9l2 2 4-4M4 8h12", "Review Queue", "Submissions awaiting review."),
])
COMMUNITY_GROUP = ("Community", [
    ("discover", "/discover", "M10 3a7 7 0 100 14 7 7 0 000-14z|M13 7l-2 4-4 2 2-4z", "Discover (Fans)", "Find artists to follow and support."),
    ("marketplace", "/marketplace", "M4 7h12l-1 8H5zM4 7l-1-3|M8 11h4", "Collab Marketplace", "Post or answer real collaboration requests."),
    ("network", "/network", "M10 4a2 2 0 100 4 2 2 0 000-4zM5 13a2 2 0 100 4 2 2 0 000-4zM15 13a2 2 0 100 4 2 2 0 000-4z|M10 8l-4 5M10 8l4 5", "Network", "The artist directory."),
    ("fan-label", "/fan-label", "M10 3l2 4 4 .5-3 3 .8 4.5L10 13l-3.8 2 .8-4.5-3-3 4-.5z", "Fan Label", "Back the artists you believe in."),
    ("fans", "/fans", "M7 8a2.5 2.5 0 100-5 2.5 2.5 0 000 5zM13 8a2.5 2.5 0 100-5 2.5 2.5 0 000 5z|M3 16c0-2.2 1.8-4 4-4M13 12c2.2 0 4 1.8 4 4", "Fan Dashboard", "Your fan-side home."),
    ("capital", "/capital", "M10 3v14M6 7h6a2 2 0 010 4H8a2 2 0 000 4h6", "Capital", "Monetization hub."),
])
ACCOUNT_GROUP = ("Account", [
    ("fan-club-admin", "/fan-club", "M10 3l2 4 4 .5-3 3 .8 4.5L10 13l-3.8 2 .8-4.5-3-3 4-.5z|M10 8v2", "Fan Club", "Your paid membership club and drops."),
    ("inbox", "/inbox", "M3 12l3-8h8l3 8v4a1 1 0 01-1 1H4a1 1 0 01-1-1z|M3 12h4l1.5 2h3L13 12h4", "Inbox", "Messages and submissions."),
    ("notifications", "/notifications", "M10 3a4 4 0 00-4 4c0 4-2 5-2 5h12s-2-1-2-5a4 4 0 00-4-4z|M8.5 16a1.5 1.5 0 003 0", "Notifications", "Everything that happened while you were away."),
    ("team", "/team", "M7 8a2.5 2.5 0 100-5 2.5 2.5 0 000 5zM13 8a2.5 2.5 0 100-5 2.5 2.5 0 000 5z|M3 16c0-2.2 1.8-4 4-4M13 12c2.2 0 4 1.8 4 4", "Team", "Invite your manager, accountant, attorney."),
    ("billing", "/billing", "M3 6h14v8H3z|M3 9h14M6 12h3", "Billing", "Plan and payments."),
    ("portal", "/portal", "M4 4h12v12H4z|M4 8h12M8 8v8", "Partner Portal", "Read-only views for your team memberships."),
    ("roster", "/roster", "M6 7a3 3 0 116 0 3 3 0 01-6 0z|M1 17c1-3 3.5-4 8-4|M13 9h6|M13 13h6|M13 17h4", "Label Roster", "Your artists, one desk (Label plan)."),
    ("referrals", "/referrals", "M10 3v14|M3 10h14|M6 6l8 8|M14 6l-8 8", "Referrals", "Bring an artist, both sides win."),
    ("certified", "/certified", "M10 2l2.4 4.9 5.6.8-4 3.9.9 5.4-4.9-2.6-4.9 2.6.9-5.4-4-3.9 5.6-.8z", "Certified", "Six rungs computed from your real record."),
    ("settings", "/settings", "M10 7a3 3 0 100 6 3 3 0 000-6z|M10 3v2M10 15v2M3 10h2M15 10h2", "Settings", "Account and preferences."),
])

FAN_ACCOUNT_KEYS = ("notifications", "billing", "settings")

# One icon per hub, for the collapsed rail. Kept in a dict rather than a
# sixth field on the HUBS tuples so nothing that unpacks them - the
# sidebar, the desk pages, command_index - has to change to gain it.
HUB_ICONS = {
    "command": "M4 4h5v5H4zM11 4h5v3h-5zM11 9h5v7h-5zM4 11h5v5H4z",
    "studio": "M3 4h14v4H3z|M3 12h14v4H3z|M6 6h.01|M6 14h.01",
    "launch": "M10 3l7 7-7 7-7-7z|M10 7v6M7 10h6",
    "stage": "M3 5h14v11H3z|M3 9h14|M7 3v4|M13 3v4",
    "money": "M10 3v14M6 7h6a2 2 0 010 4H8a2 2 0 000 4h6",
    "account": "M10 4a3 3 0 100 6 3 3 0 000-6z|M4 17c0-3 2.5-5 6-5s6 2 6 5",
    "label": "M4 6h12v10H4z|M4 9h12M8 6V4h4v2",
    "community": "M10 3a7 7 0 100 14 7 7 0 000-14z|M13 7l-2 4-4 2 2-4z",
}

# Features that genuinely work today; everything else shows a lock.
#
# Anything gated on a deployment flag CANNOT be a literal here. Remix Lab was,
# and once its engine was connected the sidebar badge, the hub-desk tile, the
# hub-desk footnote and the command palette all went on calling a live page
# "example data, not yours" - four surfaces wrong from one stale list entry.
# Flag-gated keys are appended by live_keys() instead.
_BASE_LIVE = ["apparel", "beats", "statements", "notifications", "documents", "identifiers", "cases",
             "deal-room", "sync-packs", "deal-simulator", "artist-twin",
             "revenue-os", "trust-score", "overview", "royalties", "recovery",
             "valuation", "links", "rollout", "artwork", "services", "submit",
             "inbox", "settings", "epk", "discover", "catalog", "command-center",
             "actions", "autopilot", "clean-release", "qualification", "profile",
             "vault", "review", "pulse", "team", "stats", "tax", "connections",
             "releases", "publishing", "mechanicals", "neighboring",
             "territories", "insights", "disputes", "fan-club-admin", "portal",
             "tour", "tours", "stage-plot", "tour-board", "rack", "roster", "referrals",
             "lights", "tracks", "royalty-lanes", "money-queue", "certified",
             "press-desk",
             "hours"]


def live_keys():
    """LIVE_KEYS, plus whatever the deployment's flags have actually switched on.

    Called per request rather than computed at import: the flags are read from
    the environment, and a module-level list would freeze whatever was set when
    the process booted.
    """
    keys = list(_BASE_LIVE)
    try:
        import remix_lab_config
        if remix_lab_config.engine_live():
            keys.append("remix-lab")
    except Exception:
        pass
    try:
        import audio_studio
        if any(lane["on"] for lane in audio_studio._lanes_for_render()):
            keys.append("audio-studio")
    except Exception:
        pass
    return keys


# Kept as a name because templates and tests read it. It is the BASE list -
# call live_keys() for the flag-aware answer.
LIVE_KEYS = _BASE_LIVE


def command_index():
    """Every destination as one flat list, for the command palette.

    Built from the same HUBS/LABEL/COMMUNITY/ACCOUNT definitions the
    sidebar renders, so the palette cannot drift from the nav - a search
    box that finds a page which no longer exists is worse than no search
    box. Each entry carries the hub it belongs to, so a result can say
    where it lives, and whether the feature is actually live.

    Returns [{key, href, label, desc, group, live}].
    """
    out = []
    seen = set()

    def add(key, href, label, desc, group):
        if key in seen:
            return
        seen.add(key)
        out.append({"key": key, "href": href, "label": label,
                    "desc": desc, "group": group,
                    "live": key in LIVE_KEYS})

    for _hkey, name, _tagline, items in HUBS:
        for key, href, _icon, label, desc in items:
            add(key, href, label, desc, name)
    for group_name, items in (LABEL_GROUP, COMMUNITY_GROUP, ACCOUNT_GROUP):
        for key, href, _icon, label, desc in items:
            add(key, href, label, desc, group_name)
    # The Hours desk sits in the money hub already; anything reachable but
    # not in a group would be invisible here, so keep this list honest by
    # deriving it rather than hand-maintaining a second one.
    return out


def get_hub(key):
    for hkey, name, tagline, items in HUBS:
        if hkey == key:
            return {"key": hkey, "name": name, "tagline": tagline, "modules": items}
    return None
