"""Ask Reach — deterministic, grounded command/search surface.

This first version intentionally answers only from Reach's persisted records.
It recognizes a small set of artist-facing intents and returns UNKNOWN/empty
states when the account has no supporting data. No model-generated facts are
introduced here.
"""

import re

from . import (analytics, artist_profile, campaigns, db, humanactions,
               intake_monitor, onboarding, outcomes, rbac, signal_stack)


def _clean(query):
    return " ".join(str(query or "").strip().split())[:300]


def _contains(text, *terms):
    return any(term in text for term in terms)


def _suggestions():
    return [
        "What should I do today?",
        "Show my best opportunities",
        "Any deadlines or intake changes?",
        "What replies came in?",
        "Show my campaigns",
        "How ready is my next release?",
        "What are similar artists surfacing?",
    ]


def _today():
    tenant = rbac.current_principal().tenant_id
    items = []
    intake = intake_monitor.events(open_only=True, limit=6)
    for row in intake[:2]:
        items.append({
            "type": "intake",
            "campaign_id": row["campaign_id"], "target_id": row["target_id"],
            "label": row["summary"], "meta": row["severity"],
        })

    drafted = db.query(
        "SELECT t.id AS target_id, t.campaign_id, o.name AS outlet_name "
        "FROM campaign_target t JOIN outlet o ON o.id=t.outlet_id "
        "WHERE t.tenant_id=? AND t.status IN ('DRAFTED','NEEDS_APPROVAL') "
        "ORDER BY t.updated_at DESC LIMIT 3", (tenant,)
    )
    for row in drafted:
        items.append({"type":"review", "campaign_id":row["campaign_id"],
                      "target_id":row["target_id"], "label":f"Review pitch for {row['outlet_name']}",
                      "meta":"Prepared outreach"})

    for row in outcomes.follow_ups_due()[:2]:
        items.append({"type":"response", "campaign_id":row["campaign_id"],
                      "target_id":row["target_id"], "label":f"Follow up with {row['outlet_name']}",
                      "meta":"Follow-up due"})

    manual = humanactions.open_count()
    if manual:
        items.append({"type":"needs_you", "label":f"Complete {manual} manual action{'s' if manual != 1 else ''}",
                      "meta":"Needs You"})

    if not items:
        q = db.query(
            "SELECT t.id AS target_id,t.campaign_id,o.name AS outlet_name," 
            "(SELECT score FROM opportunity_score s WHERE s.target_id=t.id ORDER BY s.created_at DESC LIMIT 1) AS score "
            "FROM campaign_target t JOIN outlet o ON o.id=t.outlet_id "
            "WHERE t.tenant_id=? AND t.status IN ('QUALIFIED','READY') "
            "ORDER BY score DESC NULLS LAST LIMIT 3", (tenant,)
        )
        for row in q:
            items.append({"type":"opportunity", "campaign_id":row["campaign_id"],
                          "target_id":row["target_id"], "label":row["outlet_name"],
                          "meta":f"Match {row['score']}" if row["score"] is not None else "Qualified opportunity"})

    return {
        "intent":"today", "title":"What matters now",
        "answer":"These are the highest-priority items Reach can establish from your current records." if items else "Nothing urgent is established in Reach right now.",
        "items":items[:6],
    }


