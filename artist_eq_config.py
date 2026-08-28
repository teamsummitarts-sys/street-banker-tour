"""The Artist EQ: six strategic channels, and the plan they produce.

This replaces the fifteen-band frequency equaliser. The bands were
engraved 25 Hz through 16 kHz, which was a joke the interface could not
land: these are business priorities, and dressing them as audio
frequencies made a serious diagnostic read as a novelty plug-in.

Everything here is configuration plus deterministic functions over it.
Nothing is random and nothing is a prediction - the same six numbers
always produce the same plan, which matters because the browser computes
it live while /plan recomputes it server-side from a link, and the two
have to agree.

What the score is: a weighted average of six self-reported priorities,
scaled to 100, with a small preset weighting. What it is not: a
forecast. It cannot say whether a record will land, whether a label will
call, or whether money will come back - and nothing here claims it can.
"""

# --- channels ---------------------------------------------------------------
# icon: pipe-joined SVG paths on a 20x20 grid, the same convention hubs.py
# uses, so the template renders them the same way.
CHANNELS = [
    {
        "key": "release", "label": "Release", "short": "RELEASE",
        "icon": "M10 3a7 7 0 100 14 7 7 0 000-14z|M10 6.5v4l2.5 2",
        "desc": ("Release preparation, timing, metadata completion, "
                 "delivery readiness and the launch checklist."),
    },
    {
        "key": "creative", "label": "Creative", "short": "CREATIVE",
        "icon": "M10 3a5 5 0 00-3 9v2h6v-2a5 5 0 00-3-9z|M8 17h4",
        "desc": ("Cover artwork, visual identity, content production, "
                 "merch direction and creative consistency."),
    },
    {
        "key": "audience", "label": "Audience", "short": "AUDIENCE",
        "icon": ("M7 8a2.5 2.5 0 100-5 2.5 2.5 0 000 5zM13 8a2.5 2.5 0 100-5 "
                 "2.5 2.5 0 000 5z|M3 16c0-2.2 1.8-4 4-4M13 12c2.2 0 4 1.8 4 4"),
        "desc": ("Fan discovery and capture, segmentation, geographic "
                 "response, and streaming and social engagement."),
    },
    {
        "key": "rights", "label": "Rights", "short": "RIGHTS",
        "icon": "M10 3l6 3v5c0 3-2.5 5-6 6-3.5-1-6-3-6-6V6z|M7.5 10l2 2 3.5-4",
        "desc": ("Ownership, credits, splits, registrations, metadata "
                 "conflicts and the documents that prove them."),
    },
    {
        "key": "revenue", "label": "Revenue", "short": "REVENUE",
        "icon": "M10 3v14M6 7h6a2 2 0 010 4H8a2 2 0 000 4h6",
        "desc": ("Royalty visibility, missing-income detection, statement "
                 "review and monetisation opportunities."),
    },
    {
        "key": "growth", "label": "Growth", "short": "GROWTH",
        "icon": "M3 14l4-4 3 3 7-7|M14 6h3v3",
        "desc": ("Artist development, campaign expansion, partner "
                 "readiness, catalog growth and long-term leverage."),
    },
]

CHANNEL_KEYS = [c["key"] for c in CHANNELS]

