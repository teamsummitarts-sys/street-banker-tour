"""Config-driven data for the Dispute / Audit center.

Formal disputes raised against payers (distributors, PROs, labels) when
royalties look wrong — underpayment, unmatched usage, misattribution, or
a full audit. Each dispute moves through a resolution pipeline; the
advance action steps it to the next stage. Disputes live in a
module-level store so status changes persist for the session.

Amounts in dispute are illustrative demo data referencing real song
titles where applicable.
"""

from royalty_data import get_songs

# Linear resolution pipeline; a dispute advances one stage at a time.
STAGES = ["Filed", "Submitted", "Under Review", "Resolved"]

STAGE_TONE = {
    "Filed": "border-gray-500/20 bg-gray-500/10 text-gray-300",
    "Submitted": "border-blue-500/20 bg-blue-500/10 text-blue-400",
    "Under Review": "border-amber-500/20 bg-amber-500/10 text-amber-400",
    "Resolved": "border-green-500/20 bg-green-500/10 text-green-400",
}


def _seed():
    titles = [s.title for s in get_songs()] or ["Untitled"]

    def title(i):
        return titles[i % len(titles)]

    return [
        {"id": "disp-1", "title": "Underpaid streaming mechanicals", "counterparty": "The MLC",
         "type": "Underpayment", "song": title(0), "amount": 640.00, "stage_index": 2, "opened": "2026-04-18"},
        {"id": "disp-2", "title": "Unmatched YouTube Content ID revenue", "counterparty": "YouTube",
         "type": "Unmatched Usage", "song": title(1), "amount": 415.50, "stage_index": 1, "opened": "2026-05-02"},
        {"id": "disp-3", "title": "Performance royalties attributed to wrong writer", "counterparty": "ASCAP",
         "type": "Misattribution", "song": title(2), "amount": 1220.00, "stage_index": 0, "opened": "2026-06-10"},
        {"id": "disp-4", "title": "Distributor statement audit", "counterparty": "DistroKid",
         "type": "Audit", "song": None, "amount": 2850.00, "stage_index": 3, "opened": "2026-02-28"},
    ]


_disputes = _seed()


def reset_disputes_state():
    global _disputes
    _disputes = _seed()


def _decorate(d):
    stage = STAGES[d["stage_index"]]
    return {**d, "stage": stage, "resolved": stage == "Resolved"}


def advance_dispute(dispute_id):
    for d in _disputes:
        if d["id"] == dispute_id:
            if d["stage_index"] < len(STAGES) - 1:
                d["stage_index"] += 1
            return _decorate(d)
    return None


def get_disputes_data():
    disputes = [_decorate(d) for d in _disputes]
    open_disputes = [d for d in disputes if not d["resolved"]]
    return {
        "summary": {
            "open": len(open_disputes),
            "amount_in_dispute": round(sum(d["amount"] for d in open_disputes), 2),
            "recovered": round(sum(d["amount"] for d in disputes if d["resolved"]), 2),
            "total": len(disputes),
        },
        "disputes": disputes,
        "stages": STAGES,
        "stage_tone": STAGE_TONE,
    }