def _opportunities():
    tenant = rbac.current_principal().tenant_id
    rows = db.query(
        "SELECT t.id AS target_id,t.campaign_id,t.status,o.name AS outlet_name,o.kind,o.territory," 
        "(SELECT score FROM opportunity_score s WHERE s.target_id=t.id ORDER BY s.created_at DESC LIMIT 1) AS score "
        "FROM campaign_target t JOIN outlet o ON o.id=t.outlet_id "
        "WHERE t.tenant_id=? AND t.status IN ('QUALIFIED','READY','DRAFTED','NEEDS_APPROVAL') "
        "ORDER BY score DESC NULLS LAST,t.updated_at DESC LIMIT 12", (tenant,)
    )
    items=[{"type":"opportunity","campaign_id":r["campaign_id"],"target_id":r["target_id"],
            "label":r["outlet_name"],"meta":" · ".join(filter(None,[r["kind"],r["territory"],f"Match {r['score']}" if r["score"] is not None else None,r["status"]]))} for r in rows]
    return {"intent":"opportunities","title":"Best current opportunities",
            "answer":f"Reach has {len(rows)} actionable opportunity{'ies' if len(rows)!=1 else 'y'} in this view." if rows else "Reach has no currently qualified or review-ready opportunities.","items":items}


def _deadlines():
    rows = intake_monitor.events(open_only=True, limit=20)
    deadline_kinds={intake_monitor.DEADLINE_FOUND,intake_monitor.DEADLINE_CHANGED,
                    intake_monitor.WINDOW_OPENED,intake_monitor.WINDOW_CLOSED,
                    intake_monitor.ROUTE_CHANGED,intake_monitor.REQUIREMENTS_CHANGED,
                    intake_monitor.COST_CHANGED}
    rows=[r for r in rows if r["kind"] in deadline_kinds]
    items=[{"type":"intake","campaign_id":r["campaign_id"],"target_id":r["target_id"],
            "label":r["summary"],"meta":f"{r['severity']} · {r['outlet_name'] or r['outlet_domain']}"} for r in rows]
    return {"intent":"deadlines","title":"Deadlines & intake changes",
            "answer":f"{len(rows)} monitored change{'s' if len(rows)!=1 else ''} currently need attention." if rows else "No unacknowledged deadline or intake changes are currently recorded.","items":items}


def _replies():
    rows=outcomes.responses(limit=20)
    items=[{"type":"response","campaign_id":r["campaign_id"],"target_id":r["target_id"],
            "label":r["outlet_name"],"meta":f"{r['kind'].replace('_',' ').title()} · {r['received_at'][:10]}"} for r in rows]
    return {"intent":"replies","title":"Recent replies","answer":f"Reach has {len(rows)} recent recorded response{'s' if len(rows)!=1 else ''}." if rows else "No responses are recorded yet.","items":items}


def _campaigns():
    rows=campaigns.list_campaigns(limit=20)
    items=[]
    for row in rows:
        m=analytics.campaign_metrics(row["id"])
        items.append({"type":"campaign","campaign_id":row["id"],"label":row["name"],
                      "meta":f"{row['status']} · {m['submitted']} sent · {m['responses']} replies · {m['placed']} placed"})
    return {"intent":"campaigns","title":"Campaigns","answer":f"{len(rows)} campaign{'s' if len(rows)!=1 else ''} are in your Reach history." if rows else "No campaigns exist yet.","items":items}


def _relationships():
    tenant=rbac.current_principal().tenant_id
    rows=db.query(
        "SELECT rel.id,o.name AS outlet_name,o.kind,o.territory,rel.last_contact_at,rel.accepted_count,rel.declined_count,rel.placement_count "
        "FROM relationship rel LEFT JOIN outlet o ON o.id=rel.outlet_id WHERE rel.tenant_id=? "
        "ORDER BY rel.placement_count DESC,rel.accepted_count DESC,rel.last_contact_at DESC LIMIT 20",(tenant,))
    items=[{"type":"relationship","label":r["outlet_name"] or "Relationship",
            "meta":f"{r['placement_count']} placements · {r['accepted_count']} accepts"} for r in rows]
    return {"intent":"relationships","title":"Relationship memory","answer":f"Reach has {len(rows)} relationship record{'s' if len(rows)!=1 else ''}." if rows else "No relationship history is recorded yet.","items":items}


