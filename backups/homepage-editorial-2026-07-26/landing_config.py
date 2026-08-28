"""Central content config for the Street Banker homepage.

Editorial front door, not a feature directory. Seven sections only:
nav, hero, three lanes, Royalty Sweep, signature tools, final CTA,
minimal footer. Every href points at a real route; no invented client
names, partner logos, or statistics. Any figure shown inside a product
screenshot is labeled as illustrative.
"""


def get_landing_config():
    return {
        "brand": "Royalty Sweep",

        # Retired slots kept as None so the existence guards in app.py stay
        # harmless. The artwork files remain on disk and in backups/.
        "top_banner": None,
        "hero_image": None,
        "features_image": None,
        "ownership_image": None,
        "patchbay_image": None,

        "nav": {
            "logo": {"primary": "STREET BANKER",
                     "secondary": "ARTIST INFRASTRUCTURE"},
            "links": [
                {"label": "Platform", "href": "/overview"},
                {"label": "Solutions", "href": "/services"},
                {"label": "Company", "href": "/network"},
                {"label": "Resources", "href": "/reports"},
            ],
            "actions": [
                {"label": "Login", "href": "/login", "variant": "text"},
                {"label": "Start Free Scan", "href": "/recovery",
                 "variant": "primary"},
            ],
        },

        "hero": {
            "eyebrow": "ARTIST INFRASTRUCTURE",
            "headline": ["THE ARTIST", "BACK OFFICE."],
            "support": "Release music. Recover royalties. Build equity.",
            "description": ("Distribution, royalty recovery, campaign tools, "
                            "and catalog intelligence built around artist "
                            "ownership."),
            "ctas": [
                {"label": "SCAN MY CATALOG", "href": "/recovery",
                 "variant": "primary"},
                {"label": "EXPLORE THE PLATFORM", "href": "/overview",
                 "variant": "outline-dark"},
            ],
            "proof": "Distribution · Royalty Recovery · Artist Development",
            "image": {"src": "/static/img/sb-hero-photo.jpg?v=4",
                      "alt": "Artist performing to a full crowd"},
        },

        "lanes": {
            "heading": "THE THREE STREET BANKER LANES",
            "support": "Three paths. One infrastructure.",
            "cards": [
                {"label": "01 · DISTRIBUTION",
                 "headline": "RELEASE THE RECORD.",
                 "description": ("Global distribution, metadata, reporting, "
                                 "and payouts."),
                 "link": {"label": "Explore Distribution",
                          "href": "/services/distribution"},
                 "image": "/static/img/sb-lane-01.jpg?v=4"},
                {"label": "02 · DEVELOPMENT",
                 "headline": "BUILD THE ARTIST.",
                 "description": ("Campaigns, content, fan growth, and "
                                 "release strategy."),
                 "link": {"label": "Explore Development",
                          "href": "/audience"},
                 "image": "/static/img/sb-lane-02.jpg?v=4"},
                {"label": "03 · PARTNERSHIP",
                 "headline": "BUILD THE ASSET.",
                 "description": ("Label services, funding, catalog growth, "
                                 "and long-term alignment."),
                 "link": {"label": "Explore Partnership", "href": "/capital"},
                 "image": "/static/img/sb-lane-03.jpg?v=4"},
            ],
        },

        "sweep": {
            "eyebrow": "ROYALTY SWEEP",
            "headline": ["FIND WHAT YOU EARNED.", "FIX WHAT IS MISSING."],
            "description": ("Scan your catalog, identify collection gaps, "
                            "and track recovery through payout."),
            "cta": {"label": "START A FREE SCAN", "href": "/recovery"},
            "note": ("No upfront scan fee. Results depend on available "
                     "catalog and registration data."),
            # The rack enclosure holds a product view; every figure inside
            # it is labeled illustrative, never presented as real earnings.
            "image": {"src": "/static/img/sb-patchbay.jpg?v=4",
                      "alt": "Royalty Sweep signal routing: DSP, sync, merch,"
                             " fan data, catalog, and revenue on one patchbay"},
            "demo_label": "ILLUSTRATIVE DEMO DATA",
        },

        "tools": {
            "heading": "EVERYTHING BEHIND THE ARTIST.",
            "support": ("Strategy, rights, releases, campaigns, and "
                        "opportunities in one system."),
            "items": [
                {"name": "Artist Twin", "href": "/artist-twin",
                 "icon": "M10 3a3 3 0 013 3v1.2a3.2 3.2 0 010 5.6V14a3 3 0 11-6 0v-1.2a3.2 3.2 0 010-5.6V6a3 3 0 013-3z|M10 8.5v3"},
                {"name": "Release Autopilot", "href": "/releases/autopilot",
                 "icon": "M10 2.5l7 7-7 7-7-7z|M10 7v6M7 10h6"},
                {"name": "Metadata Passport", "href": "/metadata-passport",
                 "icon": "M5 3h7l3 3v11a1 1 0 01-1 1H5a1 1 0 01-1-1V4a1 1 0 011-1z|M7 9h6M7 12.5h6"},
                {"name": "Rollout Studio", "href": "/rollout-studio",
                 "icon": "M4 4.5h12v9H4z|M4 13.5l3 3M16 13.5l-3 3|M7.5 8.5l2 2 3.5-3.5"},
                {"name": "Deal Room", "href": "/deal-room",
                 "icon": "M3 7.5h14v8a1 1 0 01-1 1H4a1 1 0 01-1-1z|M7 7.5V5a1 1 0 011-1h4a1 1 0 011 1v2.5"},
            ],
        },

        # Thin full-bleed band that separates the tools strip from the
        # closing statement. No text in the artwork; nothing to click.
        "band_image": {
            "src": "/static/img/sb-band.jpg?v=1",
            "alt": "Front-of-house engineers working the desk in front of a "
                   "full arena",
        },

        "final_cta": {
            "headline": ["YOUR MUSIC IS THE PRODUCT.",
                         "YOUR CATALOG IS THE ASSET."],
            "cta": {"label": "START FREE", "href": "/signup"},
            "note": ("No upfront scan fee. You keep ownership of your music "
                     "and data."),
        },

        "footer": {
            "logo": {"primary": "STREET BANKER",
                     "secondary": "ARTIST INFRASTRUCTURE"},
            "description": ("Infrastructure for independent artists and "
                            "labels."),
            "columns": [
                {"title": "Platform", "links": [
                    {"label": "Overview", "href": "/overview"},
                    {"label": "Royalty Sweep", "href": "/recovery"},
                    {"label": "Distribution", "href": "/services/distribution"},
                    {"label": "Artist Twin", "href": "/artist-twin"},
                ]},
                {"title": "Solutions", "links": [
                    {"label": "For Artists", "href": "/overview"},
                    {"label": "For Labels", "href": "/roster"},
                    {"label": "Development", "href": "/audience"},
                    {"label": "Partnership", "href": "/capital"},
                ]},
                {"title": "Company", "links": [
                    {"label": "About", "href": "/services"},
                    {"label": "Contact", "href": "/submit"},
                    {"label": "Partners", "href": "/network"},
                ]},
                {"title": "Legal", "links": [
                    {"label": "Terms", "href": "/terms"},
                    {"label": "Privacy", "href": "/privacy"},
                    {"label": "Copyright", "href": "/privacy"},
                ]},
            ],
            "socials": [
                {"label": "Instagram",
                 "href": "https://instagram.com/summitartsgroup"},
                {"label": "X", "href": "https://x.com"},
                {"label": "YouTube", "href": "https://youtube.com"},
                {"label": "LinkedIn", "href": "https://linkedin.com"},
            ],
            "copyright": "© 2026 Street Banker LLC. All rights reserved.",
        },
    }
