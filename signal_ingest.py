"""Street Banker Signal - ingestion and refresh.

There is no scheduler, worker or queue in this application, so Phase 1 does
what the rest of the codebase already does for periodic work: a bounded sweep
that runs on a request and stops as soon as it has done its slice
(`board.py::_sweep_renewals` is the precedent).

Two entry points:

* `refresh_universe()` - pull the discovery universe from the preferred
  provider for each capability. Bounded by `max_artists` and only re-pulls an
  artist whose data has gone stale, so opening the dashboard never turns into
  a hundred provider calls.
* `sweep(org_id)` - the cheap per-request tick: refresh a small slice, then
  evaluate alert rules for that organisation.

Every provider call is timed and recorded in `signal_provider_runs`, so the
usage and health screens are built from real calls rather than guesses. A
provider that raises is caught, recorded as a failure, and skipped - a broken
vendor degrades the product, it never takes a page down.
"""
import time
from datetime import date, datetime, timedelta, timezone

import signal_providers as providers
import signal_scoring as scoring
import signal_store as sstore

# How long before an artist's pulled data is considered stale enough to refetch
REFRESH_AFTER_HOURS = 12
# Hard ceiling on provider calls per sweep, so a page view stays a page view
SWEEP_ARTIST_BUDGET = 3
METRIC_WINDOW_DAYS = 120


def _timed(provider, capability, fn, *args, **kwargs):
    """Run a provider call, record how it went, never raise."""
    start = time.time()
    try:
        out = fn(*args, **kwargs)
        ms = int((time.time() - start) * 1000)
        sstore.record_provider_run(provider.key, capability, True, ms,
                                   getattr(provider, "cost_per_request", 0.0))
        return out
    except NotImplementedError:
        sstore.record_provider_run(provider.key, capability, False, 0, 0,
                                   "capability not implemented")
        return None
    except Exception as exc:                      # noqa: BLE001 - degrade, never crash
        ms = int((time.time() - start) * 1000)
        sstore.record_provider_run(provider.key, capability, False, ms, 0,
                                   "%s: %s" % (type(exc).__name__, exc))
        return None


def _needs_refresh(artist):
    if not artist:
        return True
    last = artist.get("last_updated_at")
    if not last:
        return True
    try:
        when = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
    except ValueError:
        return True
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - when) > timedelta(hours=REFRESH_AFTER_HOURS)


def ingest_artist(provider_artist_id, reg=None, force=False):
    """Pull one artist through every capability and score them.

    Returns the canonical artist id, or None when even identity could not be
    fetched (in which case nothing is written - a half-ingested artist is
    worse than none).
    """
    reg = reg or providers.registry()
    ident = reg.for_capability(providers.CAP_ARTIST)
    if ident is None:
        return None
    detail = _timed(ident, providers.CAP_ARTIST, ident.get_artist, provider_artist_id)
    if not detail:
        return None

    artist_id = sstore.upsert_artist(ident.key, provider_artist_id, detail)
    end = date.today()
    start = end - timedelta(days=METRIC_WINDOW_DAYS)

    metrics_p = reg.for_capability(providers.CAP_METRICS)
    if metrics_p:
        points = _timed(metrics_p, providers.CAP_METRICS, metrics_p.get_artist_metrics,
                        provider_artist_id, start, end)
        if points:
            sstore.replace_metrics(artist_id, metrics_p.key, points)

    cities_p = reg.for_capability(providers.CAP_CITIES)
    if cities_p:
        cities = _timed(cities_p, providers.CAP_CITIES, cities_p.get_artist_cities,
                        provider_artist_id, start, end)
        if cities:
            sstore.replace_city_metrics(artist_id, cities_p.key, cities)

    releases_p = reg.for_capability(providers.CAP_RELEASES)
    releases = []
    if releases_p:
        releases = _timed(releases_p, providers.CAP_RELEASES, releases_p.get_artist_releases,
                          provider_artist_id) or []
        if releases:
            sstore.replace_releases(artist_id, releases_p.key, releases)

    _ingest_distribution(artist_id, releases, reg)
    _ingest_contacts(artist_id, provider_artist_id, reg)
    _ingest_rights(artist_id, releases, reg)

    scoring.score_artist(artist_id)
    return artist_id


def _ingest_distribution(artist_id, releases, reg):
    """Distributor is a per-release claim. The artist-level view is derived,
    and both the claim and its source are stored."""
    if not releases:
        return
    for rel in releases[:12]:
        name = rel.get("distributor_name")
        if not name:
            continue
        sstore.add_evidence(
            "artist", artist_id, sstore.CLAIM_DISTRIBUTOR,
            claim_key=rel.get("title") or "",
            claim_value=name,
            source_type="release_metadata",
            source_label="Release metadata - %s" % (rel.get("title") or "untitled"),
            source_url="",
            excerpt=rel.get("copyright_line") or "",
            confidence=0.85,
            provider=rel.get("provider") or "",
            detail={"classification": rel.get("distributor_class") or "Unknown",
                    "release_date": rel.get("release_date") or ""})


def _ingest_contacts(artist_id, provider_artist_id, reg):
    p = reg.for_capability(providers.CAP_CONTACTS)
    if p is None:
        return
    found = _timed(p, providers.CAP_CONTACTS, p.get_contact_evidence, provider_artist_id) or []
    for c in found:
        value = c.get("email") or c.get("company_name") or c.get("person_name") or ""
        sstore.add_evidence(
            "artist", artist_id, sstore.CLAIM_CONTACT,
            claim_key=c.get("role") or "Contact",
            claim_value=value,
            source_type=c.get("source_type") or "directory",
            source_label=c.get("source_label") or "",
            source_url=c.get("source_url") or "",
            excerpt=c.get("excerpt") or "",
            confidence=c.get("confidence") or 0.4,
            provider=p.key,
            detail={"person": c.get("person_name") or "", "company": c.get("company_name") or "",
                    "phone": c.get("phone") or ""})