# --- presets ----------------------------------------------------------------
# Product-routing logic, not validated research. These weights decide which
# part of Street Banker gets recommended first, and nothing else.
PRESETS = [
    {"id": "new-artist", "name": "New Artist",
     "icon": "M10 3v14M3 10h14|M5.5 5.5l9 9M14.5 5.5l-9 9",
     "values": {"release": 6, "creative": 8, "audience": 7, "rights": 4,
                "revenue": 3, "growth": 7},
     "weights": {"creative": 1.25, "audience": 1.15, "growth": 1.1}},
    {"id": "releasing-soon", "name": "Releasing Soon",
     "icon": ("M10 6a4 4 0 100 8 4 4 0 000-8z|M4 4c3.5 3.5 3.5 8.5 0 12"
              "M16 4c-3.5 3.5-3.5 8.5 0 12"),
     "values": {"release": 10, "creative": 8, "audience": 8, "rights": 7,
                "revenue": 5, "growth": 6},
     "weights": {"release": 1.35, "creative": 1.15, "audience": 1.15,
                 "rights": 1.1}},
    {"id": "growing-catalog", "name": "Growing Catalog",
     "icon": ("M10 4c3.5 0 6 1 6 2s-2.5 2-6 2-6-1-6-2 2.5-2 6-2z"
              "|M4 6v8c0 1 2.5 2 6 2s6-1 6-2V6"),
     "values": {"release": 6, "creative": 6, "audience": 8, "rights": 8,
                "revenue": 8, "growth": 9},
     "weights": {"audience": 1.15, "rights": 1.15, "revenue": 1.2,
                 "growth": 1.25}},
    {"id": "missing-royalties", "name": "Missing Royalties",
     "icon": "M9 4a5 5 0 100 10 5 5 0 000-10z|M13 12l4 4",
     "values": {"release": 4, "creative": 3, "audience": 4, "rights": 10,
                "revenue": 10, "growth": 5},
     "weights": {"rights": 1.4, "revenue": 1.4}},
    {"id": "label-ready", "name": "Label Ready",
     "icon": "M3 6l3 3 4-5 4 5 3-3v8H3z|M3 16h14",
     "values": {"release": 9, "creative": 9, "audience": 9, "rights": 9,
                "revenue": 8, "growth": 10},
     "weights": {}},
    {"id": "custom", "name": "Custom",
     "icon": "M4 6h12M4 10h12M4 14h12|M7 4v4M13 8v4M9 12v4",
     "values": None, "weights": {}},
]

DEFAULT_PRESET = "releasing-soon"

# --- lanes ------------------------------------------------------------------
LANES = [
    {"id": "distribution", "name": "Distribution — Release the Record",
     "href": "/services/distribution",
     "keys": ["release", "creative", "rights"],
     "why": "Your highest priorities are getting the record out clean, on time and correctly registered."},
    {"id": "development", "name": "Development — Build the Artist",
     "href": "/catalog-sweep",
     "keys": ["creative", "audience", "growth"],
     "why": "Your highest priorities are creative work and audience, which is artist development."},
    {"id": "partnership", "name": "Partnership — Build the Asset",
     "href": "/services",
     "keys": ["rights", "revenue", "growth"],
     "why": "Your highest priorities are rights and income, which is where a catalog becomes an asset."},
]

# --- modules ----------------------------------------------------------------
# Ordered per channel, strongest fit first. `slug` anchors the public plan
# page, which is where a signed-out visitor reads what each one does.
MODULES = {
    "release": [("Rollout Engine", "rollout-studio"),
                ("Metadata Passport", "metadata-passport"),
                ("Smart Links", "smart-links")],
    "creative": [("Creative Studio", "creative-studio"),
                 ("Artwork Generator", "artwork-generator"),
                 ("AI Artist Twin", "artist-twin")],
    "audience": [("Fan Intelligence", "fan-intelligence"),
                 ("Smart Links", "smart-links"),
                 ("Rollout Engine", "rollout-studio")],
    "rights": [("Rights & Ownership", "rights-ownership"),
               ("Metadata Passport", "metadata-passport"),
               ("Royalty Sweep", "royalty-sweep")],
    "revenue": [("Royalty Sweep", "royalty-sweep"),
                ("Catalog Intelligence", "catalog-intelligence"),
                ("Rights & Ownership", "rights-ownership")],
    "growth": [("AI Artist Twin", "artist-twin"),
               ("Deal Room", "deal-room"),
               ("Catalog Intelligence", "catalog-intelligence")],
}

MODULE_NOTES = {
    "rollout-studio": "Generates a dated rollout — captions, assets and a schedule — from the release you are working on.",
    "metadata-passport": "One record per track of every field a distributor, PRO or society asks for, with the gaps marked.",
    "smart-links": "One link per release that shows where the clicks came from and captures the fans who consent.",
    "creative-studio": "Cover directions, campaign visuals and merch concepts kept beside the release they belong to.",
    "artwork-generator": "Cover-art directions to compare side by side before committing to one.",
    "artist-twin": "A strategist read on your own numbers: what moved, what stalled, and what to do next.",
    "fan-intelligence": "Who is listening, where they are, and which of them you actually own the relationship with.",
    "rights-ownership": "Splits, credits and signatures in one place, with the documents attached to the track.",
    "royalty-sweep": "Reads your uploaded statements for money paid but unattributed, and for sources that have gone quiet.",
    "catalog-intelligence": "What the catalog earns, where it earns it, and what that pace is worth.",
    "deal-room": "The export a partner asks for: income on record, rights position and catalog shape in one document.",
}

