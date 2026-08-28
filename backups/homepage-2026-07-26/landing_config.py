"""Central content config for the Street Banker homepage.

This is the editable source of truth for the marketing home page (the
Python equivalent of a homePageContent.js). Every label, link, card,
stat, and panel row lives here so the template holds no hard-coded copy.

Art direction: Street Banker is the white, luxury, editorial parent
brand; Royalty Sweep is the dark hardware/software recovery engine
inside it. Section hrefs point at real in-app routes (the marketing
routes like /platform don't exist), and can be re-pointed here freely.
"""


def get_landing_config():
    return {
        # Kept for the <title> and legacy references; the product name.
        "brand": "Royalty Sweep",

        # Full-width banner graphic pinned to the very top (under the nav,
        # above the hero). Carries its own headline + modules; links into the
        # app. Renders only when the file is on disk.
        "top_banner": None,

        # Full-bleed hero artwork (the user's design; headline, subcopy, and
        # the four module cards are baked into the image). Real navigation
        # renders as buttons below it.
        "hero_image": {
            "src": "/static/img/sb-hero.jpg?v=3",
            "blend": True,
            "fullbleed": True,
            "alt": "Release Music. Build Equity. — Infrastructure for the business of music: distribution, development, finance, physical, merch, and direct-to-fan systems built around artist ownership.",
            "bare": True,
            "center_buttons": True,
            "buttons_below": [
                {"label": "Start Free Scan", "href": "/overview", "variant": "primary"},
                {"label": "Distribute Your Music", "href": "/submit", "variant": "outline-dark"},
                {"label": "See How It Works", "href": "#features", "variant": "outline-dark"},
            ],
        },

        "nav": {
            "logo": {"primary": "STREET BANKER", "secondary": "ARTIST INFRASTRUCTURE"},
            "links": [
                {"label": "Platform", "href": "/overview"},
                {"label": "Distribution", "href": "/services/distribution"},
                {"label": "Solutions", "href": "#services"},
                {"label": "Resources", "href": "/reports"},
                {"label": "Company", "href": "#infrastructure"},
                {"label": "Pricing", "href": "/billing"},
            ],
            # Login only — the hero carries Start Free Scan.
            "actions": [
                {"label": "Login", "href": "/login", "variant": "text"},
            ],
        },

        "hero": {
            "eyebrow": "STREET BANKER",
            "headline": ["THE ARTIST", "BACK OFFICE", "FOR MONEY", "YOU'RE MISSING"],
            "subheadline": (
                "Street Banker's infrastructure and Royalty Sweep work end-to-end "
                "to find, collect, and protect what you've earned."
            ),
            "ctas": [
                {"label": "Start Free Scan", "href": "/overview", "variant": "primary"},
                {"label": "Distribute Your Music", "href": "/submit", "variant": "secondary"},
                {"label": "See How It Works", "href": "#features", "variant": "secondary"},
            ],
            "value_points": [
                {"icon": "shield", "title": "No Upfront Fees", "description": "We work on results, not promises."},
                {"icon": "globe", "title": "Maximum Recovery", "description": "We pursue every source, every territory."},
                {"icon": "lock", "title": "Artist-Owned System", "description": "Your masters, your data, your terms."},
            ],
        },

        "hero_visual": {
            "variant": "commandDesk",
            # Photo of the command desk; replaces the built-in SVG panel when
            # present. Whole panel links into the app. Falls back to the SVG
            # until the file is on disk.
            "image": None,
            "title": "ROYALTY SWEEP",
            "label": "COMMAND DESK",
            "center": {
                "title": "Missing Royalties Found",
                "amount": "$3,301.38",
                "delta": "+9 new matches found",
                "status": "Scan in Progress",
                "description": "Analyzing 347 sources across 192 territories.",
            },
            "connected_sources": [
                {"name": "Spotify", "logo": "spotify", "status": "Connected"},
                {"name": "Apple Music", "logo": "apple", "status": "Connected"},
                {"name": "ASCAP", "logo": "ascap", "status": "Connected"},
                {"name": "BMI", "logo": "bmi", "status": "Connected"},
                {"name": "SoundExchange", "logo": "soundexchange", "status": "Connected"},
                {"name": "YouTube Content ID", "logo": "youtube", "status": "Connected"},
                {"name": "The MLC", "logo": "mlc", "status": "Connected"},
            ],
            "recovery_opportunities": [
                {"title": "Unclaimed Royalties", "amount": "$1,250.00"},
                {"title": "Underpaid Streaming", "amount": "$876.21"},
                {"title": "Performance Royalties", "amount": "$642.17"},
                {"title": "Mechanical Royalties", "amount": "$389.00"},
                {"title": "Sync Licenses", "amount": "$144.00"},
            ],
            "recent_recoveries": [
                {"source": "ASCAP", "logo": "ascap", "amount": "$786.43", "status": "Recovered"},
                {"source": "Spotify", "logo": "spotify", "amount": "$2,500.00", "status": "Recovered"},
                {"source": "Apple Music", "logo": "apple", "amount": "$1,234.56", "status": "Recovered"},
                {"source": "BMI", "logo": "bmi", "amount": "$4,321.00", "status": "Recovered"},
                {"source": "The MLC", "logo": "mlc", "amount": "$318.00", "status": "Recovered"},
                {"source": "SoundExchange", "logo": "soundexchange", "amount": "$1,850.32", "status": "Recovered"},
            ],
            "recoveries_cta": {"label": "View All Recoveries", "href": "/recovery"},
        },

        # A single strip graphic that replaces the four feature cards. Its
        # labels/CTAs are baked in, so each quarter is a clickable region
        # (left to right) rather than a duplicate button. Drop the file at
        # this path; falls back to the built-in cards until it exists.
        "features_image": {
            "src": "/static/img/sb-engines.jpg?v=3",
            "blend": True,
            "fullbleed": True,
            "alt": "One Platform. Multiple Engines. — Distribution Engine, Artist Development, Asset Partnership, Direct-to-Fan, Catalog Engine, Backend Intelligence",
            "bare": True,
            "rows": 2,
            # Region grid mirrors the 2x3 panel layout baked into the art;
            # each panel clicks through to its real module.
            "regions": [
                {"label": "Distribution Engine", "href": "/services/distribution"},
                {"label": "Artist Development", "href": "/audience"},
                {"label": "Asset Partnership", "href": "/capital"},
                {"label": "Direct-to-Fan", "href": "/fan-club"},
                {"label": "Catalog Engine", "href": "/catalog"},
                {"label": "Backend Intelligence", "href": "/insights"},
            ],
        },

        "features": [
            {"icon": "search", "texture": "vu", "title": "Find Missing Money",
             "description": "We uncover what's unclaimed, unpaid, or unmatched.",
             "link": {"label": "Learn More", "href": "/recovery"}},
            {"icon": "link", "texture": "knob", "title": "Connect Everything",
             "description": "All platforms. All territories. One infrastructure.",
             "link": {"label": "Learn More", "href": "/connections"}},
            {"icon": "chart", "texture": "grille", "title": "Maximize Your Value",
             "description": "More data. More leverage. Higher catalog value.",
             "link": {"label": "Learn More", "href": "/valuation"}},
            {"icon": "lock", "texture": "patchbay", "title": "You Stay In Control",
             "description": "You own your catalog, connections, and future.",
             "link": {"label": "Learn More", "href": "/catalog"}},
        ],

        "lanes": {
            "label": "OUR INFRASTRUCTURE",
            "headline": "THREE LANES. ONE INFRASTRUCTURE.",
            "subheadline": (
                "Three integrated lanes, each solving a different problem: "
                "release it, grow it, own it."
            ),
            "cta": {"label": "Explore The Three Lanes", "href": "/overview"},
            # Full-bleed graphic that carries its own title + all lane detail.
            # Engagement buttons render BELOW it (the art has no empty space
            # to safely overlay). Drop the file at this exact path.
            "image": {
                "src": "/static/img/sb-distro-lanes.jpg?v=3",
            "blend": True,
            "fullbleed": True,
                "alt": "The Three Distro Lanes — 01 Distribution: release the record. 02 Development: build the artist. 03 Partnership: build the asset.",
                "bare": True,          # borderless, blends on the white page
                "rows": 3,
                # One region per rack unit, top to bottom; labels painted in
                # the art, so no text repeats below it.
                "regions": [
                    {"label": "Lane 01 — Distribution", "href": "/royalties"},
                    {"label": "Lane 02 — Development", "href": "/audience"},
                    {"label": "Lane 03 — Partnership", "href": "/capital"},
                ],
                "inset_top": "18%",
                "center_buttons": True,
                "buttons_below": [
                    {"label": "01 Distribution", "href": "/royalties", "variant": "outline-dark"},
                    {"label": "02 Development", "href": "/audience", "variant": "outline-dark"},
                    {"label": "03 Partnership", "href": "/capital", "variant": "outline-dark"},
                    {"label": "Explore The Three Lanes", "href": "/overview", "variant": "primary"},
                ],
            },
            "items": [
                {"number": "01", "title": "Distribution", "description": "Release. Collect. Report.", "href": "/royalties"},
                {"number": "02", "title": "Development", "description": "Build the artist. Grow the audience.", "href": "/audience"},
                {"number": "03", "title": "Partnership", "description": "Build assets. Create ownership.", "href": "/capital"},
            ],
            "status": [
                {"label": "Distribution", "value": "Active"},
                {"label": "Development", "value": "Active"},
                {"label": "Partnership", "value": "Active"},
            ],
        },

        "royalty_sweep": {
            "label": "ROYALTY SWEEP",
            "headline": ["THE RECOVERY ENGINE", "POWERING YOUR INFRASTRUCTURE"],
            "subheadline": (
                "Royalty Sweep is the technology layer inside Street Banker's "
                "Distribution Lane. It scans, matches, and recovers what others "
                "miss — so you keep more of what you've earned."
            ),
            "cta": {"label": "Explore Royalty Sweep", "href": "/recovery"},
            # The one and only Royalty Sweep pitch on the page — the old
            # "Recover What You're Owed" pillar was folded in here.
            "bullets": ["Full-catalog scan of DSPs, PROs & societies",
                        "Publishing, neighboring rights & mechanicals",
                        "Claims worked through to payout"],
            "engine": {
                "status_label": "Scan Complete",
                "matches_label": "Matches Found",
                "matches_value": "347",
                "sensitivity_label": "Sensitivity",
                "results_cta": {"label": "View Results", "href": "/recovery"},
            },
            # Photo panel for the right side; overlay sits in the dark
            # bottom-left area so the VU meters stay uncovered. Falls back to
            # the built-in engine rack until the file is on disk.
            "image": None,
        },

        # The record as an artist-owned system (flat-lay artwork; words are
        # in the image, navigation is real buttons).
        "ownership_image": {
            "src": "/static/img/sb-ownership.jpg?v=3",
            "blend": True,
            "fullbleed": True,
            "alt": "From Release to Ownership. — every record can expand into a real artist-owned system: merch, fan access, licensing, royalties, catalog.",
            "bare": True,
            "center_buttons": True,
            "buttons_below": [
                {"label": "Open Your Catalog", "href": "/catalog", "variant": "primary"},
                {"label": "Start a Fan Club", "href": "/fan-club", "variant": "outline-dark"},
            ],
        },

        # Signal-routing patchbay: DSP / Sync / Merch / Fan Data / Catalog /
        # Revenue all patched into one system.
        "patchbay_image": {
            "src": "/static/img/sb-patchbay.jpg?v=3",
            "blend": True,
            "fullbleed": True,
            "alt": "Patchbay — DSP, Sync, Merch, Fan Data, Catalog, and Revenue routed through one system.",
            "bare": True,
            "center_buttons": True,
            "buttons_below": [
                {"label": "Explore Royalty Sweep", "href": "/recovery", "variant": "primary"},
                {"label": "See Your Connections", "href": "/connections", "variant": "outline-dark"},
            ],
        },

                "services": {
            "label": "SERVICES & SOLUTIONS",
            "headline": "BUILT FOR EVERY STAGE OF YOUR CAREER",
            "items": [
                {"title": "Royalty Recovery", "description": "Uncollected royalties, found and filed.", "href": "/recovery"},
                {"title": "Catalog Management", "description": "Organize, protect, and maximize the value of your catalog.", "href": "/catalog"},
                {"title": "Sync & Licensing", "description": "Unlock new revenue through sync and commercial use.", "href": "/sync"},
                {"title": "Reporting & Analytics", "description": "Real-time data. Clear insights. Smarter decisions.", "href": "/reports"},
                {"title": "Infrastructure Setup", "description": "We build your system so you can focus on your art.", "href": "/services"},
            ],
        },

        "footer": {
            "logo": {"primary": "STREET BANKER", "secondary": "ARTIST INFRASTRUCTURE"},
            "description": (
                "We build the infrastructure independent artists and labels need to "
                "release, collect, and grow — on their own terms."
            ),
            "columns": [
                {"title": "Platform", "links": [
                    {"label": "Royalty Sweep", "href": "/recovery"},
                    {"label": "Three Lanes", "href": "#infrastructure"},
                    {"label": "How It Works", "href": "#features"},
                    {"label": "Integrations", "href": "/connections"},
                ]},
                {"title": "Solutions", "links": [
                    {"label": "Royalty Recovery", "href": "/recovery"},
                    {"label": "Catalog Management", "href": "/catalog"},
                    {"label": "Sync & Licensing", "href": "/sync"},
                    {"label": "Analytics", "href": "/stats"},
                ]},
                {"title": "Resources", "links": [
                    {"label": "Guides", "href": "/reports"},
                    {"label": "Case Studies", "href": "/reports"},
                    {"label": "Blog", "href": "/reports"},
                    {"label": "Support", "href": "/settings"},
                ]},
                {"title": "Company", "links": [
                    {"label": "Label Services", "href": "/services"},
                    {"label": "Shop Apparel", "href": "https://www.artiswarrecords.com"},
                    {"label": "Team", "href": "/team"},
                    {"label": "Partners", "href": "/network"},
                    {"label": "Contact", "href": "/submit"},
                ]},
            ],
            "socials": [
                {"label": "Instagram", "href": "https://instagram.com/summitartsgroup"},
                {"label": "X", "href": "https://x.com"},
                {"label": "YouTube", "href": "https://youtube.com"},
                {"label": "LinkedIn", "href": "https://linkedin.com"},
            ],
            "legal": ["Terms of Service", "Privacy Policy", "Cookie Policy"],
            "copyright": "© 2026 Street Banker LLC. All rights reserved.",
        },
    }