def _ingest_rights(artist_id, releases, reg):
    p = reg.for_capability(providers.CAP_RIGHTS)
    if p is None:
        return
    for rel in (releases or [])[:6]:
        found = _timed(p, providers.CAP_RIGHTS, p.get_rights_evidence,
                       None, rel.get("title"), None) or []
        for r in found:
            sstore.add_evidence(
                "artist", artist_id, sstore.CLAIM_RIGHTS,
                claim_key=rel.get("title") or "",
                claim_value="work_match" if r.get("work_match") else "no_confident_match",
                source_type=r.get("source_type") or "work_registry",
                source_label=r.get("source_label") or "",
                source_url=r.get("source_url") or "",
                excerpt=r.get("excerpt") or "",
                confidence=r.get("confidence") or 0.4,
                # Absence of a match is a POTENTIAL gap - never a finding.
                status=None if r.get("work_match") else "potential_gap",
                provider=p.key,
                detail={"work_match": bool(r.get("work_match")),
                        "writers_complete": bool(r.get("writers_complete")),
                        "publisher_detected": bool(r.get("publisher_detected")),
                        "shares_complete": bool(r.get("shares_complete")),
                        "recording_linked": bool(r.get("recording_linked"))})


def refresh_universe(max_artists=25, reg=None, force=False):
    """Seed or refresh the discovery universe. Returns how many were pulled."""
    reg = reg or providers.registry()
    ident = reg.for_capability(providers.CAP_ARTIST)
    if ident is None:
        return 0
    found = _timed(ident, providers.CAP_ARTIST, ident.search_artists, "", max_artists) or []
    n = 0
    for a in found[:max_artists]:
        pid = a.get("provider_artist_id")
        if not pid:
            continue
        existing_id = None
        known = sstore.artist_provider_id
        # cheap staleness check before paying for a full pull
        with_id = _existing_artist(ident.key, pid)
        if with_id and not force and not _needs_refresh(sstore.get_artist(with_id)):
            continue
        if ingest_artist(pid, reg=reg):
            n += 1
    return n


def _existing_artist(provider, provider_id):
    from db import get_db
    with get_db() as db:
        row = db.execute("SELECT artist_id FROM signal_artist_ids WHERE provider=? AND provider_id=?",
                         (provider, provider_id)).fetchone()
    return row["artist_id"] if row else None


def ensure_universe(reg=None):
    """Called by the dashboard. Fills an empty universe once, then does
    nothing expensive on later views."""
    if sstore.counts()["artists"] == 0:
        return refresh_universe(reg=reg)
    return 0


def sweep(organization_id, reg=None, budget=SWEEP_ARTIST_BUDGET):
    """The per-request tick: refresh a few stale artists, then run alerts."""
    reg = reg or providers.registry()
    refreshed = 0
    for artist in sstore.list_artists(limit=200):
        if refreshed >= budget:
            break
        if not _needs_refresh(artist):
            continue
        pid = sstore.artist_provider_id(artist["id"], (reg.for_capability(providers.CAP_ARTIST) or reg.mock).key)
        if pid and ingest_artist(pid, reg=reg):
            refreshed += 1
    raised = evaluate_alerts(organization_id)
    return {"refreshed": refreshed, "alerts": raised}


def evaluate_alerts(organization_id):
    """Run this org's rules over its own watched artists.

    Scoped to the organisation on both sides: its rules, its watchlist. One
    customer's thresholds never fire against another's roster.
    """
    rules = sstore.list_alert_rules(organization_id, active_only=True)
    if not rules:
        return 0
    watched = sstore.watch_items(organization_id)
    raised = 0
    for item in watched:
        artist_id = item["artist_id"]
        scores = sstore.latest_scores(artist_id)
        for rule in rules:
            kind = rule["trigger_kind"]
            threshold = rule["threshold"]
            hit, title = False, ""
            if kind == "momentum_above":
                v = (scores.get(scoring.MOMENTUM) or {}).get("value")
                hit = v is not None and v >= threshold
                title = "%s: SB Momentum %d" % (item["canonical_name"], round(v or 0))
            elif kind == "distribution_gap_above":
                v = (scores.get(scoring.DISTRIBUTION_GAP) or {}).get("value")
                hit = v is not None and v >= threshold
                title = "%s: Distribution Gap %d" % (item["canonical_name"], round(v or 0))
            elif kind == "deal_readiness_above":
                v = (scores.get(scoring.DEAL_READINESS) or {}).get("value")
                hit = v is not None and v >= threshold
                title = "%s: Deal Readiness %d" % (item["canonical_name"], round(v or 0))
            elif kind == "rights_health_below":
                v = (scores.get(scoring.RIGHTS_HEALTH) or {}).get("value")
                hit = v is not None and v <= threshold
                title = "%s: Rights Health %d" % (item["canonical_name"], round(v or 0))
            if hit and sstore.raise_alert(organization_id, kind, title,
                                          body="Rule “%s” matched." % rule["name"],
                                          artist_id=artist_id, rule_id=rule["id"],
                                          severity="high" if "gap" in kind else "info"):
                raised += 1
    return raised
