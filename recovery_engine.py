"""The recovery view, computed from the artist's own statements.

/recovery used to be the most confident page in the product and the least
true one. Every figure on it - "Estimated Uncollected $3,301.38", "Ready
to Claim $1,731.34", 52% high-confidence, seventeen flagged issues, the
claim rows, the leak alerts, the recovery-over-time curve - came from
`_DEFAULT_PLATFORMS`, a hardcoded list in royalty_data.py. It was the
same number on every account on the first day of every account. An
artist who had uploaded nothing was told, to the cent, what they were
owed.

This computes the same page from `statements_engine.analyze()`, which
reads the rows the artist uploaded. Two kinds of finding come out of it,
and the difference between them is the whole point:

  Unattributed revenue is ACTUAL. The statement says money was paid and
  names no track. That is not a guess - the dollars are on the page, the
  attribution is missing. It is the strongest thing this product can
  tell someone, so it leads.

  Coverage gaps are ESTIMATES. A track earns on Spotify and Apple and
  shows nothing from Deezer, where its labelmates earn. That is worth
  checking, and the amount is that track's own per-source average, which
  is a reasonable guess and nothing more. Confidence is Medium when two
  or more sources corroborate the track's earning history and Low when
  only one does - fewer sources, thinner evidence.

Nothing here degrades to seed data. An account with no statements gets
`has_data: False`, and the page says it has not scanned anything rather
than that it found nothing: "no findings" and "nothing uploaded to find
findings in" are different sentences and only one of them is true.
"""

import db as store
import statements_engine


_UNATTRIBUTED_ACTION = "Request corrected metadata from the distributor"
_GAP_ACTION = "Verify delivery and registration"


def _unattributed_by_source(rows):
    """Untitled rows grouped by whoever paid them, biggest first."""
    totals, periods = {}, {}
    for r in rows:
        if (r.get("title") or "").strip():
            continue
        amount = r.get("amount") or 0
        if amount <= 0:
            continue
        source = (r.get("source") or "").strip() or "Unknown source"
        totals[source] = totals.get(source, 0) + amount
        period = (r.get("period") or "").strip()
        if period:
            periods.setdefault(source, set()).add(period)
    out = [{"source": s, "amount": round(a, 2),
            "periods": sorted(periods.get(s, ()))}
           for s, a in totals.items()]
    out.sort(key=lambda x: x["amount"], reverse=True)
    return out


def _unattributed_by_period(rows):
    totals = {}
    for r in rows:
        if (r.get("title") or "").strip():
            continue
        period = (r.get("period") or "").strip()
        if not period:
            continue
        totals[period] = totals.get(period, 0) + (r.get("amount") or 0)
    return [{"period": p, "amount": round(a, 2)}
            for p, a in sorted(totals.items()) if a > 0]


def _slug(text):
    return "".join(c if c.isalnum() else "-" for c in str(text).lower()).strip("-")


