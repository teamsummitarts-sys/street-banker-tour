"""Artist-facing Ask Reach command/search surface."""

from flask import jsonify, render_template, request, url_for

from . import ask_reach
from .web import bp, _shell


def _decorate(result):
    items=[]
    for raw in result.get("items") or []:
        item=dict(raw)
        kind=item.get("type")
        if kind in ("opportunity","intake") and item.get("campaign_id") and item.get("target_id"):
            item["url"]=url_for("reach.target_detail",campaign_id=item["campaign_id"],target_id=item["target_id"])
        elif kind == "review" and item.get("campaign_id"):
            item["url"]=url_for("reach.review",campaign_id=item["campaign_id"],target_id=item.get("target_id"))
        elif kind == "response":
            item["url"]=url_for("reach.all_responses")
        elif kind == "needs_you":
            item["url"]=url_for("reach.needs_you")
        elif kind == "campaign" and item.get("campaign_id"):
            item["url"]=url_for("reach.overview",campaign_id=item["campaign_id"])
        elif kind == "relationship":
            item["url"]=url_for("reach.contacts_view")
        elif kind == "artist" and item.get("artist_id"):
            item["url"]=url_for("reach.artist_profile_page",artist_id=item["artist_id"])
        elif kind == "release" and item.get("recording_id"):
            item["url"]=url_for("reach.new_campaign",recording_id=item["recording_id"])
        elif kind == "signal" and item.get("artist_id"):
            item["url"]=url_for("reach.all_opportunities",artist_id=item["artist_id"])
        elif kind == "readiness":
            item["url"]=url_for("reach.catalog_view")
        else:
            item["url"]=url_for("reach.index")
        items.append(item)
    result=dict(result);result["items"]=items
    return result


@bp.route("/ask", methods=["GET"])
def ask_reach_page():
    query=request.args.get("q") or ""
    result=_decorate(ask_reach.ask(query))
    return render_template("reach/ask_reach.html",result=result,query=query,**_shell())


@bp.route("/ask.json", methods=["GET"])
def ask_reach_json():
    query=request.args.get("q") or ""
    return jsonify({"ok":True,**_decorate(ask_reach.ask(query))})


@bp.after_app_request
def _wire_dashboard_ask_reach(response):
    """Make the two Today-page Ask Reach controls open the command surface.

    The current v6 home template intentionally keeps Radar as a separate
    navigation destination. This scoped render rewrite changes only anchors with
    the Ask Reach classes, so Radar continues to point at /reach/opportunities.
    It avoids broad template churn while the dashboard shell is otherwise parked.
    """
    if request.endpoint != "reach.index" or response.mimetype != "text/html":
        return response
    html=response.get_data(as_text=True)
    radar=url_for("reach.all_opportunities")
    ask=url_for("reach.ask_reach_page")
    html=html.replace(
        f'class="r6-mobile-search" href="{radar}"',
        f'class="r6-mobile-search" href="{ask}"',
    ).replace(
        f'class="r6-search" href="{radar}"',
        f'class="r6-search" href="{ask}"',
    )
    response.set_data(html)
    return response
