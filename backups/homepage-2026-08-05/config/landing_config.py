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

        # The public header. Every hash destination is written /#name rather
        # than #name: the header renders on eleven public pages, and a bare
        # #platform on /rollout scrolls to nothing. Every destination is
        # reachable without an account: the old nav pointed Platform at /overview and the CTA at
        # /recovery, both of which bounce a visitor to a login wall for
        # asking what the product is.
        "nav": {
            "logo": {"primary": "STREET BANKER",
                     "secondary": "THE ARTIST OPERATING SYSTEM"},
            "links": [
                {"label": "Platform", "href": "/#platform"},
                {"label": "AI Artist Twin", "href": "/#artist-twin-section"},
                {"label": "Creative + Rollout", "href": "/#creative-studio"},
                {"label": "Royalty Sweep", "href": "/#royalty-sweep"},
                {"label": "Product tour", "href": "/product-tour"},
                {"label": "For Labels", "href": "/services"},
            ],
            # The drawer names the two studios separately, because on a
            # phone there is room to say what "Creative + Rollout" means.
            "drawer_links": [
                {"label": "Platform", "href": "/#platform"},
                {"label": "AI Artist Twin", "href": "/#artist-twin-section"},
                {"label": "Creative Studio", "href": "/#creative-studio"},
                {"label": "Rollout Engine", "href": "/#rollout-engine"},
                {"label": "Royalty Sweep", "href": "/#royalty-sweep"},
                {"label": "Metadata Passport", "href": "/#metadata-passport"},
                {"label": "Product tour", "href": "/product-tour"},
                {"label": "For Labels", "href": "/services"},
            ],
            "login": {"label": "Log in", "href": "/login"},
            "cta": {"label": "Run a Free Catalog Sweep",
                    "short": "Free Sweep", "href": "/catalog-sweep"},
        },

        # Section 2. Copy is live HTML in the template; this is the one
        # place it is written down. The CTAs both land somewhere a
        # signed-out visitor can actually use - the old pair pointed at
        # /recovery and /overview, which are behind the login gate.
        "hero": {
            "eyebrow": "STREET BANKER · THE ARTIST OPERATING SYSTEM",
            "headline": ["BUILD THE RELEASE.", "OWN THE MOMENT."],
            "support": ("Street Banker brings creative tools, rollout "
                        "intelligence, artist development, rights "
                        "management, fan data, and royalty recovery into "
                        "one platform."),
            "ctas": [
                {"label": "Explore Street Banker", "href": "#platform",
                 "variant": "primary"},
                {"label": "Run a Royalty Sweep", "href": "/catalog-sweep",
                 "variant": "outline"},
            ],
            # One photograph, two crops: a wide editorial frame for
            # desktop and a band-first one for phones, so `cover` never
            # decides which musician gets thrown off the edge.
            "image": {
                "wide": "/static/img/hero-band-wide",
                "tall": "/static/img/hero-band-tall",
                "wide_widths": [900, 1100, 1342],
                "tall_widths": [640, 900],
                "alt": ("Band rehearsing while release artwork is "
                        "developed inside a working music studio."),
            },
        },

        # Retired with the homepage rebuild: "lanes" (now Section 6,
        # lanes_config), "sweep" (Section 9, sweep_config), "tools" - the
        # Signature Tools strip, whose five links all went into the login
        # wall - and "band_image" + "final_cta", the old closing pair,
        # replaced by the trust band and Section 12 in closing_config.
        # Sections 3-12 each own their own config module now, so this file
        # holds only what is still rendered: the header, the hero and the
        # footer.

        # The footer. Five columns, and every href in it answers a
        # signed-out visitor: the previous one sent seven of its fifteen
        # links (/overview, /recovery, /artist-twin, /roster, /audience,
        # /capital, /network) straight into the login wall. The social row
        # now carries only the account that exists - x.com, youtube.com and
        # linkedin.com were the bare domains, not profiles.
        "footer": {
            "logo": {"primary": "STREET BANKER",
                     "secondary": "The Artist Operating System"},
            "description": ("One connected system to build, protect, "
                            "distribute, promote and grow the work."),
            "columns": [
                {"title": "Platform", "links": [
                    {"label": "Product tour", "href": "/product-tour"},
                    {"label": "AI Artist Twin", "href": "/artist-twin/start"},
                    {"label": "Creative Studio", "href": "/creative-studio"},
                    {"label": "Rollout Engine", "href": "/rollout"},
                    {"label": "Royalty Sweep", "href": "/royalty-sweep"},
                    {"label": "Global Distribution", "href": "/distribution"},
                    {"label": "Metadata Passport", "href": "/metadata"},
                    {"label": "Smart Links", "href": "/product-tour/smart-link"},
                ]},
                {"title": "Solutions", "links": [
                    {"label": "Start a plan", "href": "/start"},
                    {"label": "Find your lane", "href": "/lanes"},
                    {"label": "Free catalog sweep", "href": "/catalog-sweep"},
                    {"label": "For labels", "href": "/services"},
                ]},
                {"title": "Trust", "links": [
                    {"label": "Artist control policy", "href": "/artist-control"},
                    {"label": "How we use AI", "href": "/ai"},
                    {"label": "Privacy", "href": "/privacy"},
                    {"label": "Terms", "href": "/terms"},
                ]},
                {"title": "Company", "links": [
                    {"label": "About", "href": "/services"},
                    {"label": "Contact", "href": "/submit"},
                ]},
                {"title": "Account", "links": [
                    {"label": "Create an account", "href": "/signup"},
                    {"label": "Log in", "href": "/login"},
                    {"label": "Reset password", "href": "/forgot"},
                ]},
            ],
            "socials": [
                {"label": "Instagram",
                 "href": "https://instagram.com/summitartsgroup"},
            ],
            "copyright": "© 2026 Street Banker LLC. All rights reserved.",
        },
    }
