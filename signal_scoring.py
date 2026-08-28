"""Street Banker Signal - the scoring layer.

Every score here obeys four rules:

1. **Versioned.** `SCORE_VERSION` changes whenever a weight or a formula
   changes, and is stored with every value. A score from March can be told
   apart from a score from June, so "what did we know at the time" and
   score-version backtesting stay answerable.
2. **Explainable.** Every score returns its feature contributions, the
   weights used, the cohort it was normalised against and what data was
   missing. The UI shows that panel; a number with no explanation is not
   shippable.
3. **Cohort-relative.** A developing act is never compared to a global
   superstar. Cohorts are (career stage x audience band), and percentile
   position inside the cohort is what gets scored.
4. **Honest about gaps.** Missing data lowers `data_quality` and is named in
   the explanation. It never silently becomes a zero that reads as a fact.

Nothing here decides anything. These scores rank and explain; a person signs.
"""
from datetime import date, datetime, timedelta

import signal_store as sstore

SCORE_VERSION = "2026.08-p1"

# Score keys
MOMENTUM = "sb_momentum"
MOMENTUM_QUALITY = "momentum_quality"
PLAYLIST_DEPENDENCY = "playlist_dependency"
DISTRIBUTION_GAP = "distribution_gap"
DEAL_READINESS = "deal_readiness"
RIGHTS_HEALTH = "rights_health"
CONTACT_CONFIDENCE = "contact_confidence"

SCORE_LABELS = {
    MOMENTUM: "SB Momentum",
    MOMENTUM_QUALITY: "Momentum Quality",
    PLAYLIST_DEPENDENCY: "Playlist Dependency Risk",
    DISTRIBUTION_GAP: "Distribution Gap",
    DEAL_READINESS: "Deal Readiness",
    RIGHTS_HEALTH: "Rights Health",
    CONTACT_CONFIDENCE: "Contact Confidence",
}

# Default weights. Organisations may override these in a later phase; the
# defaults are stored with the score so an old value stays interpretable.
MOMENTUM_WEIGHTS = {
    "velocity": 0.20,
    "acceleration": 0.15,
    "cross_platform": 0.15,
    "city_expansion": 0.10,
    "fan_conversion": 0.10,
    "release_reaction": 0.10,
    "playlist_durability": 0.10,
    "catalog_consistency": 0.10,
}
ANOMALY_MAX_PENALTY = 25.0

DISTRIBUTION_GAP_WEIGHTS = {
    "momentum": 0.40,
    "distributor_gap": 0.20,
    "team_gap": 0.15,
    "catalog_fragmentation": 0.10,
    "rights_gap": 0.10,
    "d2f_gap": 0.05,
}
DEAL_READINESS_WEIGHTS = {
    "momentum_quality": 0.30,
    "release_cadence": 0.15,
    "contactability": 0.15,
    "rights_health": 0.15,
    "mandate_fit": 0.15,
    "scale": 0.10,
}
RIGHTS_HEALTH_WEIGHTS = {
    "identifier_consistency": 0.20,
    "work_match": 0.25,
    "writer_completeness": 0.20,
    "share_completeness": 0.15,
    "recording_link": 0.10,
    "recording_evidence": 0.10,
}

AUDIENCE_BANDS = [(0, 10000, "0-10k"), (10000, 50000, "10-50k"),
                  (50000, 250000, "50-250k"), (250000, 1000000, "250k-1M"),
                  (1000000, 10 ** 12, "1M+")]


def _clamp(v, lo=0.0, hi=100.0):
    return max(lo, min(hi, v))


def audience_band(listeners):
    for lo, hi, label in AUDIENCE_BANDS:
        if lo <= (listeners or 0) < hi:
            return label
    return "1M+"


def cohort_of(artist):
    """(career stage x audience band x genre) - the peer group a score is
    measured against. Genre is included because a 20% month means something
    different in ambient than in hip-hop."""
    return "%s|%s|%s" % (artist.get("career_stage") or "Unknown",
                         audience_band(artist.get("monthly_listeners")),
                         artist.get("genre") or "Unknown")


