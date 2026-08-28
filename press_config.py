"""Press Desk, explained before an account is asked for.

Same shape as creative_config: grouped by what is TRUE rather than by
feature, with a third group for what the tool does not do. A press page
that will not print the third group is a sales page.

The third group matters more here than almost anywhere else in the
product, because the two things a press tool is most often sold on -
a database of journalists, and coverage as an outcome - are exactly the
two things this does not provide.
"""

EYEBROW = "Press Desk"
HEADLINE = "Tell the press. Know who read it."
SUBLINE = ("Your own media list, announcements written as news, and one "
           "tracked link per contact — so an open belongs to an outlet "
           "instead of disappearing into a total. Here is what that means "
           "in the app, and where it stops.")

# The five steps, in the order they actually happen.
WORKFLOW = [
    ("Build the list", "Add the writers, editors, shows and curators you "
                       "have a reason to contact, with their outlet, their "
                       "beat and your notes. Paste a CSV if you already keep "
                       "one — every row it cannot read is named, with its "
                       "line number, rather than quietly dropped."),
    ("Write the announcement", "One headline, a dateline, what happened, a "
                               "quote you would actually say out loud, and an "
                               "embargo date if you need one. You see it laid "
                               "out as the document a journalist reads."),
    ("Choose who gets it", "Pick from your list. Each contact gets their own "
                           "message, personalised with their name and outlet, "
                           "and their own link. Nobody is ever on a shared "
                           "To: line with forty other people."),
    ("Send it, or send it yourself", "The desk writes every message first and "
                                     "sending is a separate, deliberate act. "
                                     "You can send from your own inbox, which "
                                     "is usually the better route for press."),
    ("Watch what lands", "An open is attributed to the outlet that opened it. "
                         "You are told the first time each one reads it, and "
                         "not again when they re-read it."),
    ("Log what ran", "Record the review, the quote and the date. That is the "
                     "material your press kit is allowed to reuse — real "
                     "quotes with a real source."),
]

CAPABILITIES = [
    ("In the app today", [
        ("Your media list", "Contacts with outlet, role, beat, location and "
                            "notes, searchable and filterable. Yours alone: "
                            "no other artist on Street Banker can see it."),
        ("Announcements", "A written release — headline, subhead, dateline, "
                          "body, quote, boilerplate, embargo — previewed "
                          "exactly as it will be read."),
        ("A link per recipient", "Every contact on a pitch gets a distinct "
                                 "tracked link. That is the difference "
                                 "between knowing somebody opened it and "
                                 "knowing which magazine did."),
        ("The page they open", "A clean announcement page with the audio and "
                               "press kit attached. No account, no password, "
                               "and not indexed by search engines, so an "
                               "embargoed story cannot leak through a search "
                               "result."),
        ("Do not contact, enforced", "A contact you have marked do-not-contact "
                                     "or bounced is dropped where the pitch is "
                                     "built, not merely hidden from a form. It "
                                     "cannot be pitched by accident."),
        ("Coverage log", "What ran, where, when, and the line worth reusing."),
    ]),
    ("Guided, not automatic", [
        ("You choose the list", "Nothing here suggests journalists to you or "
                                "decides who should hear from you. The list is "
                                "the one you build."),
        ("You write the pitch", "Placeholders fill in each contact's name, "
                                "their outlet and their link. The words around "
                                "them are yours — a press email that reads as "
                                "generated gets filed as one."),
        ("Nothing sends itself", "Messages are prepared and shown to you "
                                 "first. Sending is a separate action you take "
                                 "after reading them."),
        ("A hundred per pitch", "A brake rather than a technical limit. A "
                                "press list worth having is small and chosen, "
                                "and a four-figure send is the behaviour that "
                                "gets a sending domain blocked."),
    ]),
    ("What it does not do", [
        ("It is not a media database", "No journalist contacts come with it. "
                                       "It holds the relationships you already "
                                       "have or go and build. Bought lists are "
                                       "how independent artists end up marked "
                                       "as spam."),
        ("It cannot promise coverage", "Nothing here buys, guarantees or "
                                       "arranges a placement. It gets a "
                                       "well-made pitch in front of people you "
                                       "chose, and then it is journalism."),
        ("No wire distribution", "This does not push announcements to a "
                                 "newswire or syndicate them anywhere."),
        ("No open pixel", "An open is recorded when somebody opens the link, "
                          "not when an email loads an invisible image. That "
                          "means the count is lower and it means it is real."),
        ("Sending needs your own domain", "Street Banker will only send press "
                                          "email once a verified sending "
                                          "domain is configured. Until then it "
                                          "refuses and says so, rather than "
                                          "reporting a delivery that did not "
                                          "happen — see below."),
    ]),
]

SENDING_TITLE = "Two ways it goes out, and one it refuses"
SENDING_COPY = (
    "From your own inbox is always available and is usually the right choice: "
    "the journalist sees a real person's address and their reply reaches you "
    "directly. From Street Banker sends one separate email per contact. That "
    "second route stays switched off unless a verified sending domain is "
    "configured — on a shared sender every message would report success and "
    "reach nobody, and a press desk that lies about delivery is worse than one "
    "that cannot send.")


def get_press_config():
    return {
        "eyebrow": EYEBROW,
        "headline": HEADLINE,
        "subline": SUBLINE,
        "workflow": WORKFLOW,
        "capabilities": CAPABILITIES,
        "sending_title": SENDING_TITLE,
        "sending_copy": SENDING_COPY,
    }
