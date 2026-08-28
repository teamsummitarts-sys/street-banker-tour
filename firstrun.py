"""The first move, for an account that has just arrived.

A new user lands in five hubs and seventy destinations with nothing in
any of them, and no way to tell which door to open first. This is a short
checklist that answers that, derived entirely from what the account
actually has - not a tour, not a modal, and not a fixed script that keeps
telling you to do something you did last week.

Two rules it keeps:

  It reads state, never a "seen the onboarding" flag. A step is done when
  the thing exists. Delete the thing and the step comes back, because it
  is describing your account rather than remembering a click.

  It disappears. Once the essentials are there the panel stops rendering
  entirely - permanent onboarding is clutter, and an app that keeps
  congratulating you is an app that thinks you are still a beginner.

Pure functions over counts, so the ordering can be checked without a
database.
"""

# Each step: (key, title, why, href, cta). Order is the order to do them
# in - each one makes the next more useful, which is the only defensible
# reason to put a checklist in a particular sequence.
#
# Every destination here must be reachable on the ENTRY plan. Statements
# and Overview are gated above it, so sending a new account there would
# be a checklist whose first instruction is a locked door.
STEPS = [
    ("profile", "Name the artist",
     "Every public page — your press kit, smart links, one-sheet — reads "
     "from this. Nothing else looks right until it is filled in.",
     "/artist-profile", "Set up the profile"),
    ("track", "Add a track",
     "Tracks are the spine: royalty lanes, registration, metadata and the "
     "release tools all hang off one. With none, most of the app has "
     "nothing to talk about.",
     "/tracks", "Add your first track"),
    ("link", "Make a smart link",
     "One link per release, with real click tracking behind it — the "
     "fastest thing here to get something back from.",
     "/links", "Create a smart link"),
    ("rack", "Put a track through the Rack",
     "Real EQ, saturation, stem separation, loudness to the broadcast "
     "standard — all running in your browser, nothing uploaded.",
     "/rack", "Open the Rack"),
    ("rate", "Set what you charge",
     "The Hours desk logs sessions and raises invoices once it knows your "
     "rates.",
     "/hours", "Fill in the rate card"),
]

# Below this many done, the panel shows. At or above it, it retires — the
# account has enough in it that a checklist is just clutter.
RETIRE_AT = 4


def build(state):
    """The checklist for one account.

    `state` is a plain dict of booleans keyed like STEPS. Returns None when
    there is nothing worth showing, so the caller can simply skip it.
    """
    steps = []
    for key, title, why, href, cta in STEPS:
        steps.append({
            "key": key, "title": title, "why": why, "href": href, "cta": cta,
            "done": bool(state.get(key)),
        })
    done = sum(1 for s in steps if s["done"])
    if done >= RETIRE_AT:
        return None                      # earned its way off the screen
    nxt = next((s for s in steps if not s["done"]), None)
    return {
        "steps": steps,
        "done": done,
        "total": len(steps),
        "next": nxt,
        # A brand-new account gets different words to a half-set-up one.
        "fresh": done == 0,
        "remaining": len(steps) - done,
    }