# --- actions ----------------------------------------------------------------
ACTIONS = {
    "release": [("Complete the release metadata passport", "metadata-passport"),
                ("Build a 21-day rollout around the active release", "rollout-studio")],
    "creative": [("Generate and compare three cover-art directions", "artwork-generator"),
                 ("Set the visual direction for the campaign", "creative-studio")],
    "audience": [("Create a fan-capture smart link", "smart-links"),
                 ("Segment the fans you already own", "fan-intelligence")],
    "rights": [("Complete missing songwriter and producer splits", "rights-ownership"),
               ("File the documents that prove each split", "rights-ownership")],
    "revenue": [("Run a preliminary Royalty Sweep on the catalog", "royalty-sweep"),
                ("Upload a recent statement so the sweep has rows to read", "royalty-sweep")],
    "growth": [("Review the Artist Twin's campaign assessment", "artist-twin"),
               ("Assemble the deal room export for a partner", "deal-room")],
}

# Where each module lives inside the app. The public plan page explains
# modules by slug and never links into the product; these routes are for
# the signed-in surfaces (onboarding, the command desk) that already have
# an account behind them.
MODULE_ROUTES = {
    "Rollout Engine": "/rollout-studio",
    "Metadata Passport": "/metadata-passport",
    "Smart Links": "/links",
    "Creative Studio": "/artwork",
    "Artwork Generator": "/artwork",
    "AI Artist Twin": "/artist-twin",
    "Fan Intelligence": "/fans",
    "Rights & Ownership": "/tracks",
    "Royalty Sweep": "/recovery",
    "Catalog Intelligence": "/catalog",
    "Deal Room": "/deal-room",
}

# Every action leads somewhere real for an account that has one. Derived
# from the module each action belongs to rather than hand-listed, so a
# renamed action cannot orphan its link.
_SLUG_TO_MODULE = {slug: name for options in MODULES.values()
                   for name, slug in options}
ACTION_ROUTES = {
    label: MODULE_ROUTES.get(_SLUG_TO_MODULE.get(slug, ""), "")
    for options in ACTIONS.values() for label, slug in options
}

READINESS_BANDS = [
    (40, "Foundation Stage"),
    (60, "Building Momentum"),
    (75, "Release Ready"),
    (88, "Growth Ready"),
    (101, "Partner Ready"),
]

# Rough, and labelled rough everywhere it is shown.
SETUP_TIMES = ["10–15 minutes", "20–30 minutes", "45–60 minutes"]

MAX_MODULES = 4
ACTION_COUNT = 3
STORAGE_KEY = "streetBankerArtistEq"


# --- the engine -------------------------------------------------------------

def _preset(preset_id):
    for p in PRESETS:
        if p["id"] == preset_id:
            return p
    return None


def default_values():
    return dict(_preset(DEFAULT_PRESET)["values"])


def clean_values(raw):
    """Coerce whatever arrived into six numbers between 0 and 10."""
    out = default_values()
    for key in CHANNEL_KEYS:
        value = (raw or {}).get(key)
        try:
            value = float(value)
        except (TypeError, ValueError):
            continue
        out[key] = max(0.0, min(10.0, round(value * 2) / 2))
    return out


def readiness(values, preset_id=None):
    """0-100 from the six numbers, with a small preset weighting.

    A weighted mean and nothing cleverer, written out so the page can say
    exactly what it did.
    """
    values = clean_values(values)
    weights = ((_preset(preset_id) or {}).get("weights") or {}) if preset_id else {}
    total = weighted = 0.0
    for key in CHANNEL_KEYS:
        w = float(weights.get(key, 1.0))
        weighted += values[key] * w
        total += w
    score = (weighted / total) * 10 if total else 0
    return int(max(0, min(100, round(score))))


def readiness_band(score):
    for ceiling, label in READINESS_BANDS:
        if score < ceiling:
            return label
    return READINESS_BANDS[-1][1]


