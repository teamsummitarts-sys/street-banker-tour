"""Royalty-statement ingestion + real recovery analysis.

Parses distributor/PRO/MLC statement CSVs with flexible column detection
(every service names its columns differently), then runs genuinely
computable findings on the artist's own numbers:

- totals by source and by track (real)
- unmatched revenue: rows with no track title — money that can't be
  attributed (the "black box" made concrete) (real)
- cross-source coverage gaps: tracks earning on some sources but absent
  from others, with an estimated value based on that track's own average
  per-source earnings (estimate, labeled as such)
"""

import csv
import io

# Header aliases -> canonical fields. Compared lowercased/stripped.
_TITLE_COLS = {"title", "track", "track title", "song", "song title", "track_name",
               "trackname", "song_name", "release title", "asset title", "work title"}
_SOURCE_COLS = {"source", "platform", "store", "dsp", "retailer", "service",
                "store name", "channel", "distributor", "society"}
_AMOUNT_COLS = {"amount", "revenue", "earnings", "royalty", "royalties", "net",
                "net revenue", "net earnings", "payable", "total", "usd",
                "amount due", "net amount", "earnings (usd)", "royalty amount"}
_PERIOD_COLS = {"period", "date", "month", "statement period", "sales period",
                "reporting period", "sale month", "accounting period"}
_TERRITORY_COLS = {"territory", "country", "region", "market", "country code",
                   "country of sale", "sales territory"}


def _match(headers, aliases):
    for h in headers:
        if h.lower().strip() in aliases:
            return h
    # loose contains-match fallback (e.g. "Net Revenue (USD)")
    for h in headers:
        hl = h.lower()
        if any(a in hl for a in aliases if len(a) > 4):
            return h
    return None


def _to_amount(raw):
    if raw is None:
        return None
    s = str(raw).strip().replace("$", "").replace(",", "").replace("(", "-").replace(")", "")
    if not s:
        return None
    try:
        return round(float(s), 4)
    except ValueError:
        return None


def parse_statement(data, filename="statement.csv"):
    """Parse CSV bytes/str -> {rows, columns, skipped, error}."""
    if isinstance(data, bytes):
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = data.decode("latin-1")
    else:
        text = data

    reader = csv.DictReader(io.StringIO(text))
    headers = reader.fieldnames or []
    if not headers:
        return {"rows": [], "columns": {}, "skipped": 0, "error": "No header row found."}

    col_title = _match(headers, _TITLE_COLS)
    col_source = _match(headers, _SOURCE_COLS)
    col_amount = _match(headers, _AMOUNT_COLS)
    col_period = _match(headers, _PERIOD_COLS)
    col_territory = _match(headers, _TERRITORY_COLS)
    if not col_amount:
        return {"rows": [], "columns": {}, "skipped": 0,
                "error": "Couldn't find an amount/revenue column. Headers seen: " + ", ".join(headers)}

    rows, skipped = [], 0
    for raw in reader:
        amount = _to_amount(raw.get(col_amount))
        if amount is None:
            skipped += 1
            continue
        rows.append({
            "title": (raw.get(col_title) or "").strip() if col_title else "",
            "source": ((raw.get(col_source) or "").strip() if col_source else "") or "Unknown source",
            "amount": amount,
            "period": (raw.get(col_period) or "").strip() if col_period else "",
            "territory": (raw.get(col_territory) or "").strip() if col_territory else "",
        })

    return {
        "rows": rows,
        "columns": {"title": col_title, "source": col_source, "amount": col_amount,
                    "period": col_period, "territory": col_territory},
        "skipped": skipped,
        "error": None if rows else "No usable rows found.",
    }


def analyze(rows):
    """Real findings from parsed statement rows."""
    if not rows:
        return None

    total = round(sum(r["amount"] for r in rows), 2)
    sources = {}
    tracks = {}
    unmatched = 0.0
    periods = set()

    for r in rows:
        sources[r["source"]] = sources.get(r["source"], 0) + r["amount"]
        title = r["title"] or "(no title)"
        if not r["title"]:
            unmatched += r["amount"]
        tracks.setdefault(title, {}).setdefault(r["source"], 0)
        tracks[title][r["source"]] += r["amount"]
        if r["period"]:
            periods.add(r["period"])

    by_source = sorted(({"source": s, "amount": round(a, 2)} for s, a in sources.items()),
                       key=lambda x: x["amount"], reverse=True)
    by_track = sorted(
        ({"title": t, "amount": round(sum(m.values()), 2), "sources": len(m)} for t, m in tracks.items()),
        key=lambda x: x["amount"], reverse=True)

    # Cross-source coverage gaps (estimate): a titled track missing from
    # sources where other tracks earn. Estimated at the track's own average
    # per-source earnings for each missing source.
    all_sources = set(sources)
    findings = []
    for title, per_source in tracks.items():
        if title == "(no title)":
            continue
        missing = all_sources - set(per_source)
        if not missing or len(all_sources) < 2:
            continue
        avg = sum(per_source.values()) / len(per_source)
        est = round(avg * len(missing), 2)
        if est <= 0:
            continue
        findings.append({
            "title": title,
            "missing_sources": sorted(missing),
            "estimated_value": est,
        })
    findings.sort(key=lambda f: f["estimated_value"], reverse=True)

    return {
        "total": total,
        "row_count": len(rows),
        "source_count": len(sources),
        "period_count": len(periods),
        "by_source": by_source,
        "by_track": by_track[:15],
        "unmatched_revenue": round(unmatched, 2),
        "coverage_gaps": findings[:15],
        "gap_estimate_total": round(sum(f["estimated_value"] for f in findings), 2),
    }


def build_royalty_summary(rows):
    """Everything the money pages need from real uploaded statements:
    the core analysis plus a monthly trend and an honest catalog-value
    estimate (labeled, never presented as financial advice)."""
    result = analyze(rows)
    if result is None:
        return None
    monthly = {}
    for r in rows:
        if r["period"]:
            monthly[r["period"]] = monthly.get(r["period"], 0) + r["amount"]
    trend = [(p, round(a, 2)) for p, a in sorted(monthly.items())]
    result["monthly_trend"] = trend[-12:]
    # Valuation signal: annualize the average tracked month, apply a
    # conservative independent-catalog multiple range.
    months = max(len(monthly), 1)
    annualized = round(result["total"] / months * 12, 2)
    result["annualized"] = annualized
    result["valuation"] = {
        "low": round(annualized * 3), "mid": round(annualized * 4),
        "high": round(annualized * 5),
    }
    return result