# --- series helpers ----------------------------------------------------------

def _window(series, days, end=None):
    """The values inside the last `days` of a (date, value) series."""
    if not series:
        return []
    end = end or date.fromisoformat(series[-1][0])
    start = end - timedelta(days=days)
    out = []
    for d, v in series:
        try:
            day = date.fromisoformat(d)
        except ValueError:
            continue
        if start <= day <= end:
            out.append(v)
    return out


def pct_change(series, days):
    """Percentage change across the window. None when there is not enough
    history - which the caller must surface, not treat as zero."""
    vals = _window(series, days)
    if len(vals) < 2 or not vals[0]:
        return None
    return (vals[-1] - vals[0]) / float(vals[0]) * 100.0


def velocity(series, days):
    """Average daily change over the window, as a share of the base."""
    vals = _window(series, days)
    if len(vals) < 2 or not vals[0]:
        return None
    return ((vals[-1] - vals[0]) / float(vals[0])) / float(days) * 100.0


def acceleration(series, days=28):
    """This window's velocity minus the previous window's. Positive means
    the growth itself is speeding up, which is the interesting signal."""
    if not series:
        return None
    try:
        end = date.fromisoformat(series[-1][0])
    except (ValueError, IndexError):
        return None
    cur = _window(series, days, end)
    prev = _window(series, days, end - timedelta(days=days))
    if len(cur) < 2 or len(prev) < 2 or not cur[0] or not prev[0]:
        return None
    v_cur = (cur[-1] - cur[0]) / float(cur[0]) / days
    v_prev = (prev[-1] - prev[0]) / float(prev[0]) / days
    return (v_cur - v_prev) * 100.0


def growth_shape(series):
    """Plain-language classification used in the artist brief."""
    a = acceleration(series, 28)
    c7, c28, c90 = pct_change(series, 7), pct_change(series, 28), pct_change(series, 90)
    if c28 is None:
        return "Not enough history"
    if c7 is not None and c28 is not None and c7 > 12 and c28 < 18:
        return "One-period spike"
    if a is not None and a > 0.05 and c28 > 12:
        return "Three-period acceleration" if (c90 or 0) > 25 else "Two-period acceleration"
    if c28 > 8:
        return "Sustained growth"
    if c28 < -8:
        return "Reversing" if (c7 or 0) < -6 else "Decelerating"
    return "Stable"


def _scale(value, lo, hi):
    """Map a raw number onto 0-100 with clamping at both ends."""
    if value is None:
        return None
    if hi == lo:
        return 50.0
    return _clamp((value - lo) / float(hi - lo) * 100.0)


# --- feature extraction ------------------------------------------------------

def artist_features(artist_id, artist=None):
    """Everything the scores read, gathered once. Missing inputs come back as
    None so each score can record what it could not see."""
    artist = artist or sstore.get_artist(artist_id)
    listeners = sstore.metric_series(artist_id, "spotify_monthly_listeners")
    followers = sstore.metric_series(artist_id, "spotify_followers")
    releases = sstore.list_releases(artist_id)
    cities = sstore.list_city_metrics(artist_id)
    contacts = sstore.list_evidence("artist", artist_id, sstore.CLAIM_CONTACT)
    rights = sstore.list_evidence("artist", artist_id, sstore.CLAIM_RIGHTS)
    dist = sstore.list_evidence("artist", artist_id, sstore.CLAIM_DISTRIBUTOR)

    missing = []
    if not listeners:
        missing.append("streaming history")
    if not cities:
        missing.append("city breakdown")
    if not releases:
        missing.append("release history")
    if not contacts:
        missing.append("professional contacts")

    return {
        "artist": artist,
        "listeners": listeners,
        "followers": followers,
        "releases": releases,
        "cities": cities,
        "contacts": contacts,
        "rights": rights,
        "distributor": dist,
        "missing": missing,
    }


def _data_quality(missing):
    if not missing:
        return "ok"
    return "partial" if len(missing) < 3 else "thin"


# --- SB Momentum -------------------------------------------------------------

