"""Computed insights over real account data.

Rule-based observations — the kind a sharp manager would spot in your
numbers — each one citing the data it came from and linking to the move
it suggests. No language model, no generated fluff: if the data isn't
there, the insight isn't either.
"""

import db as store
import links_store as mls
import royalty_types


def _insight(kind, title, body, href, label):
    return {"kind": kind, "title": title, "body": body,
            "href": href, "label": label}


def build_insights(user_id):
    out = []

    # --- Money: statement concentration and streams ---------------------------
    rows = store.get_statement_rows(user_id)
    total = sum(r["amount"] for r in rows)
    if rows:
        sources = {}
        for r in rows:
            sources[r["source"]] = sources.get(r["source"], 0.0) + r["amount"]
        top_src, top_amt = max(sources.items(), key=lambda x: x[1])
        share = round(100 * top_amt / total) if total else 0
        if share >= 60 and len(sources) > 1:
            out.append(_insight("risk", "Income concentration",
                                "%s is %d%% of your reported income. One policy change "
                                "there moves most of your money — diversifying sources "
                                "is de-risking, not just growth." % (top_src, share),
                                "/royalties", "Income breakdown"))
        missing = [royalty_types.LABELS[b] for b in
                   ("publishing", "mechanical", "neighboring")
                   if royalty_types.type_report(user_id, b)["rows"] == 0]
        if missing:
            out.append(_insight("money", "Uncollected royalty streams",
                                "Your statements show zero income from: %s. These "
                                "streams exist for most released artists — absence "
                                "usually means unregistered, not unearned."
                                % ", ".join(missing),
                                "/publishing", "See what's missing"))
    else:
        out.append(_insight("start", "No income data yet",
                            "Every money insight starts with a statement upload — "
                            "recovery findings, tax summaries, and funding readiness "
                            "all compute from it.",
                            "/statements", "Upload a statement"))

    # --- Promo: what's actually converting ------------------------------------
    campaigns = [c for c in mls.list_campaigns(user_id) if not c.get("archived_at")]
    best = None
    for c in campaigns:
        n = mls.event_counts(c["id"])
        views = n.get("pageview", 0) + n.get("page_view", 0)
        clicks = n.get("click", 0) + n.get("service_click", 0)
        if views >= 10:
            rate = clicks / views
            if best is None or rate > best[1]:
                best = (c, rate, views)
    if best:
        c, rate, views = best
        out.append(_insight("promo", "Your best converter",
                            "“%s” turns %d%% of its %d visits into platform "
                            "clicks — when you spend on ads or trade features, send "
                            "that traffic here." % (c["title"], round(rate * 100), views),
                            "/links/%s/analytics" % c["id"], "Campaign analytics"))

    # --- Fans: list you own ----------------------------------------------------
    fans = mls.list_fans(user_id)
    hot = [f for f in fans if f.get("intent_score", 0) >= 60]
    if hot:
        out.append(_insight("fans", "%d high-intent fans" % len(hot),
                            "These fans pre-saved or came back repeatedly. They're "
                            "the first buyers of tickets and merch — reach them "
                            "before you reach strangers.",
                            "/links/fans", "Fan CRM"))

    # --- Growth: pulse snapshot deltas ------------------------------------------
    snaps = store.list_pulse_snapshots(user_id)
    if len(snaps) >= 2:
        first, last = snaps[0], snaps[-1]
        delta = last["followers"] - first["followers"]
        if delta != 0:
            out.append(_insight("growth", "Spotify followers %+d" % delta,
                                "From %s to %s, tracked live. Popularity is %d/100 "
                                "as of the latest snapshot."
                                % (first["day"], last["day"], last["popularity"]),
                                "/stats", "Growth history"))

    # --- Catalog hygiene ----------------------------------------------------------
    tracks = store.get_catalog_tracks(user_id)
    if tracks:
        incomplete = [t for t in tracks
                      if not ((t.get("meta") or {}).get("isrc"))]
        if incomplete:
            out.append(_insight("hygiene", "%d track%s missing identifiers"
                                % (len(incomplete), "" if len(incomplete) == 1 else "s"),
                                "Tracks without ISRCs can't be matched by collection "
                                "societies — that's how royalties end up in the "
                                "black box.",
                                "/metadata-passport", "Metadata Passport"))

    # --- Links: where fans actually click through -----------------------------
    for c in mls.list_campaigns(user_id):
        if c.get("archived_at"):
            continue
        split = mls.breakdown(c["id"], "service_key", "service_click")
        clicks = sum(n for _k, n in split)
        if clicks < 20 or not split:
            continue
        top_key, top_n = split[0]
        share = round(100 * top_n / clicks)
        if share >= 60 and len(split) > 1:
            out.append(_insight(
                "observation", "One platform dominates “%s”" % c["title"],
                "%d%% of this link's %d click-throughs go to %s — measured "
                "from your own click log. Worth knowing which door your "
                "fans actually use before you spend anywhere else."
                % (share, clicks, top_key.replace("_", " ").title()),
                "/links/%s/analytics" % c["id"], "Link analytics"))
            break  # one observation of this kind is enough

    return out
