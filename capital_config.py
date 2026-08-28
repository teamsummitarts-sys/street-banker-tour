"""Config-driven data for the Capital / monetization hub.

Houses the artist-financing concepts from the reference app: Fan Royalty
Passes, Catalog Crowdfunding, a Royalty Futures marketplace, staking
pools, and the "Roll the Dice" mini-game.

IMPORTANT: every one of these is a SIMULATED DEMO. The app moves no real
money, collects no payment, and never actually assigns, transfers, or
forfeits any real royalties. In this concept the artist would be staking
a slice of their *own* future royalties (nothing is sold to a third
party), but here it is purely an illustrative UI. Figures are illustrative.
"""

from royalty_data import get_songs


def _titles():
    return [s.title for s in get_songs()] or ["Untitled"]


def get_capital_data():
    t = _titles()

    def title(i):
        return t[i % len(t)]

    passes = {
        "release": title(0),
        "share_pct": 5,
        "term_months": 6,
        "supply": 500,
        "sold": 318,
        "price_each": 25,
    }
    passes["raised"] = passes["sold"] * passes["price_each"]

    crowdfunding = {
        "title": "Next EP — pressing + video",
        "raised": 6200,
        "goal": 10000,
        "backers": 214,
        "repay_pct": 8,
    }
    crowdfunding["pct"] = round(crowdfunding["raised"] / crowdfunding["goal"] * 100)

    futures = [
        {"id": "fut-1", "release": title(1), "share_pct": 10, "term_months": 12, "asking": 4200, "yield_est": "14%"},
        {"id": "fut-2", "release": title(3), "share_pct": 6, "term_months": 9, "asking": 2100, "yield_est": "11%"},
        {"id": "fut-3", "release": title(2), "share_pct": 8, "term_months": 18, "asking": 3000, "yield_est": "16%"},
    ]

    staking = {
        "pools": [
            {"release": title(0), "staked_pct": 15, "apy": "9%"},
            {"release": title(1), "staked_pct": 10, "apy": "7%"},
            {"release": title(4), "staked_pct": 5, "apy": "12%"},
        ],
    }
    staking["total_staked_pct"] = sum(p["staked_pct"] for p in staking["pools"])

    dice = {
        "tracks": t[:5],
        "multiplier": 2,
        "win_days": 30,
    }

    return {
        "passes": passes,
        "crowdfunding": crowdfunding,
        "futures": futures,
        "staking": staking,
        "dice": dice,
    }
