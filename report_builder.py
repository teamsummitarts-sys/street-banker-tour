"""Reports that are actually files.

POST /reports/<id>/generate used to append a dict with a made-up filename
to an in-memory list and return ok:true. The page then displayed
"Ready: royalty-report-20260801.pdf" and listed it under Recently
Generated. No file was written, no endpoint served that name, and there
was nowhere to click. The app told the artist something had happened
that had not.

This builds the file, from their own statements. Two consequences worth
being explicit about:

  Formats. The declared formats were PDF and XLSX. Producing either
  needs a dependency this project does not have, and adding one to keep
  a label honest is the wrong trade when CSV opens in Excel, Sheets and
  Numbers and is what a rights administrator wants to paste anyway. The
  labels now say CSV because CSV is what arrives.

  Empty accounts. A report with no data behind it is not an empty
  report, it is a misleading one - a "Missing Money Report" listing
  nothing reads as "nothing is missing". So a builder returns None with
  a reason, and the page says why instead of downloading a header row.

Nothing is stored. Reports are derived from live statement data, so they
are rebuilt on download; a cached copy could only ever be staler than
the numbers on screen.
"""

import csv
import io
from datetime import date

import capital_engine
import db as store
import royalty_types


def _rows(user_id):
    return store.get_statement_rows(user_id)


def _csv(header, body):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    for r in body:
        w.writerow(r)
    return buf.getvalue()


# --- the six --------------------------------------------------------------

def _royalty_report(user_id):
    rows = _rows(user_id)
    if not rows:
        return None, ("No royalty statements uploaded yet, so there is "
                      "nothing to break down.")
    out = []
    for r in sorted(rows, key=lambda r: (r.get("source") or "",
                                         -(r.get("amount") or 0))):
        out.append([r.get("period") or "", r.get("source") or "",
                    r.get("title") or "(untitled)",
                    r.get("territory") or "",
                    "%.2f" % (r.get("amount") or 0)])
    return _csv(["Period", "Source", "Track", "Territory", "Amount"], out), None


def _missing_money_report(user_id):
    rows = _rows(user_id)
    if not rows:
        return None, ("No statements uploaded, so nothing has been checked "
                      "for missing money. An empty report here would read "
                      "as 'nothing is missing', which is not the same thing.")
    # Rows that were paid but never attributed to a track.
    unmatched = [r for r in rows if not (r.get("title") or "").strip()]
    # Tracks earning on some sources and absent from others.
    by_title, sources = {}, set()
    for r in rows:
        t = (r.get("title") or "").strip()
        if not t:
            continue
        s = r.get("source") or ""
        sources.add(s)
        by_title.setdefault(t, {}).setdefault(s, 0.0)
        by_title[t][s] += r.get("amount") or 0

    out = []
    for r in unmatched:
        out.append(["Unattributed row", r.get("source") or "",
                    r.get("period") or "", "",
                    "%.2f" % (r.get("amount") or 0),
                    "Paid but no track title - ask the distributor for "
                    "corrected metadata"])
    for title, per_source in sorted(by_title.items()):
        missing = sources - set(per_source)
        if not missing:
            continue
        avg = sum(per_source.values()) / max(len(per_source), 1)
        out.append(["Coverage gap", ", ".join(sorted(missing)), "", title,
                    "%.2f" % avg,
                    "Earns elsewhere but absent here. Amount is this "
                    "track's own per-source average, an estimate, not a "
                    "guarantee"])
    if not out:
        return None, ("Checked %d statement rows and found no unattributed "
                      "revenue and no coverage gaps. Nothing to export."
                      % len(rows))
    return _csv(["Finding", "Source", "Period", "Track", "Amount", "Notes"],
                out), None


def _catalog_valuation_report(user_id):
    el = capital_engine.advance_eligibility(user_id)
    if not el.get("real"):
        return None, el.get("note") or ("No statements uploaded, so there "
                                        "is no income to value.")
    total = el.get("income_total") or 0
    periods = el.get("periods") or 0
    annualised = (total / periods * 12) if periods else 0
    out = [["Tracked income", "%.2f" % total],
           ["Statement periods", periods],
           ["Annualised pace", "%.2f" % annualised]]
    for label, mult in (("Low (3x)", 3), ("Mid (4x)", 4), ("High (5x)", 5)):
        out.append([label, "%.2f" % (annualised * mult)])
    out.append(["Basis", "Annualised from your uploaded statement months "
                         "with a conservative independent-catalog multiple. "
                         "An estimate, not an appraisal, and not financial "
                         "advice."])
    return _csv(["Measure", "Value"], out), None


