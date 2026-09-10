"""Automatic scheduler for REACH Deadline + Intake Monitor."""

import os
import threading

from . import intake_monitor

_thread = None
_lock = threading.Lock()
_stop = threading.Event()

DEFAULT_INTERVAL_SECONDS = 6 * 60 * 60
START_DELAY_SECONDS = 120


def _loop(app, interval_seconds):
    if _stop.wait(START_DELAY_SECONDS):
        return
    while not _stop.is_set():
        try:
            with app.app_context():
                intake_monitor.scan_due(limit=20, force=False)
        except Exception:
            # Monitoring is advisory and must never bring down the web worker.
            pass
        _stop.wait(interval_seconds)


def start(app, interval_seconds=DEFAULT_INTERVAL_SECONDS):
    """Start once on Render; remain disabled in tests/local development."""
    global _thread
    if not os.environ.get("RENDER"):
        return None
    if (os.environ.get("REACH_INTAKE_MONITOR_AUTO") or "1").strip().lower() in (
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
            name="reach-intake-monitor",
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
