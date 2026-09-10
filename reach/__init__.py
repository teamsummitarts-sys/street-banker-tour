"""REACH — global music discovery, opportunity intelligence and outreach.

REACH is a standalone application. It has its own Flask entry point, its own
templates, its own SQLite store and its own recording catalog; it does not
import, read or write any other application's data.

Layout: ``app.py`` is the entry point, ``reach/`` is this package, ``templates/``
holds the shell and the screens, ``tests/`` the suite and ``docs/`` the eight
Phase One documents.
"""

REACH_VERSION = "1.0.0-phase-one"

# Artist-profile routes attach to the existing REACH blueprint before Flask
# registers it. Keeping this import after REACH_VERSION avoids a second
# blueprint while keeping the profile workspace in its own small module.
from . import artist_profile_web as _artist_profile_web  # noqa: E402,F401