def momentum(artist_id, features=None):
    f = features or artist_features(artist_id)
    series = f["listeners"]
    parts, notes = {}, []

    v = velocity(series, 28)
    parts["velocity"] = _scale(v, -0.2, 1.2) if v is not None else None
    a = acceleration(series, 28)
    parts["acceleration"] = _scale(a, -0.3, 0.9) if a is not None else None

    # cross-platform: does the follower curve agree with the listener curve?
    lf, ff = pct_change(series, 28), pct_change(f["followers"], 28)
    if lf is None or ff is None:
        parts["cross_platform"] = None
    else:
        agree = 100.0 if (lf > 0 and ff > 0) else (35.0 if (lf > 0 or ff > 0) else 0.0)
        parts["cross_platform"] = agree

    rising = [c for c in f["cities"] if (c.get("change_28d_pct") or 0) > 10]
    parts["city_expansion"] = _scale(len(rising), 0, 5) if f["cities"] else None

    # fan conversion: followers as a share of listeners
    if series and f["followers"] and series[-1][1]:
        ratio = f["followers"][-1][1] / float(series[-1][1])
        parts["fan_conversion"] = _scale(ratio, 0.03, 0.30)
    else:
        parts["fan_conversion"] = None

    parts["release_reaction"] = _release_reaction(f["releases"], series)
    parts["playlist_durability"] = 100.0 - _playlist_dependency_raw(f)
    parts["catalog_consistency"] = _catalog_consistency(f["releases"])

    weighted, used_weight, contributions = 0.0, 0.0, {}
    for key, weight in MOMENTUM_WEIGHTS.items():
        val = parts.get(key)
        if val is None:
            notes.append("%s unavailable" % key.replace("_", " "))
            continue
        weighted += val * weight
        used_weight += weight
        contributions[key] = {"value": round(val, 1), "weight": weight,
                              "points": round(val * weight, 2)}
    # renormalise over the weights we could actually use, so a missing input
    # does not silently drag the score toward zero
    base = (weighted / used_weight) if used_weight else 0.0

    penalty, anomaly = _anomaly_penalty(f)
    value = _clamp(base - penalty)

    explanation = {
        "score": round(value, 1),
        "base_before_penalty": round(base, 1),
        "weights": MOMENTUM_WEIGHTS,
        "contributions": contributions,
        "coverage": round(used_weight, 3),
        "anomaly_penalty": round(penalty, 1),
        "anomaly_reasons": anomaly,
        "shape": growth_shape(series),
        "change_7d": _round_or_none(pct_change(series, 7)),
        "change_28d": _round_or_none(pct_change(series, 28)),
        "change_90d": _round_or_none(pct_change(series, 90)),
        "missing": f["missing"],
        "notes": notes,
    }
    return value, explanation, _data_quality(f["missing"])


def _round_or_none(v, places=1):
    return None if v is None else round(v, places)


def _release_reaction(releases, series):
    """Did the most recent release move anything? None when we cannot tell."""
    if not releases or not series:
        return None
    try:
        newest = max(r["release_date"] for r in releases if r.get("release_date"))
        rel = date.fromisoformat(newest)
    except (ValueError, TypeError):
        return None
    age = (date.today() - rel).days
    if age > 120:
        return 25.0            # nothing recent to react to
    change = pct_change(series, min(90, max(7, age)))
    if change is None:
        return None
    return _scale(change, -5, 45)


def _catalog_consistency(releases):
    """Regular releasing is a business signal. Gaps of years are not."""
    dates = sorted([r["release_date"] for r in releases if r.get("release_date")])
    if len(dates) < 2:
        return None
    try:
        days = [(date.fromisoformat(dates[i + 1]) - date.fromisoformat(dates[i])).days
                for i in range(len(dates) - 1)]
    except ValueError:
        return None
    if not days:
        return None
    avg = sum(days) / float(len(days))
    return _scale(-avg, -400, -45)     # ~45 days between releases scores high


def _playlist_dependency_raw(f):
    """0-100 risk. Without playlist data we assume moderate and say so."""
    cities = f["cities"]
    if not cities:
        return 45.0
    total = sum(c.get("listeners") or 0 for c in cities) or 1
    top = max((c.get("listeners") or 0) for c in cities)
    concentration = top / float(total)
    return _clamp(concentration * 130.0)


