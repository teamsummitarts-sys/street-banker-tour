# Beats — the producer's desk

`/beats` is a registry, a licence generator, a cleared list and a set of
usage cases. This document covers the audit pass: the audio a producer
drops in, what gets measured from it, and the private links that carry
one beat to one artist.

## Files

| File | What it holds |
|---|---|
| `templates/beats.html` | The list: state line, tabs, drop zone, LED rows, register drawer |
| `templates/beat_detail.html` | One beat: player, private links, licence generator |
| `templates/beat_share.html` | Standalone reader page — no account, one beat |
| `static/css/beats.css` | Hand-written `bt-*` (the Tailwind build is frozen) |
| `static/js/beats.js` | Bulk upload, in-browser analysis, list player, tabs, drawer |
| `static/js/beat-detail.js` | Detail player, private links, licence presets |
| `static/js/beat-share.js` | The reader's player |
| `static/js/tempokey.js` | The detector, shared with the Rack (SB-13 TMP-1) |
| `db.py` | `beats`, `beat_audio`, `beat_shares`, plus licences/clearances/uses |
| `producers.py` | Summaries, licence types, clearance kinds |
| `tests/test_beats_desk.py` | 9 tests over upload, analysis, links, isolation |

## The state line is not fine print

The top of the page says **"Nothing here scans for you"** and, folded
behind it, why: this desk does not listen to audio or crawl platforms,
and no part of it is Content ID. That sentence is the difference between
a registry and a product that claims to find infringement for you, so
the headline stays visible and only the explanation collapses. It turns
green on its own the day `acr_provider.configured()` becomes true — it
is a status, not a disclaimer, which is why it earns the space.

A test pins both halves.

## Bulk upload, measured in the browser

Drop one file or forty. For each one, in order (never in parallel —
decoding forty tracks at once freezes the tab doing it):

1. `decodeAudioData` in the page.
2. `SBTempoKey.detectBpm` and `detectKey` — the same detector the Rack
   uses. Autocorrelation genuinely cannot tell 85 BPM from 170, so the
   half/double readings are stored in `bpm_alternates` and shown.
3. 480 min/max buckets become the stored waveform, so the list can draw
   forty beats without decoding forty files.
4. `POST /beats/register` mints the registry row; `POST /beats/<id>/audio`
   carries the bytes and the measurements.

**The audio is never analysed server-side and never handed to a third
party.** The server stores bytes and numbers; it does not decode.

A file the browser cannot decode still uploads — it just arrives without
measurements, because undecodable *here* does not mean unplayable in an
`<audio>` tag.

### A measured number never overwrites a typed one

A number the producer typed is a decision. A number this page measured is
a guess with a confidence score attached. So the measurement fills `bpm`
and `song_key` on the registry row **only where they are empty**, and the
response says which fields it filled. The measurement is always recorded
on `beat_audio` regardless, so the detail page can show both.

## Storage

`blob_store.save()` — R2 when configured, disk when not, and the caller
does not branch. Keys are nested (`beats/<user_id>/<uuid>.ext`) because
that is how they want to live in a bucket.

**That nesting exposed a real bug in `blob_store`**: the disk fallback
did a flat `open(join(uploads_dir, fname))`, so every nested key raised
`FileNotFoundError` while the R2 path accepted the same key happily.
`remove()` had the matching bug in reverse — it `basename()`d the path,
deleted nothing, and returned `True`. Both are fixed, and
`safe_local_path()` now refuses any stored path that would resolve
outside the uploads directory.

Audio streams through `/beats/<id>/stream` (owner) or
`/beat/<token>/stream` (link). The storage path itself never reaches the
browser — `_beat_audio_public()` assembles the response field by field.

**One honest limit on revocation.** When R2 is configured, the stream
route hands out a presigned URL with `DEFAULT_TTL` of one hour. Revoking
a link closes the page and the stream route immediately, but a presigned
URL already issued stays valid until it expires. Closing that window
would mean proxying every byte of audio through the app, which is a real
bandwidth cost for a one-hour gap on a link that was, by design, given to
someone the producer chose. Worth knowing; not worth paying for yet.

