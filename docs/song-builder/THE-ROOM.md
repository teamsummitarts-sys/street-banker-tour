# The Room — test release

Approved name: The Room by Street Banker. Tagline: Bring an idea. Build a record.
Use the owner's touring-console reference: black equipment faceplates, silver
flight-case rails, metallic knobs, amber selected sections and clear waveforms.
Noise Lab is locked. Do not modify its code, settings or stored patches.
Keep /song-builder URLs and portable .sbsong files compatible with existing data.

This release changes the Room title/header, retains five disabled rack knobs in
an empty session, and provides Create a section with AI beside the local demo.
That button opens Takes and focuses the prompt; it never spends provider credits.
The account's existing ElevenLabs connection already reports configured, with a
successful section take observed in the live Takes panel on 2026-09-07.

## Storage release gate

The previous test song disappeared across deployment. The host database being
on the disk does not protect this module's separately configured database/audio.
Do not redeploy before copying the existing Room store. In particular, the
live session currently has an unaccepted generated take that must be preserved.

1. Stop Room edits and wait for music jobs to finish. Keep it idle until release.
2. Run the standalone `song_builder/migrate_storage.py` in the current V2 shell
   from the project root BEFORE deploying this branch. It can be pasted between
   `python - <<'PY'` and `PY`. It requires only Python's standard library.
3. Confirm the reported destination `/var/data/v2/the_room` and copied asset count.
4. Set only `SONG_BUILDER_DATA_DIR=/var/data/v2/the_room` in V2, then deploy.
   Preserve all existing environment variables, including Noise Lab settings.
5. Confirm the Room footer reports persistent storage, the existing candidate
   still plays, and projects reopen with their audio after another restart.

The script keeps the original files, refuses an existing destination, checks for
active jobs, backs up SQLite consistently, copies all referenced assets including
unaccepted candidates, and verifies their bytes. It is a quiescent migration:
changes made after its snapshot are not included. Do not resume edits early.
On a partial filesystem failure, inspect the destination rather than retrying
over it. Do not delete either copy until the migration is verified.

The capability response now marks storage durable only when the real /var/data
mount is present and the database and audio directory resolve underneath it.
This code does not silently relocate an existing store at application startup.

## Verification

30 Python checks pass, including new migration/reopen, unaccepted-audio retention,
active-job refusal, missing-file failure and mounted-path checks. Nine native-audio
and DOM integration checks pass, including the empty rack's five disabled controls.
The existing pure JavaScript unit suite is also part of release verification.
No new paid provider request was made. Physical iPhone touch behavior and full
live generation/separation/accept/export remain acceptance checks, not claimed
complete. The layout is functional CSS, not a pixel match to a generated image.

After storage is verified, use the existing candidate to test audition, acceptance
into a new version, trimming, rack changes, export and reopening. A paid separation
or additional generation should be initiated by the owner during the music test.