def build(user_id):
    """The whole /recovery page for one account. Never seed data."""
    rows = store.get_statement_rows(user_id) if user_id else []
    analysis = statements_engine.analyze(rows) if rows else None
    cases = store.list_recovery_cases(user_id) if user_id else []
    case_view = {
        "all": cases,
        "open": [c for c in cases if c["status"] in ("open", "submitted", "waiting")],
        "pipeline": round(sum(c["estimated_amount"] for c in cases
                              if c["status"] in ("open", "submitted", "waiting")), 2),
        "recovered": round(sum(c.get("payout_result") or 0
                               for c in cases if c["status"] == "won"), 2),
        # Titles already under a case, so a finding can say "case open"
        # instead of offering to open a second one for the same money.
        "titles": {(c["title"] or "").strip().lower() for c in cases},
    }

    if analysis is None:
        return {"has_data": False, "findings": [], "by_source": [],
                "unattributed_by_period": [], "cases": case_view,
                "row_count": 0, "source_count": 0, "period_count": 0,
                "tracked_total": 0.0, "actual_unattributed": 0.0,
                "estimated_gaps": 0.0, "total_at_stake": 0.0,
                "finding_count": 0, "affected_recordings": 0}

    # How many sources each track is already earning on - the evidence
    # behind a coverage gap's confidence.
    sources_per_track = {t["title"]: t["sources"] for t in analysis["by_track"]}

    findings = []
    for entry in _unattributed_by_source(rows):
        detail = ("Paid by %s with no track title on the row. The money is "
                  "on your statement; the attribution is not."
                  % entry["source"])
        if entry["periods"]:
            detail += " Periods: %s." % ", ".join(entry["periods"])
        findings.append({
            "id": "unattributed-%s" % _slug(entry["source"]),
            "kind": "unattributed",
            "basis": "Actual",
            "confidence": "High",
            "source": entry["source"],
            "track": "",
            "issue_type": "Unattributed revenue",
            "detail": detail,
            "amount": entry["amount"],
            "action": _UNATTRIBUTED_ACTION,
            "case_title": "Unattributed revenue on %s" % entry["source"],
            "case_category": "unmatched",
        })

    for gap in analysis["coverage_gaps"]:
        missing = gap["missing_sources"]
        per_source = round(gap["estimated_value"] / max(len(missing), 1), 2)
        corroborating = sources_per_track.get(gap["title"], 1)
        findings.append({
            "id": "gap-%s" % _slug(gap["title"]),
            "kind": "coverage_gap",
            "basis": "Estimate",
            "confidence": "Medium" if corroborating >= 2 else "Low",
            "source": ", ".join(missing),
            "track": gap["title"],
            "issue_type": "Coverage gap",
            "detail": ('"%s" earns on %d source%s and shows nothing from %s. '
                       "Estimated at $%.2f per missing source, this track's "
                       "own per-source average. An estimate, not a guarantee."
                       % (gap["title"], corroborating,
                          "" if corroborating == 1 else "s",
                          ", ".join(missing), per_source)),
            "amount": gap["estimated_value"],
            "action": _GAP_ACTION,
            "case_title": "Coverage gap: %s" % gap["title"],
            "case_category": "coverage_gap",
        })

    findings.sort(key=lambda f: (f["basis"] != "Actual", -f["amount"]))
    for f in findings:
        f["has_case"] = f["case_title"].strip().lower() in case_view["titles"]

    actual = round(sum(f["amount"] for f in findings if f["basis"] == "Actual"), 2)
    estimated = round(sum(f["amount"] for f in findings if f["basis"] == "Estimate"), 2)

    # Where the missing money sits. Unattributed rows are filed under the
    # source that paid them; gaps under the source that is silent.
    by_source = {}
    for f in findings:
        for name in (f["source"].split(", ") if f["kind"] == "coverage_gap"
                     else [f["source"]]):
            share = (f["amount"] / len(f["source"].split(", "))
                     if f["kind"] == "coverage_gap" else f["amount"])
            bucket = by_source.setdefault(name, {"source": name, "amount": 0.0,
                                                 "actual": 0.0, "estimated": 0.0})
            bucket["amount"] += share
            bucket["actual" if f["basis"] == "Actual" else "estimated"] += share
    sources = sorted(by_source.values(), key=lambda s: s["amount"], reverse=True)
    for s in sources:
        for key in ("amount", "actual", "estimated"):
            s[key] = round(s[key], 2)

    return {
        "has_data": True,
        "row_count": analysis["row_count"],
        "source_count": analysis["source_count"],
        "period_count": analysis["period_count"],
        "tracked_total": analysis["total"],
        "actual_unattributed": actual,
        "estimated_gaps": estimated,
        "total_at_stake": round(actual + estimated, 2),
        "finding_count": len(findings),
        "affected_recordings": len({f["track"] for f in findings if f["track"]}),
        "findings": findings,
        "by_source": sources[:8],
        "unattributed_by_period": _unattributed_by_period(rows),
        "cases": case_view,
    }
