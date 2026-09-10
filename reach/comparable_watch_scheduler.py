"""Low-cost scheduler for Comparable Artist Watch.

The V2 service already runs one Gunicorn worker with a persistent REACH SQLite
file. A daemon thread in that same process can therefore check which artist
profiles are due without adding a second Render service or a second database.
The thread is deployment-only, idempotent, and does no work when live search is
not connected.
"""

import os
import threading

from . import artist_profile, audit, comparable_watch, rbac
from .providers import search as search_provider

_thread = None
_lock = threading.Lock()
_stop = threading.Event()

DEFAULT_INTERVAL_SECONDS = 60 * 60  # wake hourly; each artist runs at most weekly
START_DELAY_SECONDS = 75             # avoid deploy-overlap double work


def run_due_once(limit=25):
    """Run at most one weekly snapshot per due artist profile.

    This function is deterministic enough to test directly. A recent RUNNING
    row is treated as a lease so a rolling deploy cannot duplicate searches.
    """
    rbac.ensure_default_tenant()
    if not search_provider.connected():
        return {"checked": 0, "ran": 0, "skipped": "SEARCH_NOT_CONNECTED"}

    artists = artist_profile.list_artists()[:limit]
    ran = 0
    failures = 0
    for artist in artists:
        artist_id = artist["id"]
        if not comparable_watch.comparables(artist_id):
            continue
        latest = comparable_watch.latest_run(artist_id)
        if latest and latest["status"] == "RUNNING":
            age = comparable_watch.clock.days_since(latest["created_at"])
            if age is not None and age < 0.25:  # six-hour lease
                continue
        if not comparable_watch.due(artist_id):
            continue
        try:
            comparable_watch.run_now(artist_id)
            ran += 1
        except Exception as exc:  # isolate one artist from the next
            failures += 1
            audit.record(
                "comparable_watch.automatic_failed",
                entity_type="artist",
                entity_id=artist_id,
                payload={"error": str(exc)[:500]},
            )
    return {"checked": len(artists), "ran": ran, "failures": failures}


def _loop(app, interval_seconds):
    # Give a rolling deploy time to retire the previous process before the
    # first automatic scan. Manual Radar refresh remains immediately available.
    if _stop.wait(START_DELAY_SECONDS):
        return
    while not _stop.is_set():
        try:
            with app.app_context():
                run_due_once()
        except Exception:
            # The scheduler must never take down the web worker. Individual
            # watch runs already persist their failure state for inspection.
            pass
        _stop.wait(interval_seconds)


def start(app, interval_seconds=DEFAULT_INTERVAL_SECONDS):
    """Start once in the deployed V2 process; remain off in tests/local dev."""
    global _thread
    if not os.environ.get("RENDER"):
        return None
    if (os.environ.get("REACH_COMPARABLE_WATCH_AUTO") or "1").strip().lower() in (
        "0", "false", "off", "no"
    ):
        return None
    with _lock:
        if _thread is not None and _thread.is_alive():
            return _thread
        _stop.clear()
        _thread = threading.Thread(
            target=_loop,
            args=(app, interval_seconds),
            name="reach-comparable-watch",
            daemon=True,
        )
        _thread.start()
        return _thread


def stop():
    global _thread
    _stop.set()
    with _lock:
        thread = _thread
        _thread = None
    if thread is not None and thread.is_alive():
        thread.join(timeout=3)
