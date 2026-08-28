"""Config-driven data for the Label Services section.

Content adapted from artiswarrecords.com (Art Is War Records / SummitArts).
No public pricing tiers exist on the source site, so services use
"request a quote / custom package" CTAs rather than invented prices.
"""

BRAND = {
    # Platform branding is Street Banker everywhere; Art Is War Records is
    # the external Shopify store's identity (linked, not the app's brand).
    "name": "Street Banker",
    "sub": "Label Services",
    "tagline": "Music Marketing, Management & Label",
    # The live Shopify store — the ecosystem's real commerce engine.
    "store_url": "https://www.artiswarrecords.com",
    "store_label": "Shop Apparel & Merch",
    "contact_email": "team.summitarts@gmail.com",
    "submissions_emails": ["team.summitarts@gmail.com", "artiswarrecords@gmail.com"],
    "consulting_contact": "Lucas Joyner",
    "socials": [
        {"label": "Facebook", "handle": "/artiswarrecords", "url": "https://facebook.com/artiswarrecords/", "logo": "other"},
        {"label": "Instagram", "handle": "@summitartsgroup", "url": "https://instagram.com/summitartsgroup", "logo": "other"},
        {"label": "YouTube", "handle": "Street Banker", "url": "https://youtube.com", "logo": "youtube"},
    ],
}

# Illustrative reach figures quoted from the source site.
DISTRIBUTION_STATS = [
    {"label": "Digital platforms", "value": "200+"},
    {"label": "National & indie retailers", "value": "2,500"},
    {"label": "E-commerce customers", "value": "3,700+"},
    {"label": "Ship-to locations", "value": "16,000"},
]

SERVICES = [
    {
        "slug": "distribution",
        "title": "Music Distribution",
        "tagline": "CDs, vinyl & digital — no setup fees.",
        "icon": "disc",
        "summary": "Full physical and digital distribution powered by our Symphonic partnership — no setup fees, real-time data, social/UGC monetization, and collection everywhere.",
        "features": [
            "No physical or digital set-up fees",
            "Digital delivery to 200+ streaming & download platforms",
            "Physical: CD & vinyl into 2,500 national and independent retailers",
            "Music video distribution",
            "Monetize TikTok, YouTube, Instagram & Facebook UGC (Content ID)",
            "Unlimited collaborator splits — everyone paid automatically",
            "Real-time analytics across platforms, including TikTok",
            "DSP playlist pitching to Spotify, Apple & YouTube",
            "Publishing administration + neighboring-rights collection",
            "Sync licensing and royalty advances available",
            "Metadata management, real-time data + optional Soundscan",
            "Distribution via SummitArts on Symphonic Distribution",
        ],
        "cta": "Start distributing",
    },
    {
        "slug": "marketing",
        "title": "Music Marketing",
        "tagline": "Reach a 200,000+ fan email list — and grow it daily.",
        "icon": "megaphone",
        "summary": "End-to-end marketing: branding, apparel, web, advertising, and promotion built to turn listeners into fans.",
        "features": [
            "Logo design with print-ready 300 DPI files",
            "In-house apparel design and production",
            "Website development with e-commerce + SEO management",
            "Print-on-demand and bulk water-based ink printing",
            "Promotional posters, stickers, and materials",
            "Multi-company promotional mailers (100s weekly, domestic & international)",
            "YouTube optimization, metatags & Google Search Console setup",
            "Targeted social media and YouTube video advertising",
            "Street team promotion at major festivals",
            "Entertainment-lawyer consulting, contracts & brand protection",
        ],
        "cta": "Plan a campaign",
    },
    {
        "slug": "management",
        "title": "Consulting & Management",
        "tagline": "Talent consulting for music artists and actors.",
        "icon": "briefcase",
        "summary": "Guidance for professional entertainment careers — from one-time consulting to full long-term management.",
        "features": [
            "Day-to-day business affairs management",
            "Advice on professional matters, long-term plans & personal decisions",
            "Meetings with clients and potential talent buyers",
            "Radio connections and publicity events",
            "Booking agents for worldwide regions",
            "Shopping current releases for licensing or deals",
            "Travel arrangements and advertising strategy",
            "Accounting and entertainment-lawyer relationships",
            "Multiple levels — one-time consulting through long-term contracts",
        ],
        "cta": "Request consulting",
    },
]


def get_service(slug):
    return next((s for s in SERVICES if s["slug"] == slug), None)


def get_label_data():
    return {"brand": BRAND, "services": SERVICES, "distribution_stats": DISTRIBUTION_STATS}
