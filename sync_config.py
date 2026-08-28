"""Config-driven data for the Sync / Licensing page.

Sync licensing = placing recordings in film, TV, ads, games, and
trailers. The app doesn't model sync deals, so the placements, incoming
requests, and open briefs here are illustrative demo data — but each one
references a real song title from the catalog so the page stays
consistent with the rest of the app. Deal fees are illustrative.
"""

from royalty_data import get_songs

MEDIA_TYPES = ["Film", "TV", "Advertising", "Video Game", "Trailer"]

STATUS_TONE = {
    "Live": "border-green-500/20 bg-green-500/10 text-green-400",
    "Pending": "border-amber-500/20 bg-amber-500/10 text-amber-400",
    "Negotiating": "border-blue-500/20 bg-blue-500/10 text-blue-400",
    "Expired": "border-gray-500/20 bg-gray-500/10 text-gray-300",
    "New": "border-amber-500/20 bg-amber-500/10 text-amber-400",
    "In Review": "border-blue-500/20 bg-blue-500/10 text-blue-400",
    "Countered": "border-purple-500/20 bg-purple-500/10 text-purple-400",
}


def _titles():
    titles = [s.title for s in get_songs()]
    # Guard against an empty catalog so indexing stays safe.
    return titles or ["Untitled"]


def get_sync_data():
    t = _titles()

    def title(i):
        return t[i % len(t)]

    placements = [
        {"id": "sync-1", "song": title(0), "project": "Midnight City (Feature Film)", "media_type": "Film",
         "licensee": "Aurora Pictures", "fee": 7500.00, "territory": "Worldwide", "term": "In perpetuity", "status": "Live"},
        {"id": "sync-2", "song": title(3), "project": "DriveElectric — EV Campaign", "media_type": "Advertising",
         "licensee": "Vantage Motors", "fee": 12000.00, "territory": "North America", "term": "1 year", "status": "Live"},
        {"id": "sync-3", "song": title(1), "project": "Neon Circuit (Streaming Series S2)", "media_type": "TV",
         "licensee": "Lumen Studios", "fee": 4200.00, "territory": "Worldwide", "term": "5 years", "status": "Negotiating"},
        {"id": "sync-4", "song": title(2), "project": "Skyline Racers (Video Game)", "media_type": "Video Game",
         "licensee": "Pixel Forge", "fee": 3000.00, "territory": "Worldwide", "term": "In perpetuity", "status": "Pending"},
    ]

    requests = [
        {"id": "req-1", "song": title(0), "requester": "Halcyon Trailers", "media_type": "Trailer",
         "offer": 5500.00, "status": "New"},
        {"id": "req-2", "song": title(4), "requester": "Indie Short Collective", "media_type": "Film",
         "offer": 900.00, "status": "In Review"},
        {"id": "req-3", "song": title(1), "requester": "Brightside Ads", "media_type": "Advertising",
         "offer": 8000.00, "status": "Countered"},
    ]

    opportunities = [
        {"id": "brief-1", "brief": "Coming-of-age indie film needs dreamy synth-pop for a night-drive montage.",
         "mood": "Nostalgic · Warm", "budget": "$3,000–6,000"},
        {"id": "brief-2", "brief": "Sportswear brand seeking high-energy electronic for a 30s hero spot.",
         "mood": "Energetic · Bold", "budget": "$10,000–20,000"},
        {"id": "brief-3", "brief": "Sci-fi game trailer wants atmospheric, tension-building instrumentation.",
         "mood": "Dark · Cinematic", "budget": "$2,000–5,000"},
    ]

    live_income = round(sum(p["fee"] for p in placements if p["status"] == "Live"), 2)
    pipeline = round(sum(p["fee"] for p in placements if p["status"] in ("Pending", "Negotiating")), 2)

    return {
        "summary": {
            "sync_income": live_income,
            "pipeline_value": pipeline,
            "active_placements": sum(1 for p in placements if p["status"] in ("Live", "Pending", "Negotiating")),
            "open_requests": len(requests),
        },
        "placements": placements,
        "requests": requests,
        "opportunities": opportunities,
        "status_tone": STATUS_TONE,
    }