def _readiness():
    state=onboarding.status()
    items=[]
    for step in state.get("steps") or []:
        items.append({"type":"readiness","label":step["label"],"meta":step["state"]})
    done=state.get("done_count",0); total=state.get("total",0)
    return {"intent":"readiness","title":"Release readiness",
            "answer":f"{done} of {total} readiness steps are complete." if total else "No release-readiness checklist is available yet.","items":items}


def _comparables():
    artists=artist_profile.list_artists()
    all_items=[]
    for artist in artists[:5]:
        try:
            stack=signal_stack.radar_stack(artist["id"])
        except Exception:
            stack=[]
        for row in stack[:5]:
            all_items.append({"type":"signal","label":row["domain"],
                              "meta":f"{row['artist_count']} comparable artists · {row['signal_count']} signals",
                              "artist_id":artist["id"]})
    return {"intent":"comparables","title":"Comparable artist signals",
            "answer":f"Reach found {len(all_items)} repeated outlet signal{'s' if len(all_items)!=1 else ''} across your comparable-artist watch." if all_items else "No repeated comparable-artist outlet signals are recorded yet.","items":all_items[:15]}


def _search(query):
    tenant=rbac.current_principal().tenant_id
    needle=f"%{query[:80]}%"
    items=[]
    for row in db.query("SELECT id,name FROM artist WHERE tenant_id=? AND name LIKE ? COLLATE NOCASE LIMIT 5",(tenant,needle)):
        items.append({"type":"artist","artist_id":row["id"],"label":row["name"],"meta":"Artist Profile"})
    for row in db.query("SELECT id,title FROM recording WHERE tenant_id=? AND is_sample=0 AND title LIKE ? COLLATE NOCASE LIMIT 5",(tenant,needle)):
        items.append({"type":"release","recording_id":row["id"],"label":row["title"],"meta":"Release"})
    for row in db.query("SELECT id,name,status FROM campaign WHERE tenant_id=? AND name LIKE ? COLLATE NOCASE LIMIT 5",(tenant,needle)):
        items.append({"type":"campaign","campaign_id":row["id"],"label":row["name"],"meta":row["status"]})
    for row in db.query("SELECT t.id AS target_id,t.campaign_id,o.name,o.kind FROM campaign_target t JOIN outlet o ON o.id=t.outlet_id WHERE t.tenant_id=? AND (o.name LIKE ? COLLATE NOCASE OR o.domain LIKE ? COLLATE NOCASE) LIMIT 8",(tenant,needle,needle)):
        items.append({"type":"opportunity","campaign_id":row["campaign_id"],"target_id":row["target_id"],"label":row["name"],"meta":row["kind"]})
    return {"intent":"search","title":f"Results for “{query}”","answer":f"Reach found {len(items)} matching record{'s' if len(items)!=1 else ''}." if items else "Reach does not have a matching record for that query.","items":items[:20]}


def ask(query):
    query=_clean(query)
    if not query:
        return {"intent":"empty","title":"Ask Reach","answer":"Ask about what to do next, opportunities, campaigns, deadlines, replies, relationships, readiness or comparable-artist signals.","items":[],"suggestions":_suggestions()}
    text=query.casefold()
    if _contains(text,"what should i do","what do i do","today","next move","needs attention"):
        result=_today()
    elif _contains(text,"deadline","intake","submission window","submissions open","submissions closed"):
        result=_deadlines()
    elif _contains(text,"opportunit","best match","strongest match","radar"):
        result=_opportunities()
    elif _contains(text,"reply","replies","response","inbox"):
        result=_replies()
    elif _contains(text,"campaign"):
        result=_campaigns()
    elif _contains(text,"relationship","contact history","who knows"):
        result=_relationships()
    elif _contains(text,"ready","readiness","passport","release setup"):
        result=_readiness()
    elif _contains(text,"similar artist","comparable","signal stack","pickup"):
        result=_comparables()
    else:
        result=_search(query)
    result["query"]=query
    result["suggestions"]=_suggestions()
    return result
