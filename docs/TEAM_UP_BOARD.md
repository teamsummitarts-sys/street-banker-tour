# Team-Up Board (`/tour-board`)

Artists looking for tour partners and venues looking for acts. Server-rendered
first; `static/js/board.js` only adds the region typeahead, genre chips and
auto-opening the post fold. Everything works with JS off.

## Files

| File | What |
| --- | --- |
| `board.py` | Blueprint. `init(app, base_url)` registers it; `base_url` is a callable used in emails. |
| `board_store.py` | Schema migration (`init_board()`), encoding repair, listings, threads, watches, events, stats, verified chips. |
| `board_taxonomy.py` | Regions (16 macro regions + ~60 metros, with lat/lng), genres (27, with aliases), parsers for free text (`parse_region`, `parse_window`, `parse_genres`, `parse_draw`). |
| `templates/board/*` | `index` (board + post form), `listing` (permalink), `thread`, `inbox`, `edit`, `renewed` (standalone, no session needed). |
| `static/css/board.css` | Hand-written `tb-*` classes (the Tailwind build is frozen). |
| `tools/repair_board_encoding.py` | One-shot CLI: `--dry-run` lists rows, default applies the repair. Also runs automatically at boot. |
| `tests/test_team_up_board.py` | Foundation tests (encoding, parsers, posting/coaching, threads, lifecycle, filters, watches, chips, doorways). |

## Data

`tour_board` keeps its original columns (`title, region, window, genre, details`)
so old listing URLs and rows survive, and gains structured ones:
`region_code, region_text, window_start, window_end, genres (JSON), draw_min,
draw_max, parse_flag, expires_at, renew_token, renew_notice_at, filled_via,
filled_at, updated, structured`. Legacy rows are parsed into the structured
columns once (`migrate_legacy_listings`); anything that could not be parsed
keeps the free text and a `parse_flag` so the UI can say "as written".

Threads: `board_threads` (listing × replier, one thread each) and
`board_messages`. Legacy `board_replies` rows become the first message of a
thread. No email address is ever shown — both sides are accounts, the inbox is
`/tour-board/inbox`, and unread counts come from `last_read_*` timestamps.

Watches: `board_watches` = saved search (kind/region/genre/window). A new
listing that matches triggers an in-app notification and an email when the
mailer is configured. Events go to `board_events` for the activity stats on
the empty state ("0 open · 3 posted this month · 9 replies sent").

## Encoding

`board_store.repair_text()` undoes the known manglings end to end: percent-
encoded UTF-8 (`%E2%80%94`), percent-encoded Windows-1252 (`%97` → `—`),
UTF-8-as-cp1252 mojibake (`â€”`), and raw C1 control bytes. It is idempotent
and leaves clean text (including real `%` usage like "50%-60% door split")
alone. The repair runs on every row at boot and is available as a CLI.
All forms post UTF-8 and all pages are served UTF-8.

## Lifecycle

open → closed / filled; every listing expires 60 days after posting. The
sweep (`_sweep_renewals`, runs on board GETs) emails one renew link per
listing 5 days before expiry; the link is public (`/board-renew/<id>?t=…`),
single-use, and only renews — it never exposes the listing or the account.
Owners can also renew, edit, close, reopen and delete from the listing page.
"Mark filled" from a thread stamps `filled_via` and the listing earns the
★ MATCHED ON THE BOARD badge (`matched` in `_row`).

## Doorways

* Tour Hub calendar (list view) — off days / travel days link to
  `/tour-board?new=1&kind=artist&title=…&region=…&from=…&to=…` which opens the
  post form prefilled.
* Nav → Touring → Team-Up Board; inbox unread count on the board header.

## Verified chips

`verified_chips(user_id)` pulls from platform data only (shows played through
Tour Hub, home market from the profile, upcoming dates) and every chip is
labelled with its source. Self-reported numbers (draw) are always shown as
"self-reported".
