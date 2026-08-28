"""Repair mangled text on the Team-Up Board (and show what would change).

    python tools/repair_board_encoding.py            # dry run
    python tools/repair_board_encoding.py --apply    # write the fixes

Runs against DATABASE_PATH (or instance/streetbanker.db). The same repair
runs automatically, idempotently, at app start via board_store.init_board.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import db as store  # noqa: E402
import board_store  # noqa: E402

if __name__ == "__main__":
    apply = "--apply" in sys.argv
    store.init_db()
    changes = board_store.repair_all_text(apply=apply)
    for table, rid, field, before, after in changes:
        print("%s %s.%s\n   - %r\n   + %r" % (table, rid[:8], field, before, after))
    print("%d change(s) %s" % (len(changes), "applied" if apply else "found (dry run; pass --apply)"))
