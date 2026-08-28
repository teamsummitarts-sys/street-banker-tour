# Street Banker V2

This branch is the isolated rebuild workspace for Street Banker. It preserves
the working product engines and Git history while the architecture, security,
truthful-data boundaries, and public experience are rebuilt. It must not share
a database, upload store, provider credentials, or deployment service with the
current production site.

The current rebuild contract and migration order live in
[`docs/V2_FOUNDATION.md`](docs/V2_FOUNDATION.md).

## Local development

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
APP_ENV=development DATABASE_PATH=/tmp/streetbanker-v2.db .venv/bin/python app.py
```

Never use the production database path for local or V2 testing.

## Historical README

Early scaffold for a music & artists app. This repo starts small: a couple of
shared utility functions that the rest of the app will build on.

## Utilities

`music_utils/duration.py`
- `format_duration(seconds)` — turns a track length in seconds into `mm:ss`
  (or `h:mm:ss` for tracks over an hour).
- `parse_artist_list(raw)` — splits a comma/`&`/`feat.`-separated credit
  string (e.g. `"Artist A, Artist B & Artist C"`) into a clean list of names.

## Dashboard

`app.py` serves an artist dashboard at `/dashboard` with royalty balances
(seeded mock data for now — no live platform integrations yet), key metrics,
an earnings trend chart, and recent payouts.

```
pip install -r requirements.txt
python app.py
```

Then visit `http://127.0.0.1:5000/dashboard`.

## Development

```
pip install -r requirements.txt
pytest
```
