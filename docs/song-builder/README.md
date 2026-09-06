# Portable Song Builder — development build

Standalone Flask blueprint and native browser modules for section-based songs
and layered audio. This is source work, not a deployed or production-approved feature.

## Host integration

V2 registers the blueprint with its existing authenticated user resolver. The
feature is off by default. Set `SONG_BUILDER_ENABLED=1` in a separately approved
test environment to expose `/song-builder/`.

Set `SONG_BUILDER_DATA_DIR` to a private writable directory. Default storage is
under Flask's instance directory, not the host database. Back up both SQLite and
audio files together. An ephemeral hosting filesystem is not durable storage.

For a later V1 migration, copy the `song_builder` package and register:

```python
import song_builder
song_builder.init(app, current_user=resolve_signed_in_user,
                  data_dir='/private/song-builder',
                  url_prefix='/song-builder', return_url='/studio')
```

The resolver must return a dictionary with a stable account `id`, or `None`.
Use V1's own storage and account resolver; do not share V2's runtime directory.
Portable `.sbsong` files embed audio and import as new owned projects.

## Optional provider

Local arrangement, audio import, synthesis demo and mix export need no music API.
Generation and stem separation additionally require `SONG_BUILDER_MUSIC_ENABLED`
and server-only `ELEVENLABS_API_KEY`. No OpenAI calls or credential changes are
introduced. Provider calls may incur charges and have not been tested live.
Generation produces a candidate for one section; contextual continuity with
neighboring sections is not guaranteed. Candidates require explicit acceptance.

## Verification and remaining gates

```sh
python3 -m pytest -q tests/test_song_builder_backend.py tests/test_song_builder_host.py
node --test tests/song_builder/*.test.mjs
node --check song_builder/static/ui/controller.mjs
```

Latest local verification: 19 Python boundary/host tests and 19 JavaScript
core/backup/recovery tests passed. Controller syntax check passed. Unknown job
outcomes retain the exact request in account-session-scoped browser storage;
explicit recovery reuses its ID. A backend test confirms retries return the same
job even after later project edits. No automatic paid retry is performed.

The cloud browser URL policy blocked the local preview; browser verification
was not completed and no alternate route was used to bypass that restriction.

Remaining before release: browser/iPhone recording and playback verification,
visual review, full V2 application regression, paid-provider contract testing,
and independent review.
Do not enable paid music generation until those checks are complete.

Bundled Archivo font is distributed under the accompanying SIL Open Font License;
source: https://github.com/google/fonts/tree/main/ofl/archivo .
