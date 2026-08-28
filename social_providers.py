"""Social publishing provider registry for Rollout Engine.

Manual mode works today: copy the caption, download the asset, post it
yourself, paste the published URL, mark it posted. API providers activate
per-platform when their credentials land in the environment — until then
they are honestly labeled placeholders, and missing credentials never
crash anything or leak client-side.
"""

import os

# (key, display name, env vars required for auto-posting)
PROVIDERS = [
    ("manual", "Manual posting", ()),
    ("meta", "Instagram / Facebook (Meta API)", ("META_APP_ID", "META_APP_SECRET")),
    ("tiktok", "TikTok Content Posting API", ("TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET")),
    ("youtube", "YouTube Data API", ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET")),
    ("x", "X / Twitter API", ("X_API_KEY", "X_API_SECRET")),
    ("threads", "Threads API", ("THREADS_APP_ID",)),
    ("linkedin", "LinkedIn API", ("LINKEDIN_CLIENT_ID",)),
    ("snapchat", "Snapchat", ("SNAP_CLIENT_ID",)),
]


def provider_status():
    """[(key, name, status)] — 'ready' if manual, 'configured' when env vars
    exist, else 'needs credentials'."""
    out = []
    for key, name, env_vars in PROVIDERS:
        if key == "manual":
            status = "ready"
        elif env_vars and all(os.environ.get(v) for v in env_vars):
            status = "configured"
        else:
            status = "needs credentials"
        out.append((key, name, status))
    return out