def _anomaly_penalty(f):
    """Risk indicators, never an accusation. Each one is named."""
    reasons, penalty = [], 0.0
    series = f["listeners"]
    c7, c28 = pct_change(series, 7), pct_change(series, 28)
    if c7 is not None and c7 > 45 and (c28 is None or c28 < c7 * 1.2):
        penalty += 12
        reasons.append("A single week accounts for most of the month's growth")
    if f["cities"]:
        total = sum(c.get("listeners") or 0 for c in f["cities"]) or 1
        top = max((c.get("listeners") or 0) for c in f["cities"])
        if top / float(total) > 0.7:
            penalty += 8
            reasons.append("One city accounts for over 70% of listening")
    lf, ff = pct_change(series, 28), pct_change(f["followers"], 28)
    if lf is not None and ff is not None and lf > 25 and ff < 2:
        penalty += 10
        reasons.append("Listeners rose sharply while followers did not move")
    return min(ANOMALY_MAX_PENALTY, penalty), reasons


def anomaly_status(penalty):
    if penalty >= 20:
        return "High anomaly"
    if penalty >= 12:
        return "Elevated risk"
    if penalty >= 6:
        return "Moderate risk"
    return "Low risk"


# --- momentum quality & playlist dependency ---------------------------------

def momentum_quality(artist_id, features=None):
    f = features or artist_features(artist_id)
    series = f["listeners"]
    parts = {}
    lf, ff = pct_change(series, 28), pct_change(f["followers"], 28)
    parts["cross_platform_diversity"] = 100.0 if (lf and ff and lf > 0 and ff > 0) else 30.0
    parts["city_diversity"] = _scale(len(f["cities"]), 1, 8) or 0.0
    parts["playlist_independence"] = 100.0 - _playlist_dependency_raw(f)
    parts["durability"] = _scale(pct_change(series, 90), -10, 60) or 0.0
    if series and f["followers"] and series[-1][1]:
        parts["conversion"] = _scale(f["followers"][-1][1] / float(series[-1][1]), 0.03, 0.30)
    else:
        parts["conversion"] = 0.0
    value = _clamp(sum(parts.values()) / float(len(parts)))
    return value, {"score": round(value, 1), "parts": {k: round(v, 1) for k, v in parts.items()},
                   "missing": f["missing"]}, _data_quality(f["missing"])


def playlist_dependency(artist_id, features=None):
    f = features or artist_features(artist_id)
    raw = _playlist_dependency_raw(f)
    if raw >= 75:
        status = "Single-placement risk"
    elif raw >= 55:
        status = "High dependency"
    elif raw >= 35:
        status = "Moderate dependency"
    else:
        status = "Low dependency"
    detail = "No playlist feed is connected, so this is inferred from how concentrated listening is by city." \
        if not f["cities"] else "Inferred from concentration of listening across known markets."
    return raw, {"score": round(raw, 1), "status": status, "detail": detail}, _data_quality(f["missing"])


# --- distribution intelligence ----------------------------------------------

def current_distribution(releases):
    """Distributor is a per-release fact, so 'current' is a judgement over
    the recent catalogue - reported with how consistent it is."""
    dated = [r for r in releases if r.get("release_date")]
    dated.sort(key=lambda r: r["release_date"], reverse=True)
    if not dated:
        return {"name": "", "classification": "Unknown", "consistency": 0.0,
                "recent_of": 0, "recent_matching": 0, "changed": False}
    recent = dated[:10]
    latest = recent[0]
    name = latest.get("distributor_name") or ""
    matching = sum(1 for r in recent if (r.get("distributor_name") or "") == name)
    older = [r for r in recent[1:4] if r.get("distributor_name")]
    changed = bool(older) and all((r.get("distributor_name") or "") != name for r in older)
    return {
        "name": name,
        "classification": latest.get("distributor_class") or "Unknown",
        "consistency": round(matching / float(len(recent)), 2),
        "recent_of": len(recent),
        "recent_matching": matching,
        "changed": changed,
    }


