"""Config-driven data for the Reports page.

Composes the report library (grouped by category), a KPI summary, the
live "recently generated" history, and the illustrative scheduled-report
list into a single dict the template renders with zero hard-coded content.
"""

from royalty_data import (
    REPORT_CATEGORY_ORDER,
    get_available_reports,
    get_report_history,
    get_scheduled_reports,
)

CATEGORY_TONE = {
    "Financial": "border-amber-500/20 bg-amber-500/10 text-amber-400",
    "Recovery": "border-green-500/20 bg-green-500/10 text-green-400",
    "Rights": "border-blue-500/20 bg-blue-500/10 text-blue-400",
    "Investor": "border-purple-500/20 bg-purple-500/10 text-purple-400",
}

FORMAT_TONE = {
    "PDF": "border-red-500/20 bg-red-500/10 text-red-400",
    "CSV": "border-green-500/20 bg-green-500/10 text-green-400",
    "XLSX": "border-emerald-500/20 bg-emerald-500/10 text-emerald-400",
}


def get_reports_data(demo=False):
    """`demo` decides whether the example saved schedules are included.

    There is no scheduler behind them. Nothing runs monthly, nothing is
    emailed to "2 recipients", and the next-run dates are literals - the
    same three rows for every account, under a heading that reads as
    configuration the artist set up themselves. Real accounts get an
    empty list, and the page says the scheduler is not built yet rather
    than showing three jobs that will never run.
    """
    reports = get_available_reports()
    history = get_report_history()
    scheduled = get_scheduled_reports() if demo else []

    # Group the library by category, preserving the canonical order.
    grouped = {}
    for r in reports:
        grouped.setdefault(r["category"], []).append(r)
    categories = [
        {
            "name": name,
            "tone": CATEGORY_TONE.get(name, CATEGORY_TONE["Financial"]),
            "reports": grouped[name],
        }
        for name in REPORT_CATEGORY_ORDER
        if name in grouped
    ]

    formats = sorted({r["format"] for r in reports})

    return {
        "summary": {
            "total_reports": len(reports),
            "categories": len(categories),
            "scheduled_active": sum(1 for s in scheduled if s["enabled"]),
            "generated_session": len(history),
        },
        "categories": categories,
        "scheduled": scheduled,
        "recent": history,
        "formats": formats,
        "format_tone": FORMAT_TONE,
    }
