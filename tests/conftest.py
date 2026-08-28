"""Point the persistence layer at a throwaway SQLite file for the whole
test session, before any test module imports the app."""

import os
import tempfile

os.environ["DATABASE_PATH"] = os.path.join(tempfile.mkdtemp(prefix="sb-tests-"), "test.db")
# Existing feature tests use instant plan switches to exercise tier-gated
# routes without contacting Stripe.  Production and staging never set this.
os.environ.setdefault("ALLOW_UNBILLED_PLAN_SWITCH", "1")