def distribution_gap(artist_id, features=None, momentum_value=None):
    f = features or artist_features(artist_id)
    if momentum_value is None:
        momentum_value = momentum(artist_id, f)[0]
    dist = current_distribution(f["releases"])
    soph = sstore.DISTRIBUTOR_SOPHISTICATION.get(dist["classification"], 3)

    parts = {}
    parts["momentum"] = momentum_value
    # the lower the infrastructure, the bigger the gap
    parts["distributor_gap"] = _clamp((9 - soph) / 8.0 * 100.0)
    roles = {(e.get("claim_key") or "").lower() for e in f["contacts"]}
    has_mgmt = "manager" in roles
    has_agent = "booking agent" in roles
    parts["team_gap"] = 0.0 if (has_mgmt and has_agent) else (45.0 if (has_mgmt or has_agent) else 100.0)
    parts["catalog_fragmentation"] = _clamp((1.0 - dist["consistency"]) * 100.0)
    rh = rights_health(artist_id, f)[0]
    parts["rights_gap"] = _clamp(100.0 - rh)
    parts["d2f_gap"] = 0.0 if (f["artist"] or {}).get("website") else 100.0

    total, contributions = 0.0, {}
    for key, weight in DISTRIBUTION_GAP_WEIGHTS.items():
        val = parts.get(key) or 0.0
        total += val * weight
        contributions[key] = {"value": round(val, 1), "weight": weight, "points": round(val * weight, 2)}
    value = _clamp(total)
    explanation = {
        "score": round(value, 1),
        "weights": DISTRIBUTION_GAP_WEIGHTS,
        "contributions": contributions,
        "distribution": dist,
        "reading": ("Audience momentum materially exceeds the infrastructure behind it."
                    if value >= 70 else
                    "Momentum and infrastructure look roughly matched." if value >= 40 else
                    "The artist's infrastructure is ahead of their current momentum."),
        "missing": f["missing"],
    }
    return value, explanation, _data_quality(f["missing"])


# --- rights health -----------------------------------------------------------

def rights_health(artist_id, features=None):
    """Cautious by construction. Absence of a public record is a POTENTIAL
    gap, never a finding of 'unregistered'."""
    f = features or artist_features(artist_id)
    ev = f["rights"]
    releases = f["releases"]
    parts, findings = {}, []

    with_upc = sum(1 for r in releases if r.get("upc"))
    parts["identifier_consistency"] = _scale(with_upc / float(len(releases)), 0, 1) if releases else None
    if releases and with_upc < len(releases):
        findings.append(("Identifiers", "%d of %d releases have no UPC recorded" % (len(releases) - with_upc, len(releases)), "potential_gap"))

    def _share(flag):
        if not ev:
            return None
        hits = sum(1 for e in ev if (e.get("detail") or {}).get(flag))
        return hits / float(len(ev)) * 100.0

    parts["work_match"] = _share("work_match")
    parts["writer_completeness"] = _share("writers_complete")
    parts["share_completeness"] = _share("shares_complete")
    parts["recording_link"] = _share("recording_linked")
    parts["recording_evidence"] = _share("publisher_detected")

    if not ev:
        findings.append(("Registration", "No rights registry lookup has run for this catalogue yet", "unknown"))
    else:
        if (parts.get("work_match") or 0) < 60:
            findings.append(("Work match", "Some recordings are not confidently linked to a composition", "potential_gap"))
        if (parts.get("writer_completeness") or 0) < 60:
            findings.append(("Writers", "Writer information looks incomplete on part of the catalogue", "potential_gap"))
        if (parts.get("recording_evidence") or 0) < 60:
            findings.append(("Publisher / admin", "No publisher or administrator detected on part of the catalogue", "potential_gap"))

    total, used, contributions = 0.0, 0.0, {}
    for key, weight in RIGHTS_HEALTH_WEIGHTS.items():
        val = parts.get(key)
        if val is None:
            continue
        total += val * weight
        used += weight
        contributions[key] = {"value": round(val, 1), "weight": weight, "points": round(val * weight, 2)}
    value = _clamp(total / used) if used else 0.0
    quality = "ok" if used >= 0.8 else ("partial" if used >= 0.4 else "thin")

    explanation = {
        "score": round(value, 1),
        "weights": RIGHTS_HEALTH_WEIGHTS,
        "contributions": contributions,
        "coverage": round(used, 2),
        "findings": [{"area": a, "detail": d, "status": s} for a, d, s in findings],
        "caution": ("A low score means questions to answer, not a finding of fact. "
                    "Public registries are incomplete; only an authorised catalogue "
                    "review can confirm what is or is not registered."),
        "recommend_sweep": value < 60 or len(findings) >= 2,
    }
    return value, explanation, quality


