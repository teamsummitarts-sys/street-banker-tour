# TOUR — the touring operating system

`/tours`. Built on the existing Tour Hub rather than beside it: a show
is still a `tour_shows` row, so `/tour`, `/tour/<id>`, the public
`/showday/<token>` page and the Money Queue keep reading the same data.
TOUR groups shows into a tour and adds everything a run needs.

## Files

| File | Role |
| --- | --- |
| `tour_store.py` | Schema (27 tables + 2 columns on `tour_shows`) and accessors. Owner `user_id` on every row. No permission logic. |
| `tour_engine.py` | Rules, no I/O: readiness arithmetic, live/planning mode, NEXT, My Day, change severity, Ask Tour, the extractor, CSV/ICS/paste importers, dedupe, money derivation, CSV/ICS writers. |
| `tour_os.py` | Blueprint: routes, `require_tour(scope)`, server-side redaction, share links, uploads, wiring. |
| `tour_seed.py` | Fictional example tour. Only reachable via `POST /tours/seed-demo` for the demo account; CLI for dev. |
| `templates/tour/**` | Shell, 25 pages, 20 Show Command tabs, 5 print views, 9 share scopes. |
| `static/css/tour-os.css` | Hand-written `to-*` classes (the Tailwind build is frozen). |
| `tests/test_tour_os.py` | 21 tests: engine units + owner flows + a narrow member checked across pages, exports, Ask, search, share links, downloads. |

## Access model

- Owner = `tours.user_id`. Members = `tour_members` rows: invited by
  email → `/tours/join/<token>` → active with a scopes list.
- Scopes: `view edit schedule travel hotel people advance production
  guests vip marketing content merch financials files admin`. `admin`
  implies all; only the owner can hand out `admin`.
- Role presets (`tour_manager`, `production`, `artist`, `crew`,
  `driver`, `photographer`, `management`, `accountant`, `viewer`) are
  starting points; every membership is edited per scope.
- Unknown tour or non-member → 404. Missing scope → 403 page.
- **Redaction happens before render**, in `tour_os.py`:
  `_strip_money` (money fields blanked without `financials`),
  `_redact_people` (private phones, emergency contacts), `_redact_rooms`
  (room numbers), `_redact_lodging` / `_redact_travel` (confirmation,
  payment, legs you are not on), `_visible` (management / private
  rows), `_files_for` (private and money-category files),
  `_changes_for` (the change log is not a side door), and Ask Tour is
  given only the already-filtered context.
- Owning (creating) a tour needs the Artist tier; being invited does
  not — `/tours` is deliberately outside `plans._ARTIST_PATHS`.
- No named-person exceptions exist anywhere.

## Routes (summary)

Tour: `/tours`, `/tours/new`, `/tours/<t>`, `/my-day`, `/calendar`
(+`.ics`), `/days/add|<d>/edit`, `/shows`, `/shows/attach`,
`/schedule` (+`/add`, `/<i>/edit`), `/travel` (+`/add`, `/<i>/edit`,
`.csv`), `/hotels` (+`/add`, `/<l>/edit`, `/<l>/rooms`,
`/<l>/rooming[?format=csv]`), `/venues` (+`/save`), `/people`
(+`/save`, `.csv`), `/guests`, `/money` (+`.csv`), `/expenses/add|
<e>/delete`, `/merch` (+`/products/add`), `/marketing`, `/content`
(+`/<c>`), `/tasks` (+`/add`, `/<a>/status`), `/files` (+`/upload`,
`/<f>/download`, `/<f>/delete`), `/changes` (+`/<c>/ack`), `/ask`,
`/map`, `/import`, `/exports`, `/itinerary` (+`.csv`), `/share`
(+`/new`, `/<l>/revoke`), `/team` (+`/invite`, `/<m>`), `/settings`,
`/search`, `/mode`, `/setlists/<s>/print`.

Show Command: `/tours/<t>/shows/<s>?tab=` overview · schedule ·
advance · inbox · travel · hotel · venue · people · guests · vip ·
production · money · merch · marketing · content · setlist · files ·
tasks · notes · activity. POST endpoints under the same prefix: `/ext`,
`/notes`, `/delete`, `/standard-day`, `/copy-schedule`,
`/advance/<key>`, `/advance-bulk`, `/inbox`, `/venue/from-advance`,
`/guests/add`, `/guests/<g>`, `/guests.csv`, `/vip/add`, `/vip/<v>`,
`/money`, `/merch`, `/marketing`, `/content/bulk`, `/setlist`,
`/day-sheet`, `/settlement-summary`.

Public: `/tour-share/<token>` (GET, POST for password / check-in) and
`/tour-share/<token>/file/<f>` (production scope only). Join:
`/tours/join/<token>` (login required).

## Honesty rules that are enforced in code

- Readiness % = done ÷ applicable checklist categories, per show; the
  tour figure is the mean. Nothing is assumed complete.
- Money cards read "no money entered" rather than zero; shows without
  numbers are excluded from tour totals, not counted as zero.
- The extractor proposes; the review step writes; every write it
  causes is logged with `source = extract`.
- Ask Tour answers from rows or says "has not been entered".
- Share links are one scope + one show (or one hotel), token-only,
  optional password (salted SHA-256), optional expiry, revocable, and
  the day sheet / driver / production variants go through the same
  redaction as an unscoped member.
- Imports preview first; duplicates (same date + venue) are skipped,
  conflicts shown. No Master Tour scraping or undocumented APIs — CSV,
  .ics and pasted text only.
- PDFs are refused with the reason (no extraction library), not
  silently emptied.
- Uploads are capped at 25 MB (`tour_os.MAX_UPLOAD`; the app's global
  `MAX_CONTENT_LENGTH` matches it) and an oversize body gets the
  module's own 413 page, not a bare Werkzeug one. Files land in
  `tour_uploads/` next to the database (or R2 under `tour/`), with a
  fallback to `instance/tour_uploads` if the disk path cannot be created.
- The service worker (`sb-v117`) caches Tour Home, My Day and Show
  Command per full URL — query string included, so tabs and dated days
  survive offline.

## Deferred (said plainly in the UI)

Map tiles and drive-time estimates; PDF text extraction; ticketing /
travel / hotel / accounting integrations; push notifications (in-app +
email only, email only for critical and only with a real sender); fan
capture kiosk (the table and consent fields exist; capture UIs do not);
a language model behind the advance inbox or Ask Tour.
