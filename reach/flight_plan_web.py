"""Campaign Flight Plan template context."""

from flask import request

from . import flight_plan
from .web import bp, bootstrap


@bp.app_context_processor
def _flight_plan_context():
    if request.endpoint != "reach.overview":
        return {}
    campaign_id = (request.view_args or {}).get("campaign_id")
    if not campaign_id:
        return {}
    bootstrap()
    return {"flight_plan": flight_plan.build(campaign_id)}
