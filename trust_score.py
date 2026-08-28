"""Street Banker Trust Score.

One partner-facing number that says: this artist's business is in order.
Ten factors, ten points each, every point computed from real account
state — metadata coverage, documented splits, connected statements,
consented fan data, release readiness, sync clearance, press kit,
deal hygiene, tracked promo, and catalog depth. Factors under 5 are
blockers, and every blocker names its fix.
"""

import db as store
import links_engine
import links_store as mls


def _pts(value, full):
    if full <= 0:
        return 0
    return min(round(10 * value / full), 10)


def _pulse_pts(user_id):
    """Live-verifiable public presence: Spotify profile linked via Artist
    Pulse (5), with real followers on record (3) and growth tracked (2)."""
    if store.get_pulse_profile(user_id) is None:
        return 0
    snaps = store.list_pulse_snapshots(user_id)
    latest = snaps[-1] if snaps else {}
    return (5 + (3 if latest.get("followers", 0) > 0 else 0)
            + (2 if len(snaps) >= 2 else 0))


def calculate(user_id):
    tracks = store.get_catalog_tracks(user_id)
    with_isrc = sum(1 for t in tracks if (t.get("meta") or {}).get("isrc"))
    deals = store.list_deals(user_id)
    split_deals = [d for d in deals if d["deal_type"] == "split"
                   and d["status"] == "signed"]
    statements = store.get_statements(user_id)
    fans = mls.list_fans(user_id)
    campaigns = [c for c in mls.list_campaigns(user_id) if not c.get("archived_at")]
    scores = [links_engine.calculate_street_banker_score(
        c, mls.get_destinations(c["id"]))["total"] for c in campaigns]
    best_score = max(scores) if scores else 0
    packs = store.list_sync_packs(user_id)
    cleared_packs = [p for p in packs if p["master_status"] == "cleared"
                     and p["publishing_status"] == "cleared"]
    epk = store.get_epk(user_id) or {}
    epk_data = epk.get("data") or {}
    variants = []
    for c in campaigns:
        variants.extend(mls.list_variants(c["id"]))

    factors = [
        ("Metadata coverage", _pts(with_isrc, max(len(tracks), 1)) if tracks else 0,
         "Add catalog tracks — ISRCs auto-pull and close this gap."),
        ("Splits documented", 10 if split_deals else (5 if deals else 0),
         "Generate and sign split agreements in the Deal Room."),
        ("Statements connected", 10 if statements else 0,
         "Upload a royalty statement so income claims are verifiable."),
        ("Fan data consented", 10 if fans else 0,
         "Capture fans through your links — every signup logs consent."),
        ("Release readiness", _pts(best_score, 100),
         "Run the Clean Release checklist on your next campaign."),
        ("Sync clearance", 10 if cleared_packs else (5 if packs else 0),
         "Create a sync pack with master and publishing both cleared."),
        ("Press kit complete", _pts((3 if epk.get("photo") else 0)
                                    + (4 if epk_data.get("bio") else 0)
                                    + (3 if epk_data.get("press") else 0), 10),
         "Finish the EPK: photo, bio, and press quotes."),
        ("Deal hygiene", 10 if any(d["status"] == "signed" for d in deals)
         else (5 if deals else 0),
         "Track your agreements on the Deal Room board."),
        ("Promo attribution", 10 if variants else (5 if campaigns else 0),
         "Create campaign variants so every promo channel is measured."),
        ("Catalog depth", _pts(len(tracks) + len(campaigns), 6),
         "Keep releasing — depth compounds trust."),
        ("Verified platform presence", _pulse_pts(user_id),
         "Link your Spotify profile on Artist Pulse — partners can verify "
         "your numbers are real."),
    ]

    # Eleven factors of 10; normalized so the total stays a 0-100 score.
    total = round(sum(pts for _, pts, _ in factors) * 100 / (len(factors) * 10))
    blockers = [(name, pts, note) for name, pts, note in factors if pts < 5]
    if total >= 80:
        verdict = "Partner-ready"
    elif total >= 55:
        verdict = "Building trust"
    else:
        verdict = "Getting started"
    # Remember today's reading. Guarded: a history write must never be
    # the reason a page fails to render.
    try:
        store.record_score(user_id, "trust", total, {"factors": [[f[0], f[1]] for f in factors]})
    except Exception:
        pass
    return {"total": total, "factors": factors, "blockers": blockers,
            "verdict": verdict}
