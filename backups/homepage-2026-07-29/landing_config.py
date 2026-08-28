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
            # The section IS the photograph: corridor of road cases behind
            # a dark scrim, copy set over it. No product screenshot here,
            # so there are no figures to label or mistake for real data.
            "background": {
                "src": "/static/img/sb-band-sweep.jpg?v=1",
                "alt": "Road cases lined along a backstage corridor",
            },
        },

        "tools": {
            "heading": "EVERYTHING BEHIND THE ARTIST.",
            "support": ("Strategy, rights, releases, campaigns, and "
                        "opportunities in one system."),
            # Every icon is a piece of studio hardware, drawn in the same
            # vocabulary as the rack units in the lanes above and the road
            # cases in the band below: knobs, faders, a patchbay, a VU
            # meter, a flight case. Stroked paths on a 20x20 grid, split on
            # "|" by the template.
            "items": [
                # One large knob, pointer turned off the panel index mark.
                # Two small knobs were tried for the "twin" reading, but a
                # side-by-side pair only fills a third of the square and
                # went weak next to the other four.
                {"name": "Artist Twin", "href": "/artist-twin",
                 "icon": "M10 3.8a6.2 6.2 0 100 12.4 6.2 6.2 0 100-12.4"
                         "|M10 10l2.6-2.6|M10 3.8V2.2"},
                # A fader bank with the scene already set.
                {"name": "Release Autopilot", "href": "/releases/autopilot",
                 "icon": "M6 4.5v11|M10 4.5v11|M14 4.5v11"
                         "|M4.4 11.5h3.2|M8.4 7.2h3.2|M12.4 9.4h3.2"},
                # A stencilled label plate with its barcode, like the ones on
                # the road cases in the artwork. Metadata is the identifier.
                # Patchbay jacks were tried first: outlined holes small
                # enough to fit three across close up at this stroke weight.
                {"name": "Metadata Passport", "href": "/metadata-passport",
                 "icon": "M3 5.5h14v9H3z"
                         "|M6.1 8v3M8.7 8v3M11.3 8v3M13.9 8v3"
                         "|M5.5 12.6h9"},
                # VU meter: the needle is what a rollout is measured on.
                {"name": "Rollout Studio", "href": "/rollout-studio",
                 "icon": "M3.6 13.4h12.8v2.8H3.6z"
                         "|M4.9 13.4a5.1 5.1 0 0110.2 0"
                         "|M10 13.4l1.8-2.5"},
                # Road case: body, grab handle, and the stencilled label
                # plate the artwork's own SB-01 cases carry. A lid seam was
                # tried and cut - at 24px it merged with the plate into one
                # thick belt. Handle stays wide and shallow so it reads as a
                # case grip rather than a padlock shackle.
                {"name": "Deal Room", "href": "/deal-room",
                 "icon": "M3.5 7h13v8h-13z"
                         "|M7.6 7V6.2a2.4 1.3 0 014.8 0V7"
                         "|M6.8 10h6.4v2.6H6.8z"},
            ],
        },

        # Full-bleed band between the tools strip and the closing statement.
        # The archive wall is the closing line as a photograph: shelves of
        # masters, catalog and merch. Shelf labels are real categories, not
        # data, so there is nothing here to mistake for a client's numbers.
        "band_image": {
            "src": "/static/img/sb-band-catalog.jpg?v=1",
            "alt": "Archive shelves of master tapes, catalog and merch, "
                   "each shelf labelled",
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