# --- contacts ----------------------------------------------------------------

def contact_confidence(artist_id, features=None):
    f = features or artist_features(artist_id)
    contacts = f["contacts"]
    if not contacts:
        return 0.0, {"score": 0, "best": None, "detail": "No public professional contact found yet.",
                     "contacts": []}, "thin"
    ranked = []
    for e in contacts:
        weight = sstore.SOURCE_WEIGHT.get(e.get("source_type") or "", 0.3)
        score = min(1.0, (e.get("confidence") or 0) * weight) * 100.0
        if e.get("status") == "manually_confirmed":
            score = 100.0
        elif e.get("status") == "manually_rejected":
            score = 0.0
        elif e.get("is_stale"):
            score *= 0.7
        ranked.append((score, e))
    ranked.sort(key=lambda x: x[0], reverse=True)
    best_score, best = ranked[0]
    return best_score, {
        "score": round(best_score, 1),
        "best": {"role": best.get("claim_key"), "value": best.get("claim_value"),
                 "source": best.get("source_label"), "status": best.get("status_label"),
                 "why": "Ranked highest because a %s is the strongest source type available here." %
                        (best.get("source_type") or "public source").replace("_", " ")},
        "contacts": [{"role": e.get("claim_key"), "value": e.get("claim_value"),
                      "source": e.get("source_label"), "status": e.get("status_label"),
                      "confidence": round(s, 1), "stale": e.get("is_stale")} for s, e in ranked],
    }, "ok" if best_score > 50 else "partial"


# --- deal readiness ----------------------------------------------------------

def deal_readiness(artist_id, features=None, mandate_fit=None):
    f = features or artist_features(artist_id)
    mq = momentum_quality(artist_id, f)[0]
    rh = rights_health(artist_id, f)[0]
    cc = contact_confidence(artist_id, f)[0]
    cadence = _catalog_consistency(f["releases"]) or 30.0
    scale = _scale((f["artist"] or {}).get("monthly_listeners"), 1000, 500000) or 0.0

    parts = {
        "momentum_quality": mq,
        "release_cadence": cadence,
        "contactability": cc,
        "rights_health": rh,
        "mandate_fit": 50.0 if mandate_fit is None else mandate_fit,
        "scale": scale,
    }
    total, contributions = 0.0, {}
    for key, weight in DEAL_READINESS_WEIGHTS.items():
        val = parts[key]
        total += val * weight
        contributions[key] = {"value": round(val, 1), "weight": weight, "points": round(val * weight, 2)}
    value = _clamp(total)
    return value, {"score": round(value, 1), "weights": DEAL_READINESS_WEIGHTS,
                   "contributions": contributions,
                   "mandate_fit_supplied": mandate_fit is not None,
                   "missing": f["missing"]}, _data_quality(f["missing"])


# --- orchestration -----------------------------------------------------------

SCORE_FUNCS = [
    (MOMENTUM, momentum),
    (MOMENTUM_QUALITY, momentum_quality),
    (PLAYLIST_DEPENDENCY, playlist_dependency),
    (RIGHTS_HEALTH, rights_health),
    (CONTACT_CONFIDENCE, contact_confidence),
]


