"""Local preview server on a THROWAWAY database.

The in-app browser pane uses this to look at pages while developing; it
never touches instance/streetbanker.db (the real dev data) because the
DATABASE_PATH is pointed at a scratch file before the app is imported.

    python tools/dev_preview.py        # http://localhost:5055
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("DATABASE_PATH", os.path.join(tempfile.gettempdir(), "sb-preview", "preview.db"))
os.makedirs(os.path.dirname(os.environ["DATABASE_PATH"]), exist_ok=True)

import app as appmod  # noqa: E402

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5055"))
    # Templates re-read on every request so an edit shows up on reload;
    # static files are still subject to the service worker's cache, so
    # clear it (or bump ?v=) when checking JS/CSS edits in the pane.
    appmod.app.config["TEMPLATES_AUTO_RELOAD"] = True
    appmod.app.jinja_env.auto_reload = True
    appmod.app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
    print("preview on http://localhost:%d  (db: %s)" % (port, os.environ["DATABASE_PATH"]))
    appmod.app.run(port=port, debug=False, use_reloader=False, threaded=True)
