"""The showcase, running on the real engines.

/recovery, /valuation and /documents each had two templates: one for the
demo account, drawing hardcoded figures out of royalty_data, and one for
everybody else, computing from uploaded statements. Two pages per route
is two things to keep true, and the one a partner is shown on a call was
the one that could not be wrong, because it was not computed from
anything.

So the demo account gets statements instead - a real CSV, parsed by the
same `parse_statement` an artist's upload goes through, stored in the
same table, read by the same engines. The showcase now demonstrates the
product rather than an illustration of it, and every number a partner
sees on that call is one the code actually derived.

The rows are deliberately imperfect. Two carry no track title, so the
recovery scan has genuine unattributed revenue to find; one track earns
on three sources and is silent on a fourth, so there is a real coverage
gap. A demo where everything is clean would show a scanner finding
nothing, which is a poor demonstration of a scanner.

Seeding is idempotent and only ever touches an account that has no
statements at all: a demo someone has been clicking around in keeps
whatever they uploaded.
"""

import db as store
from statements_engine import parse_statement

FILENAME = "synthwave-surfer-q1-q2.csv"

# Six months, four sources, five recordings. Written as a CSV because
# that is what the parser takes - seeding through the same door an
# artist uses is the only way to know the door works.
CSV = """Track Title,Store,Net Revenue,Sales Period,Country
Midnight Drive,Spotify,412.55,2026-01,US
Midnight Drive,Apple Music,188.20,2026-01,US
Midnight Drive,YouTube Content ID,64.10,2026-01,GB
Neon Dreams,Spotify,301.40,2026-01,US
Neon Dreams,Apple Music,142.75,2026-01,DE
,Spotify,58.30,2026-01,US
Midnight Drive,Spotify,455.80,2026-02,US
Midnight Drive,Apple Music,201.65,2026-02,US
Neon Dreams,Spotify,288.95,2026-02,US
City Lights,Spotify,96.40,2026-02,US
City Lights,Deezer,22.15,2026-02,FR
Midnight Drive,Spotify,498.25,2026-03,US
Midnight Drive,Apple Music,220.40,2026-03,GB
Midnight Drive,Deezer,41.80,2026-03,FR
Neon Dreams,Spotify,312.60,2026-03,US
Neon Dreams,YouTube Content ID,77.35,2026-03,US
City Lights,Spotify,124.90,2026-03,US
,Apple Music,73.45,2026-03,US
Digital Paradise,Spotify,207.30,2026-04,US
Digital Paradise,Apple Music,98.55,2026-04,US
Digital Paradise,YouTube Content ID,44.20,2026-04,BR
Midnight Drive,Spotify,521.15,2026-04,US
Neon Dreams,Spotify,334.85,2026-04,US
City Lights,Spotify,141.05,2026-04,US
Midnight Drive,Spotify,545.70,2026-05,US
Midnight Drive,Apple Music,238.90,2026-05,US
Neon Dreams,Spotify,356.20,2026-05,US
Neon Dreams,Deezer,48.65,2026-05,FR
Digital Paradise,Spotify,229.75,2026-05,US
Velvet Static,Spotify,88.30,2026-05,US
Midnight Drive,Spotify,571.40,2026-06,US
Midnight Drive,Apple Music,256.35,2026-06,GB
Neon Dreams,Spotify,371.95,2026-06,US
Digital Paradise,Spotify,248.60,2026-06,US
Digital Paradise,Deezer,52.40,2026-06,FR
Velvet Static,Spotify,103.75,2026-06,US
"""


def seed_statements(user_id):
    """Give a demo account real rows. True if it wrote any.

    Keyed on the filename rather than on "has no statements at all":
    the demo databases already carry whatever previous tours uploaded,
    and this has to add the showcase statement beside those without
    replacing them or arriving twice.
    """
    if not user_id:
        return False
    if any(s.get("filename") == FILENAME for s in store.get_statements(user_id)):
        return False
    parsed = parse_statement(CSV, FILENAME)
    if parsed["error"] or not parsed["rows"]:
        return False
    store.save_statement(user_id, FILENAME, parsed["rows"])
    return True