def recommended_lane(values):
    values = clean_values(values)
    best, best_score = LANES[0], -1.0
    for lane in LANES:
        score = sum(values[k] for k in lane["keys"])
        if score > best_score:
            best, best_score = lane, score
    return best


def _ranked_keys(values):
    """Channels strongest first. Ties break in declared order, so the same
    input never produces two different plans."""
    values = clean_values(values)
    return sorted(CHANNEL_KEYS, key=lambda k: (-values[k], CHANNEL_KEYS.index(k)))


def recommended_modules(values, limit=MAX_MODULES):
    picked, seen = [], set()
    ranked = _ranked_keys(values)
    for depth in range(3):
        for key in ranked:
            options = MODULES[key]
            if depth >= len(options):
                continue
            name, slug = options[depth]
            if slug in seen:
                continue
            seen.add(slug)
            picked.append({"name": name, "slug": slug, "channel": key,
                           "note": MODULE_NOTES.get(slug, "")})
            if len(picked) >= limit:
                return picked
    return picked


def top_actions(values, count=ACTION_COUNT):
    picked, seen = [], set()
    ranked = _ranked_keys(values)
    for depth in range(2):
        for key in ranked:
            options = ACTIONS[key]
            if depth >= len(options):
                continue
            label, slug = options[depth]
            if label in seen:
                continue
            seen.add(label)
            picked.append({"label": label, "slug": slug, "channel": key})
            if len(picked) >= count:
                return picked
    return picked


def setup_time(values):
    """Longer when the priorities point at work that takes longer."""
    values = clean_values(values)
    heavy = values["rights"] + values["revenue"]
    if heavy >= 16:
        return SETUP_TIMES[2]
    if heavy >= 10 or values["release"] >= 8:
        return SETUP_TIMES[1]
    return SETUP_TIMES[0]


def build_plan(values, preset_id=None):
    """Everything the output panel and the public plan page show."""
    values = clean_values(values)
    score = readiness(values, preset_id)
    return {
        "values": values,
        "preset": preset_id or "custom",
        "score": score,
        "band": readiness_band(score),
        "lane": recommended_lane(values),
        "modules": recommended_modules(values),
        "actions": top_actions(values),
        "setup_time": setup_time(values),
    }


def get_artist_eq_config():
    """Config for the template and, as JSON, for the browser."""
    return {
        "eyebrow": "ARTIST EQ",
        "heading": "TUNE YOUR ARTIST SYSTEM.",
        "support": "Set your priorities. Street Banker builds the plan.",
        "instruction": ("Adjust the six areas below or choose a preset. Your "
                        "recommended tools and next actions update instantly."),
        "channels": CHANNELS,
        "presets": PRESETS,
        "default_preset": DEFAULT_PRESET,
        "default_values": default_values(),
        "lanes": LANES,
        "modules": MODULES,
        "module_notes": MODULE_NOTES,
        "actions": ACTIONS,
        "readiness_bands": READINESS_BANDS,
        "setup_times": SETUP_TIMES,
        "max_modules": MAX_MODULES,
        "action_count": ACTION_COUNT,
        "storage_key": STORAGE_KEY,
        "module_routes": MODULE_ROUTES,
        "action_routes": ACTION_ROUTES,
        "cta": {"label": "Build my Street Banker plan", "href": "/plan"},
        "reset_label": "Reset EQ",
        # What the panel reads before a single line of script has run. The
        # server paints the same plan the browser would, so the first frame
        # is never a placeholder that the page then corrects.
        "default_plan": build_plan(default_values(), DEFAULT_PRESET),
        "default_query": plan_query(default_values(), DEFAULT_PRESET),
    }


def plan_query(values, preset_id=None):
    """The /plan query string for a set of values - built here so the
    server-rendered links and the ones the browser rewrites are the same
    string, in the same order."""
    from urllib.parse import urlencode

    values = clean_values(values)
    # "%g" so a whole number is 10 and not 10.0, matching what the browser
    # writes into the same link.
    pairs = [(key, "%g" % values[key]) for key in CHANNEL_KEYS]
    pairs.append(("preset", preset_id or "custom"))
    return urlencode(pairs)
