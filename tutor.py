"""Tutor mode — an ordered walkthrough of the whole product, opt-in.

The successor to a different idea. Progressive disclosure hid modules
until milestones were met; the owner tried it and preferred the opposite:
show everything, and offer a guide that says what to do next. Guidance
adds; hiding subtracts. This is the guidance.

It keeps firstrun.py's two rules, because they are what make a checklist
trustworthy rather than nagging:

  Steps read STATE, never a "seen it" flag. A step is done when the thing
  exists in the account. Delete the thing and the step comes back,
  because the list describes the account, not your click history.

  Nothing is gated on it. Tutor mode never hides, dims or locks a single
  module. It is a panel that can be switched off, and switching it off
  changes nothing but the panel.

Where firstrun stops after five steps and retires, the tutor keeps going:
four stages that follow the actual shape of the work - set up, get a
release out, tell people, track the money. It never retires on its own;
it is on until the person turns it off, because it was their choice to
turn it on.

Every step names a real route. Steps whose route sits behind a higher
plan are filtered out for accounts that cannot open them - a walkthrough
whose next instruction is a locked door teaches somebody to stop
trusting the walkthrough.
"""

# Each step: (key, title, why, href, cta).
# Each stage: (key, name, one-line purpose, steps).
#
# The five firstrun steps ARE stage one, same keys, so the two features
# can never disagree about what "set up" means. firstrun keeps running
# for people who never turn the tutor on; the tutor absorbs it for
# people who do.

STAGES = [
    ("start", "Set up the desk",
     "Five things, each one making the next more useful.", [
        ("profile", "Name the artist",
         "Every public page — your press kit, smart links, one-sheet — "
         "reads from this. Nothing else looks right until it is filled in.",
         "/artist-profile", "Set up the profile"),
        ("track", "Add a track",
         "Tracks are the spine: royalty lanes, registration, metadata and "
         "the release tools all hang off one.",
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
         "The Hours desk logs sessions and raises invoices once it knows "
         "your rates.",
         "/hours", "Fill in the rate card"),
    ]),
    ("release", "Get a release out",
     "Turn the track into a dated, public release.", [
        ("campaign", "Start a release campaign",
         "A campaign is the release's home: its page, its link, its "
         "destinations. Everything after this hangs off one.",
         "/links/new", "Start a campaign"),
        ("release_date", "Give it a release date",
         "A date turns a song into a plan. The scheduler, the rollout "
         "tools and the countdown all key off it — two weeks out or more "
         "gives the promotion tools room to work.",
         "/releases", "Open the scheduler"),
        ("publish", "Publish the campaign",
         "Until it is published, the smart link is a draft only you can "
         "see. Publishing is what makes it real.",
         "/links", "Publish it"),
    ]),
    ("promote", "Tell people",
     "A release nobody hears about did not happen.", [
        ("press_contact", "Add a press contact",
         "The writers, shows and curators you already know, with your "
         "notes. A list of ten you can name beats a database of a "
         "thousand you cannot.",
         "/press-desk/contacts/new", "Add the first contact"),
        ("announcement", "Write the announcement",
         "One headline, what happened, and where to hear it. This becomes "
         "the page a journalist opens.",
         "/press-desk/announcements/new", "Write it"),
    ]),
    ("money", "Track the money",
     "The part this product is named for.", [
        ("statement", "Upload a royalty statement",
         "One CSV from your distributor and the recovery desk, royalty "
         "lanes and valuation all start running on your real numbers "
         "instead of examples.",
         "/statements", "Upload one"),
    ]),
]


def stage_state_keys():
    """Every step key the state builder must supply."""
    return [key for _sk, _n, _p, steps in STAGES
            for key, *_ in steps]


def build(state, reachable=None):
    """The tutor panel for one account.

    `state`     dict of step-key -> bool, real queries only.
    `reachable` optional set of step keys this account's PLAN can open.
                Steps not in it are dropped entirely: a walkthrough must
                never point at a locked door. None means everything.
    """
    stages = []
    next_step = None
    total = done_total = 0
    for skey, name, purpose, steps in STAGES:
        rows = []
        for key, title, why, href, cta in steps:
            if reachable is not None and key not in reachable:
                continue
            row = {"key": key, "title": title, "why": why,
                   "href": href, "cta": cta, "done": bool(state.get(key))}
            rows.append(row)
            total += 1
            if row["done"]:
                done_total += 1
            elif next_step is None:
                next_step = dict(row, stage=name)
        if rows:
            stages.append({
                "key": skey, "name": name, "purpose": purpose,
                "steps": rows,
                "done": sum(1 for r in rows if r["done"]),
                "total": len(rows),
                "complete": all(r["done"] for r in rows),
            })
    return {
        "stages": stages,
        "next": next_step,          # None means everything is done
        "done": done_total,
        "total": total,
        "complete": next_step is None,
    }
