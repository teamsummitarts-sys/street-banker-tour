"""Config-driven data for the Cover / Artwork generator.

Everything the generator offers -- colorways, layout templates, fonts,
aspect presets -- is defined here so the template holds no hard-coded
options. Quick-fill titles are pulled from the live catalog. The actual
cover is composed client-side as SVG (no external dependency), and the
/artwork/generate endpoint is a documented seam where an AI image model
can be dropped in later behind the same call.
"""

from royalty_data import get_songs

# Each colorway is two gradient stops plus an accent and text color.
COLORWAYS = [
    {"id": "midnight", "name": "Midnight", "from": "#1e1b4b", "to": "#0f172a", "accent": "#eab308", "text": "#ffffff"},
    {"id": "ember", "name": "Ember", "from": "#7f1d1d", "to": "#18181b", "accent": "#f59e0b", "text": "#fff7ed"},
    {"id": "vapor", "name": "Vapor", "from": "#831843", "to": "#1e3a8a", "accent": "#f0abfc", "text": "#ffffff"},
    {"id": "forest", "name": "Forest", "from": "#064e3b", "to": "#0c0a09", "accent": "#34d399", "text": "#ecfdf5"},
    {"id": "gold", "name": "Gold Noir", "from": "#292524", "to": "#0c0a09", "accent": "#fbbf24", "text": "#fafaf9"},
    {"id": "ice", "name": "Ice", "from": "#0e7490", "to": "#0f172a", "accent": "#67e8f9", "text": "#f0f9ff"},
]

# Layout templates control where the title/artist sit and the accent motif.
TEMPLATES = [
    {"id": "centered", "name": "Centered", "align": "center", "motif": "ring"},
    {"id": "bottom-bar", "name": "Bottom Bar", "align": "bottom", "motif": "bar"},
    {"id": "stacked", "name": "Stacked Left", "align": "left", "motif": "lines"},
    {"id": "minimal", "name": "Minimal", "align": "center", "motif": "none"},
]

# "google" is the css2 family parameter; those load on the page for the
# preview and get embedded (as data-URI @font-face) into PNG/SVG exports.
FONTS = [
    {"id": "grotesk", "name": "Grotesk", "stack": "'Arial Black', 'Helvetica Neue', sans-serif"},
    {"id": "serif", "name": "Editorial Serif", "stack": "Georgia, 'Times New Roman', serif"},
    {"id": "mono", "name": "Mono", "stack": "'Courier New', monospace"},
    {"id": "anton", "name": "Poster Block", "stack": "'Anton', Impact, sans-serif", "google": "Anton"},
    {"id": "bebas", "name": "Tall Caps", "stack": "'Bebas Neue', 'Arial Narrow', sans-serif", "google": "Bebas+Neue"},
    {"id": "oswald", "name": "Condensed", "stack": "'Oswald', 'Arial Narrow', sans-serif", "google": "Oswald:wght@600"},
    {"id": "playfair", "name": "Fashion Serif", "stack": "'Playfair Display', Georgia, serif", "google": "Playfair+Display:wght@700"},
    {"id": "abril", "name": "Fat Serif", "stack": "'Abril Fatface', Georgia, serif", "google": "Abril+Fatface"},
    {"id": "righteous", "name": "Retro Round", "stack": "'Righteous', sans-serif", "google": "Righteous"},
    {"id": "monoton", "name": "Neon Outline", "stack": "'Monoton', cursive", "google": "Monoton"},
    {"id": "marker", "name": "Marker", "stack": "'Permanent Marker', cursive", "google": "Permanent+Marker"},
    {"id": "special", "name": "Typewriter Grunge", "stack": "'Special Elite', 'Courier New', monospace", "google": "Special+Elite"},
    {"id": "rye", "name": "Western", "stack": "'Rye', serif", "google": "Rye"},
    {"id": "blackletter", "name": "Blackletter", "stack": "'UnifrakturMaguntia', serif", "google": "UnifrakturMaguntia"},
    {"id": "horror", "name": "Horror", "stack": "'Creepster', cursive", "google": "Creepster"},
]

ASPECTS = [
    {"id": "square", "name": "Square 1:1", "w": 1000, "h": 1000},
    {"id": "story", "name": "Story 9:16", "w": 900, "h": 1600},
    {"id": "wide", "name": "Banner 16:9", "w": 1600, "h": 900},
]

# Text-prompt mood -> palette suggestion. This is the deterministic stand-in
# the /artwork/generate seam uses today; an AI model would replace this
# mapping with a real image generation call.
MOOD_KEYWORDS = {
    "midnight": ["night", "dark", "midnight", "moody", "noir", "late"],
    "ember": ["fire", "warm", "heat", "ember", "sunset", "burn", "red"],
    "vapor": ["dream", "vapor", "retro", "neon", "80s", "synth", "pink"],
    "forest": ["nature", "green", "forest", "earth", "organic", "calm"],
    "gold": ["luxury", "gold", "rich", "premium", "classic", "elegant"],
    "ice": ["cold", "ice", "blue", "winter", "cool", "water", "clean"],
}


def get_artwork_data(account):
    songs = get_songs()
    quick_titles = [s.title for s in sorted(songs, key=lambda s: s.streams, reverse=True)[:6]]
    return {
        "artist": account["name"],
        "colorways": COLORWAYS,
        "templates": TEMPLATES,
        "fonts": FONTS,
        "aspects": ASPECTS,
        "quick_titles": quick_titles,
    }


def suggest_from_prompt(prompt):
    """The AI seam. Today this deterministically maps a text prompt to a
    colorway/template/tagline so the 'Generate from prompt' button does
    real work with no external dependency. To connect a real model,
    replace the body with a call to an image-generation API (add the
    provider + API key via environment config) and return an image URL.
    """
    text = (prompt or "").lower()
    scores = {
        cid: sum(1 for kw in words if kw in text)
        for cid, words in MOOD_KEYWORDS.items()
    }
    best = max(scores, key=scores.get)
    colorway_id = best if scores[best] > 0 else "gold"

    # Longer, punchier prompts lean bolder; short ones stay minimal.
    words = len(text.split())
    template_id = "bottom-bar" if words >= 6 else ("stacked" if words >= 3 else "minimal")

    return {
        "colorway_id": colorway_id,
        "template_id": template_id,
        "note": "Concept generated from your prompt. Connect an AI model to render full artwork.",
    }
