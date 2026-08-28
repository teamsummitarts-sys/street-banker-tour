"""Config-driven data for the Smart Links hub.

A smart link is one shareable URL that fans out to every platform a
release lives on, with per-link click tracking. Links live in a
module-level store so creating one at runtime persists for the session;
everything the page renders comes from get_links_data().
"""

from royalty_data import platform_logo_key

# Default destination platforms offered when building a link.
LINK_PLATFORMS = ["Spotify", "Apple Music", "YouTube", "TikTok", "SoundCloud"]

# Seeded example links. clicks are illustrative demo figures.
_smart_links = [
    {
        "id": "lnk-1", "title": "Midnight Drive", "slug": "midnight-drive",
        "platforms": ["Spotify", "Apple Music", "YouTube"], "clicks": 4820, "created": "2026-05-12",
    },
    {
        "id": "lnk-2", "title": "Neon Dreams", "slug": "neon-dreams",
        "platforms": ["Spotify", "Apple Music", "YouTube", "TikTok"], "clicks": 3110, "created": "2026-06-01",
    },
    {
        "id": "lnk-3", "title": "Digital Paradise", "slug": "digital-paradise",
        "platforms": ["Spotify", "Apple Music"], "clicks": 1290, "created": "2026-06-20",
    },
]

_link_seq = len(_smart_links)

BASE_DOMAIN = "royaltysweep.co/l"


def _slugify(title):
    slug = "".join(c if c.isalnum() or c == " " else "" for c in (title or "").lower())
    return "-".join(slug.split()) or "untitled"


def _decorate(link):
    return {
        **link,
        "url": f"{BASE_DOMAIN}/{link['slug']}",
        "platform_logos": [
            {"name": p, "logo": platform_logo_key(p)} for p in link["platforms"]
        ],
    }


def create_smart_link(title, platforms):
    global _link_seq
    if not title or not platforms:
        return None
    _link_seq += 1
    link = {
        "id": f"lnk-{_link_seq}",
        "title": title.strip(),
        "slug": _slugify(title),
        "platforms": [p for p in platforms if p in LINK_PLATFORMS],
        "clicks": 0,
        "created": "2026-07-04",
    }
    if not link["platforms"]:
        return None
    _smart_links.insert(0, link)
    return _decorate(link)


def reset_smart_links_state():
    """Test helper: restore the seeded links."""
    global _link_seq
    _smart_links[:] = [l for l in _smart_links if l["id"] in ("lnk-1", "lnk-2", "lnk-3")]
    _link_seq = 3


def get_links_data(demo=False):
    """`demo` decides whether the seeded example links are included.

    The three seeds carry invented click counts (4,820 / 3,110 / 1,290)
    and get summed into the headline band on /links - "Total Clicks
    9,220", top performer "Midnight Drive". A real artist reads that as
    their own reach. Their genuine links already render above it from
    store.get_db_links() and mls.list_campaigns(), so the seeds were
    contributing nothing except a misleading total.

    Defaults to False so a caller that forgets the flag gets an honest
    empty summary rather than somebody else's numbers.
    """
    links = [_decorate(l) for l in (_smart_links if demo else [])]
    total_clicks = sum(l["clicks"] for l in links)
    top = max(links, key=lambda l: l["clicks"]) if links else None
    return {
        "links": links,
        "platforms": LINK_PLATFORMS,
        "base_domain": BASE_DOMAIN,
        "summary": {
            "total_links": len(links),
            "total_clicks": total_clicks,
            "top_title": top["title"] if top else "—",
            "top_clicks": top["clicks"] if top else 0,
        },
    }
