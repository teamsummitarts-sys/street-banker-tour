"""Section 8 — Rollout Engine.

A release turned into a campaign: dates, content, routing, follow-through.
The photograph is a venue wall with calendars on it; the words are markup.

The sample campaign is labelled an example everywhere it appears, and the
statuses are the ones the app actually uses. Where Street Banker cannot
publish for you - which is everywhere - the copy says schedule-ready
rather than scheduled.
"""

EYEBROW = "Rollout Engine"
NUMBER = "08"
HEADLINE = ["Plan it.", "Launch it.", "Live it."]
SUPPORT = ("From release calendars to content drops and tour routing—build "
           "your rollout and hit every moment that matters.")

PRIMARY_CTA = {"label": "Open Rollout Engine", "href": "/rollout"}
SECONDARY_CTA = {"label": "See a sample rollout"}

CAPABILITIES = [
    {"id": "release-calendar", "label": "Release Calendar",
     "line": "Map releases, shows, deadlines, and key campaign moments."},
    {"id": "content-schedule", "label": "Content Schedule",
     "line": "Plan posts, videos, stories, email, SMS, and campaign drops."},
    {"id": "tour-routing", "label": "Tour Routing",
     "line": "Coordinate release activity with markets, travel, and show nights."},
    {"id": "impact-tracking", "label": "Impact Tracking",
     "line": "See which moments are working and adjust the next move."},
]

WORKFLOW = [
    ("Plan", "Choose release dates, campaign length, target markets, goals and "
             "available assets."),
    ("Build", "Generate or organise the creative, copy, pitches, emails and "
              "content required."),
    ("Schedule", "Assign dates, channels, owners, approvals and tracking links."),
    ("Launch", "Execute the release sequence across approved channels."),
    ("Adapt", "Review results and adjust timing, content, markets or "
              "follow-through."),
]

# The statuses the app uses, in the order a piece of work moves through
# them. Built as markup, never drawn into the picture.
STATUSES = ["Idea", "Drafting", "Awaiting Asset", "Awaiting Approval",
            "Approved", "Scheduled", "Published", "Completed"]

# A 21-day example, labelled as one. The days are offsets from release
# day, not dates, because a date here would read as somebody's real
# campaign.
SAMPLE = {
    "label": "Example campaign",
    "length": "21-day rollout",
    "note": ("Days are counted from release day. This is a shape, not a "
             "schedule: nothing here is anyone's real campaign."),
    "items": [
        ("Day −21", "Release announcement", "Approved"),
        ("Day −18", "Teaser post", "Scheduled"),
        ("Day −14", "Pre-save push", "Scheduled"),
        ("Day −10", "Artwork reveal", "Awaiting Approval"),
        ("Day −6", "Short-form video", "Drafting"),
        ("Day 0", "Release-day post", "Awaiting Asset"),
        ("Day +1", "Email and SMS to the list", "Idea"),
        ("Day +7", "Follow-up content", "Idea"),
    ],
}

IMAGE = {
    "wide": {"stem": "/static/img/rollout-wide", "widths": [560, 940],
             "width": 940, "height": 710},
    "close": {"stem": "/static/img/rollout-close", "widths": [400, 600],
              "width": 600, "height": 630},
    "alt": ("Artist and touring crew updating printed release calendars "
            "backstage while equipment moves through a small venue."),
}

# The public tour, grouped by what is true rather than by feature.
PLAN_LENGTHS = ["14-day", "21-day", "30-day", "60-day", "90-day"]

TOUR_SECTIONS = [
    ("In the app today", [
        ("Rollout plans", "Build a 14, 21, 30, 60 or 90-day plan around a "
                          "release date and get every moment it needs on a "
                          "calendar."),
        ("Announcement and teaser sequencing", "The order things go out in, "
                                               "worked backwards from release "
                                               "day."),
        ("Pre-save campaigns", "A pre-save page that is live and collecting "
                               "before the record is."),
        ("Platform captions and video concepts", "Copy and short-form ideas "
                                                 "written against the plan, not "
                                                 "in a vacuum."),
        ("Playlist and press preparation", "The pitch material assembled and "
                                           "ready to send."),
        ("Team assignments and approvals", "Who owns a task, and what is waiting "
                                           "on whom."),
        ("Catalog reactivation", "Campaigns for records that are already out."),
    ]),
    ("Schedule-ready, not published for you", [
        ("Nothing posts itself", "Street Banker prepares the post, the caption "
                                 "and the date. Publishing it is you, or a "
                                 "platform integration that is not live yet."),
        ("Email and SMS are integration-ready", "The sequence is built and "
                                                "waiting on a provider "
                                                "connection."),
        ("Approval required", "Anything that leaves the workspace passes through "
                              "an approval first."),
    ]),
    ("Coming soon", [
        ("Direct social publishing", "Connecting a platform account so an "
                                     "approved post goes out on schedule."),
        ("Live impact tracking", "Reading results back from the platforms "
                                 "themselves rather than from what you tell it."),
    ]),
]


def get_rollout_config():
    return {
        "number": NUMBER,
        "eyebrow": EYEBROW,
        "headline": HEADLINE,
        "support": SUPPORT,
        "primary_cta": PRIMARY_CTA,
        "secondary_cta": SECONDARY_CTA,
        "capabilities": CAPABILITIES,
        "workflow": WORKFLOW,
        "statuses": STATUSES,
        "sample": SAMPLE,
        "image": IMAGE,
    }