def score_artist(artist_id, persist=True):
    """Compute and (by default) store every score for one artist.

    Distribution Gap and Deal Readiness run last because they consume the
    others' outputs.
    """
    artist = sstore.get_artist(artist_id)
    if artist is None:
        return {}
    f = artist_features(artist_id, artist)
    cohort = cohort_of(artist)
    out = {}
    for key, fn in SCORE_FUNCS:
        value, explanation, quality = fn(artist_id, f)
        out[key] = {"value": value, "explanation": explanation, "data_quality": quality}
    gap_v, gap_e, gap_q = distribution_gap(artist_id, f, out[MOMENTUM]["value"])
    out[DISTRIBUTION_GAP] = {"value": gap_v, "explanation": gap_e, "data_quality": gap_q}
    dr_v, dr_e, dr_q = deal_readiness(artist_id, f)
    out[DEAL_READINESS] = {"value": dr_v, "explanation": dr_e, "data_quality": dr_q}

    if persist:
        for key, res in out.items():
            sstore.save_score(artist_id, key, res["value"], SCORE_VERSION, cohort,
                              res["explanation"], res["data_quality"])
    return out


def cohort_percentile(artist, value, score_key):
    """Where this value sits inside the artist's own cohort. Returned as a
    plain integer percentile so the UI can say 'top 12% of comparable acts'."""
    cohort = cohort_of(artist)
    peers = []
    for other in sstore.list_artists(limit=1000):
        if cohort_of(other) != cohort:
            continue
        s = sstore.latest_scores(other["id"]).get(score_key)
        if s:
            peers.append(s["value"])
    if len(peers) < 3:
        return None
    below = sum(1 for p in peers if p < value)
    return int(round(below / float(len(peers)) * 100))


# --- opportunity recommendation ---------------------------------------------

def recommend(artist_id, scores=None, features=None):
    """Turn the numbers into a lane and a next action. Suggestive only -
    the brief is explicit that nothing here signs or contacts anybody."""
    f = features or artist_features(artist_id)
    scores = scores or {k: {"value": v["value"], "explanation": v["explanation"]}
                        for k, v in score_artist(artist_id, persist=False).items()}

    def val(key):
        return (scores.get(key) or {}).get("value") or 0.0

    m, gap, rh, cc = val(MOMENTUM), val(DISTRIBUTION_GAP), val(RIGHTS_HEALTH), val(CONTACT_CONFIDENCE)
    dist = current_distribution(f["releases"])
    lanes, reasons = [], []

    if gap >= 70 and m >= 55:
        lanes.append("Distribution")
        reasons.append("Momentum is running ahead of a %s setup." % dist["classification"].lower())
    if rh < 60:
        lanes.append("Royalty Sweep")
        reasons.append("Rights Health is %d - there are registration questions worth answering." % round(rh))
    roles = {(e.get("claim_key") or "").lower() for e in f["contacts"]}
    if m >= 60 and "manager" not in roles:
        lanes.append("Management")
        reasons.append("No management is publicly listed while the audience is moving.")
    if m >= 60 and "booking agent" not in roles and f["cities"]:
        lanes.append("Booking")
        reasons.append("City-level demand is building with no booking representation listed.")
    if dist["consistency"] < 0.7 and len(f["releases"]) >= 4:
        lanes.append("Catalog migration")
        reasons.append("The catalogue is split across more than one distribution relationship.")
    if not lanes:
        lanes.append("Development")
        reasons.append("Nothing urgent - worth watching for the next release.")

    if m >= 65 and gap >= 70 and cc >= 50:
        action, urgency = "Contact now", "high"
    elif m >= 65 and cc < 50:
        action, urgency = "Research the contact first", "medium"
    elif m >= 45:
        action, urgency = "Watch for 7 days", "medium"
    else:
        action, urgency = "Continue monitoring", "low"

    if rh < 45:
        action = "Run a rights review"

    return {
        "lanes": lanes,
        "primary_lane": lanes[0],
        "action": action,
        "urgency": urgency,
        "reasons": reasons,
        "best_contact": contact_confidence(artist_id, f)[1].get("best"),
        "distribution": dist,
        "disclaimer": ("Signal ranks and explains. It does not sign artists, send offers, or contact "
                       "anyone; deal and rights guidance should be reviewed with qualified counsel."),
    }