### The size ceiling has to be one the app can enforce

`MAX_BEAT_BYTES` is **24 MB**, deliberately under
`app.config["MAX_CONTENT_LENGTH"]` (25 MB). Flask rejects an oversize
request *before routing*, so a beat ceiling above that one would be a
number this code prints and never enforces — the producer would get a
bare 413 instead of a sentence telling them what to do. A test asserts
the two stay in that order.

A 3-minute 24/48 stereo WAV is roughly 50 MB, so beats that size have to
be bounced to MP3 or FLAC first. The drop zone says so out loud, and
`beats.js` checks `file.size` before uploading: dropping forty WAVs fails
forty times instantly rather than after forty full uploads.

Non-audio MIME types are refused with 415, oversize with 413.

## Private links

`POST /beats/<id>/share` mints a 32-hex token with an optional label and
an optional lapse (7/30/90 days, or never). `/beat/<token>` is public —
the token is the authorisation, like every other share link on the
platform — and carries **one beat**: no catalogue, no licences, no
producer email. A test asserts every one of those is absent.

Plays are counted, page loads are not: opening a link is not interest.
The count is the producer's one honest signal that the beat was heard.

Revoking, lapsing, or deleting the beat all kill the link in both
directions (page and stream). `delete_beat` takes `beat_audio` and
`beat_shares` with it, so a re-used id can never resurrect old links.

**A private link is a courtesy, not a lock.** The page says so. Anyone
who can play a file can record it, and pretending otherwise would be the
one dishonest thing on it.

## The licence generator

Five presets — standard lease, premium lease, exclusive, work for hire,
free/promo — each prefilling type, territory, term, fee, split and full
terms text. They are **starting points a producer edits**, not contracts
this app stands behind, and the modal says so.

The wording is written to say what each shape gives away, because that is
where producers get hurt on a handshake:

- The exclusive preset says licences already granted stay in force, and
  tells the buyer to ask which exist.
- The work-for-hire preset says plainly that it gives up the back end,
  and that the fee is all of it.
- Every preset separates credit from ownership.

Switching preset after you have written your own terms asks first. A test
pins the three sentences above, because they are exactly the kind of
thing a later "tighten the copy" pass would delete.

## The locked API tab

It says **"Not built."** and lists four things that would live there,
with the note that none of them is scheduled. No fake rows, no
greyed-out switches implying a working thing behind a paywall. A test
asserts the words *Upgrade*, *Coming soon*, *Enable* and *Connect now*
do not appear in that panel.

Fingerprint monitoring is the only one with a working path today: set the
vendor keys and the state line at the top of the page goes green.

## Endpoints

`GET,POST /beats` (the form POST still registers a beat) ·
`POST /beats/register` (JSON, returns an id — bulk drop needs an id, not
a redirect) · `POST /beats/<id>/audio` (multipart: file plus
measurements) · `GET /beats/<id>/stream` · `POST /beats/<id>/audio/delete`
· `POST /beats/<id>/share` · `GET /beats/<id>/shares` ·
`POST /beat-link/<token>/revoke` · `GET /beat/<token>` (public) ·
`GET /beat/<token>/stream` (public).

`/beat/` is in `_PUBLIC_PREFIXES` with the trailing slash: `/beats`,
`/beats/<id>` and `/beat-link/<token>/revoke` all stay behind the login
wall — the last of those is the producer's control, not the recipient's.

## Testing in the browser pane

`requestAnimationFrame` is frozen while the pane is hidden, so a player's
progress never repaints there and a waveform will read as fully unplayed
even while the audio runs. Drive one frame by hand to check the
played/unplayed split. The service worker caches static assets
cache-first — unregister it and clear caches after editing `beats.js` or
`beats.css`, or bump `?v=` and `VERSION` in `static/js/sw.js`.
