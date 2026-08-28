"""What past rollouts actually converted, so the next one can start there.

Rollout Engine measures this properly already. Every post gets its own
Street Banker Links variant, named `rollout_{platform}_{phase}_{date}`
and carrying `utm_source={platform}`, so every click and every fan signup
is attributable to a platform and a release phase.

Then `rollout_engine.next_action` finishes with:

    "Rollout is live — watch the performance page for what converts."

...and the generator that plans the next one takes no performance
argument at all. The app told the artist to watch what converts and then
did not watch it itself. The next rollout's platform list came from
whichever checkboxes happened to be ticked.

The good news is that nothing needs migrating. `clear_posts` deletes
`ro_posts` on regenerate, but it never touches `ml_variants`, so the
variant names and their events survive every regeneration - the whole
history is already on disk, going back to the first rollout ever run.

Two rules this module keeps:

  It refuses to speak on thin evidence. A platform with four clicks
  is not a finding, it is noise, and saying otherwise would teach an
  artist to trust a number that cannot bear it.

  It reports rates, not totals. The platform that got the most clicks is
  usually just the platform that got the most posts.
"""

# Below this many visits on a platform, there is nothing to say about it.
MIN_VISITS = 25

# And below this many across everything, there is nothing to say at all.
MIN_TOTAL_VISITS = 60

# A platform has to beat the average by this much before it is worth
# calling a winner rather than noise.
EDGE = 1.15


def _parse(name):
    """`rollout_instagram_reels_teaser_2026-08-05` -> (platform, phase).

    The date is deliberately dropped: what converted matters, when it was
    posted is a different question this module does not answer.
    """
    if not name or not name.startswith("rollout_"):
        return None, None
    body = name[len("rollout_"):]
    bits = body.rsplit("_", 1)          # trailing date
    if len(bits) != 2:
        return None, None
    head = bits[0]
    parts = head.rsplit("_", 1)         # platform may itself hold "_"
    if len(parts) != 2:
        return None, None
    return parts[0], parts[1]


def gather(campaigns, variants_for, stats_for):
    """Roll every past rollout up by platform and by phase.

    The callables are injected so this stays a pure function over data -
    testable without a database, which is the only way to be sure the
    thresholds behave.
    """
    plat, phase = {}, {}
    for c in campaigns:
        cid = c.get("id")
        if not cid:
            continue
        stats = stats_for(cid) or {}
        for v in variants_for(cid) or []:
            if (v.get("utm_medium") or "") != "rollout":
                continue
            p, ph = _parse(v.get("name"))
            # utm_source is the platform's other home; prefer it when the
            # name has been edited into something unparseable.
            p = (v.get("utm_source") or p or "").strip()
            if not p:
                continue
            s = stats.get(v["id"], {})
            visits = s.get("page_view", 0)
            clicks = s.get("service_click", 0)
            fans = s.get("fan_signup", 0)
            for bucket, key in ((plat, p), (phase, ph)):
                if not key:
                    continue
                b = bucket.setdefault(key, {"visits": 0, "clicks": 0,
                                            "fans": 0, "posts": 0})
                b["visits"] += visits
                b["clicks"] += clicks
                b["fans"] += fans
                b["posts"] += 1
    return plat, phase


def _rate(b):
    return (b["clicks"] / b["visits"]) if b["visits"] else 0.0


def summarise(bucket, label):
    """Ranked rows plus a finding, or None when the evidence is too thin."""
    total_visits = sum(b["visits"] for b in bucket.values())
    rows = []
    for key, b in bucket.items():
        rows.append({
            "key": key, "visits": b["visits"], "clicks": b["clicks"],
            "fans": b["fans"], "posts": b["posts"],
            "rate": round(_rate(b), 4),
            "enough": b["visits"] >= MIN_VISITS,
        })
    rows.sort(key=lambda r: (r["enough"], r["rate"]), reverse=True)

    if total_visits < MIN_TOTAL_VISITS:
        return {
            "rows": rows, "finding": None, "confident": False,
            "note": "Not enough traffic yet to tell %s apart — %d visits "
                    "across all rollouts so far. This fills in on its own."
                    % (label, total_visits),
        }

    solid = [r for r in rows if r["enough"]]
    if len(solid) < 2:
        return {
            "rows": rows, "finding": None, "confident": False,
            "note": "Only one %s has enough traffic to judge. Nothing to "
                    "compare it against yet." % label[:-1],
        }

    avg = sum(r["rate"] for r in solid) / len(solid)
    best = solid[0]
    if avg <= 0 or best["rate"] < avg * EDGE:
        return {
            "rows": rows, "finding": None, "confident": True,
            "note": "No %s is clearly ahead — they convert within a few "
                    "points of each other." % label[:-1],
        }
    return {
        "rows": rows,
        "finding": {
            "key": best["key"], "rate": best["rate"],
            "visits": best["visits"], "clicks": best["clicks"],
            "lift": round((best["rate"] / avg - 1) * 100),
        },
        "confident": True,
        "note": "%s converts %d%% better than your average, measured over "
                "%d visits." % (best["key"], round((best["rate"] / avg - 1) * 100),
                                best["visits"]),
    }


def report(campaigns, variants_for, stats_for):
    plat, phase = gather(campaigns, variants_for, stats_for)
    return {
        "platforms": summarise(plat, "platforms"),
        "phases": summarise(phase, "phases"),
        "measured": bool(plat),
    }


def suggested_platforms(rep, available, fallback):
    """Which platform boxes to pre-tick on the next rollout.

    Only ever a starting point, and only when the evidence supports it.
    With nothing measured this returns the same default it always did, so
    a new account behaves exactly as before.
    """
    p = rep.get("platforms") or {}
    if not p.get("confident"):
        return list(fallback)
    keys = [r["key"] for r in p["rows"] if r["enough"] and r["key"] in available]
    return keys or list(fallback)


def next_action_line(rep):
    """Something true to say instead of 'watch the performance page'."""
    p = (rep.get("platforms") or {}).get("finding")
    ph = (rep.get("phases") or {}).get("finding")
    if p:
        return ("Rollout is live. Across your past rollouts %s converts %d%% "
                "better than average — worth weighting next time."
                % (p["key"], p["lift"]))
    if ph:
        return ("Rollout is live. Your %s phase converts %d%% better than "
                "average across past rollouts." % (ph["key"], ph["lift"]))
    return None