def _advance_readiness_report(user_id):
    el = capital_engine.advance_eligibility(user_id)
    if not el.get("real"):
        return None, el.get("note") or "No income to lend against yet."
    out = [["Tier", el.get("tier") or ""],
           ["Capital score", el.get("score") or 0],
           ["Suggested advance", "%.2f" % (el.get("suggested_advance") or 0)],
           ["Tracked income", "%.2f" % (el.get("income_total") or 0)],
           ["Statement periods", el.get("periods") or 0],
           ["Distinct sources", el.get("sources") or 0],
           ["Basis", "Computed from your uploaded statements. Indicative "
                     "only - an offer depends on the funder's own "
                     "underwriting."]]
    return _csv(["Measure", "Value"], out), None


def _registration_audit(user_id):
    rows = _rows(user_id)
    if not rows:
        return None, ("No statements uploaded, so there are no tracks to "
                      "audit registration for.")
    seen = {}
    for r in rows:
        t = (r.get("title") or "").strip()
        if not t:
            continue
        d = seen.setdefault(t, {"sources": set(), "total": 0.0})
        d["sources"].add(r.get("source") or "")
        d["total"] += r.get("amount") or 0
    if not seen:
        return None, ("Every statement row is missing a track title, so "
                      "there is nothing to audit. That is itself the "
                      "finding - see the Missing Money Report.")
    out = [[t, len(d["sources"]), ", ".join(sorted(s for s in d["sources"] if s)),
            "%.2f" % d["total"]]
           for t, d in sorted(seen.items())]
    return _csv(["Track", "Sources paying", "Sources", "Total earned"],
                out), None


def _investor_snapshot(user_id):
    rows = _rows(user_id)
    if not rows:
        return None, ("No statements uploaded. A snapshot with no numbers "
                      "behind it is worse than none.")
    total = sum(r.get("amount") or 0 for r in rows)
    titles = {(r.get("title") or "").strip() for r in rows}
    titles.discard("")
    srcs = {r.get("source") or "" for r in rows}
    srcs.discard("")
    periods = {r.get("period") or "" for r in rows}
    periods.discard("")
    out = [["Tracked revenue", "%.2f" % total],
           ["Tracks earning", len(titles)],
           ["Revenue sources", len(srcs)],
           ["Statement periods", len(periods)],
           ["Statement rows", len(rows)]]
    # territory_report returns (code, amount) tuples, not dicts.
    terr = royalty_types.territory_report(user_id) or {}
    for code, amount in (terr.get("territories") or [])[:10]:
        out.append(["Territory: %s" % code, "%.2f" % (amount or 0)])
    if terr.get("total_rows") and terr.get("covered_rows") is not None:
        out.append(["Rows carrying a territory",
                    "%d of %d" % (terr["covered_rows"], terr["total_rows"])])
    out.append(["Basis", "Your uploaded statements only. Does not include "
                         "revenue from sources you have not connected or "
                         "uploaded."])
    return _csv(["Measure", "Value"], out), None


BUILDERS = {
    "royalty-report": _royalty_report,
    "missing-money-report": _missing_money_report,
    "catalog-valuation-report": _catalog_valuation_report,
    "advance-readiness-report": _advance_readiness_report,
    "registration-audit": _registration_audit,
    "investor-snapshot": _investor_snapshot,
}


def build(report_id, user_id, today=None):
    """(filename, csv_text, None) on success, or (None, None, reason).

    `today` is injectable so tests do not depend on the clock.
    """
    fn = BUILDERS.get(report_id)
    if fn is None:
        return None, None, "Unknown report."
    body, reason = fn(user_id)
    if body is None:
        return None, None, reason
    stamp = (today or date.today()).strftime("%Y%m%d")
    return "%s-%s.csv" % (report_id, stamp), body, None
