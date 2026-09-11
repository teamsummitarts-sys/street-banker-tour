"""Artist-facing Campaign Debrief route."""

from flask import abort, render_template

from . import campaign_debrief, campaigns
from .web import bp, _shell


@bp.route("/campaigns/<campaign_id>/debrief")
def campaign_debrief_page(campaign_id):
    campaign = campaigns.get(campaign_id)
    if campaign is None:
        abort(404)
    return render_template(
        "reach/campaign_debrief.html",
        debrief=campaign_debrief.build(campaign_id),
        **_shell(campaign_id, "overview"),
    )
