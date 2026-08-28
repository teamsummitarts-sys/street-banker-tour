"""Street Banker plan tiers and product worlds.

Four purchasable sections: Promote (Artist tier), Royalty Sweep (Pro
tier), Label Services, and the free Fan side. The old demo padlocks
become the paywall: pages above your tier render an upgrade card.
Payments are simulated until Stripe lands — plan switches are labeled
as demo everywhere.
"""

TIER_RANK = {"fan": 0, "artist": 1, "pro": 2, "label": 3}

PLANS = [
    ("fan", "Fan", "Free", "Discover music, follow artists, collect moments.",
     ["Discover & Network", "Fan Dashboard", "Mintable Moments", "Marketplace"]),
    ("artist", "Artist", "$9/mo", "The Promote suite — own your fans.",
     ["Smart Links + pre-saves", "Rollout Engine", "Press Kit + public EPK",
      "Fan CRM", "Command Center & Actions", "Audience & playlist tools"]),
    ("pro", "Pro", "$29/mo", "Everything in Artist plus the money engine.",
     ["Royalty Sweep: statements, recovery, catalog", "Valuation & funding tools",
      "Sync & rights pages", "Reports & Tax Center", "Consulting hours (with ambassadors)"]),
    ("label", "Label", "$99/mo", "Everything in Pro plus label operations.",
     ["Roster seats (coming with Label Mode)", "Label Services priority",
      "Partner reports", "Team permissions"]),
]
PLAN_NAMES = {key: name for key, name, _, _, _ in PLANS}

# Product worlds shown in the sidebar switcher: (key, label, home, min tier or None)
WORLDS = [
    ("promote", "Promote", "/links", "artist"),
    ("sweep", "Royalty Sweep", "/overview", "pro"),
    ("label", "Label Services", "/services", None),
    ("fan", "Fan Side", "/discover", None),
]

# Path-prefix tier gates. Public pages (/l/, /epk/<slug>, uploads, auth)
# are never listed here, so they stay open.
_ARTIST_PATHS = ("/links", "/rollout-studio", "/artwork", "/command-center",
                 "/actions", "/releases", "/audience", "/playlists", "/stats",
                 "/insights", "/benchmark", "/pulse", "/metadata-passport",
                 "/fan-club", "/tour", "/stage-plot", "/rack", "/lights", "/tracks", "/certified",
                 "/qualification", "/artist-profile",
                 "/vault", "/artist-twin", "/trust-score")
_PRO_PATHS = ("/overview", "/royalties", "/statements", "/recovery", "/disputes",
              "/publishing", "/mechanicals", "/neighboring-rights", "/territories",
              "/connections", "/catalog", "/identifiers", "/documents",
              "/conflicts", "/registration", "/valuation", "/funding", "/sync",
              "/tax", "/reports", "/royalty-recovery", "/deal-room", "/onesheet",
              "/revenue-os",
              "/capital-score", "/spend-optimizer", "/royalty-lanes",
              "/money-queue")


def _matches(path, prefixes):
    return any(path == p or path.startswith(p + "/") for p in prefixes)


def required_tier(path):
    if path == "/epk":  # exact only — /epk/<slug> is the public press page
        return "artist"
    # /roster/join/<token> stays open to invited artists of any tier.
    if path == "/roster" or (path.startswith("/roster/")
                             and not path.startswith("/roster/join/")):
        return "label"
    if _matches(path, _PRO_PATHS):
        return "pro"
    if _matches(path, _ARTIST_PATHS):
        return "artist"
    return None


def allowed(plan, tier):
    return TIER_RANK.get(plan, 1) >= TIER_RANK.get(tier, 0)


def world_for_path(path):
    """Which product world a path belongs to, for switcher highlighting."""
    if _matches(path, _PRO_PATHS):
        return "sweep"
    if path == "/epk" or _matches(path, _ARTIST_PATHS):
        return "promote"
    if _matches(path, ("/services", "/submit", "/roster")):
        return "label"
    if _matches(path, ("/discover", "/network", "/fan-label", "/fans",
                       "/marketplace", "/capital")):
        return "fan"
    return None
