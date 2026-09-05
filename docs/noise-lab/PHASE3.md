# Phase 3 — private patch library

Status: implementation prepared for review, not activated on Render. The owner
reported that the previous release's generation, A/B, Undo and audio export all
worked on their iPhone. This is user-reported device evidence, not a measured
listening study or a sustained-playback certification.

## Architecture and scope

Base: `34257fb34282d889b9fd5b86292c014dfc811338` in
`teamsummitarts-sys/v2-street-banker`. Retains Flask, Jinja, browser modules and the
existing `db.get_db()` SQLite transaction boundary. No dependencies or DSP
changes. Account identity comes only from the host's current-user resolver.
Owned tables are created lazily in the existing host database after authenticated
access and explicit storage activation. They reference the existing users table.
No new service, V1 repository, marketplace or hardware integration is involved.

The UI adds a name, Save new patch, Save new version, a private patch selector,
version selector, Load version, Export all versions, and confirmed whole-patch
deletion. Merely browsing a patch does not change the current sound. Loading
uses the existing B/Undo path. Saving an older version appends a new version;
it never rewrites history. Editing while a save is pending preserves the newer
working settings and reports that they remain unsaved. Account saving uses fetch
and never navigates to a file. History export reuses the already-tested two-step
iPhone file preparation/share flow. Audio and prompts are excluded from saves.
Saved settings can be reloaded after closing a page; source audio must be loaded
separately. There is no automatic background save.

## API and ownership

All paths below are under `/noise-lab/api/patches`. The module and host account
gates protect reads and writes. Mutations additionally require the existing
account-bound CSRF token and same-origin checks. No request accepts an owner ID.
Other users' and missing patch IDs receive the same 404. Private responses are
no-store and vary by cookie. An account-scope change invalidates the displayed
library and disables generation until the page is reloaded in the correct session.

| Method/path | Body or response |
| --- | --- |
| GET collection | `{patches:[{id,name,headVersion,updated}]}` |
| POST collection | Exact `{requestId,name,recipe}`; returns `{patch}` |
| GET `/{id}` | `{patch:{id,name,headVersion,updated,versions:[...]}}` |
| POST `/{id}/versions` | Exact `{requestId,baseVersion,name,recipe}`; returns `{patch}` |
| GET `/{id}/export` | `{archiveVersion:1,patch:...}` with all saved versions |
| DELETE `/{id}` | Exact `{baseVersion}`; deletes the patch and all versions |

Each version includes `version`, `name`, `created`, `recipe`, and `compatible`.
Create/append returns 201; replay of a completed identical request returns 200
with its original saved version snapshot. The UI does not automatically retry.
If a response is lost, a manual retry of the same pending save reuses its UUID.
A changed request with the same UUID is rejected, and a retry after deletion
returns 410 instead of recreating the deleted patch. A stale base version returns
409 for append or deletion. SQLite `BEGIN IMMEDIATE` serializes quota checks,
version comparisons and writes. Partial schema and write failures roll back.

Bounds: 8 KiB request body; patch names 1–80 characters; 50 patches/account;
100 versions/patch; 5,000 recorded save-request IDs/account. The request ceiling
persists across patch deletion and is not advertised as a daily quota. It bounds
idempotency metadata for this validation prototype. Broader pilot expansion
requires reviewing these limits and durable AI generation quotas separately.

## Compatibility and removability

Storage schema: `noise_lab_store_meta` version 1. Owned content tables:
`noise_lab_patches`, `noise_lab_patch_versions`, `noise_lab_patch_requests`.
An unknown/partial database schema fails closed and is never silently replaced.
Before a future schema change, add an explicit migration and verify old-version
reading and rollback. The current engine and recipe schema remain
`noise-lab-1.0.0` and 1. The prompt contract remains `noise-lab-prompt-1.0.0`.

Unsupported recipes already in storage remain exportable with `compatible:false`;
unparseable stored text is preserved in `recipeRaw`, never run or repaired.
The browser refuses to apply unsupported data and retains the working sound.
Normal single-recipe downloads remain compatible with the existing import flow.
The all-versions archive is a versioned data export; it is not accepted as a
single-recipe import. To reuse a supported archived version, extract that
version's `recipe` object into a recipe JSON file. Full-database recovery uses
the native SQLite backup procedure below.

Removal: first export valued versions, disable storage, remove the existing
Noise Lab registration and owned source/assets/tests/docs. Drop only the four
owned tables as a separately reviewed data deletion (child tables first). The
shared host database/users and disk continue to belong to V2. Do not delete the
disk to remove Noise Lab. Moving to another Flask host requires equivalent
current-user resolution, SQLite `users` IDs and `db.get_db()` semantics.

## Retention, deletion and backup behavior

Saved names and settings remain in the host database until the owner deletes the
patch or the host deletes the account. Whole-patch deletion removes version
content in the active database. Minimal owner-linked request IDs, operation IDs,
fingerprints and version numbers remain until account deletion/module removal to
prevent replay from resurrecting deleted content. They contain no stored patch
names, recipes, prompts or audio. Hashes are metadata, not anonymous data.

Only the authenticated owner can access these records through the patch API.
Authorized V2 operators can access the database and native backup archives; this
is not end-to-end encryption. The host's existing owner-only `/backup` creates a
consistent SQLite snapshot and includes host uploads. Protect those archives as
private account data. No automatic off-site backup schedule or retention policy
has been verified or enabled by this change. User downloads and operator backups
are separate copies that this API cannot erase. Restoring an older database can
restore deleted content: operators must reconcile deletions before reopening
access. A durable disk is not itself a verified database recovery plan.

Render documents encrypted disks and daily disk snapshots retained for **at
least** seven days; no maximum deletion deadline is verified. Do not treat a disk
snapshot as a consistent database backup or use it for database recovery.
Use native SQLite snapshots, verify integrity and rehearse restores. Browser
Clear session releases local audio/edits and pending save bookkeeping, but does
not delete saved account patches, downloaded copies or provider logs. Phase 2's
AI description retention and process-local allowance behavior is unchanged.

## Concrete activation plan — cost approval pending

Inspected exact V2 service `srv-dad6q3gae00c7393s02g` in confirmed Lucas workspace
`tea-d96uk5kvikkc73d9clag`: Python, `main`, auto-deploy off, Free, one instance,
Gunicorn one worker/four threads, no persistent disk. SQLite on that filesystem
can disappear on a restart/redeploy/spin-down. The module must not advertise
private saving on this current configuration.

Proposed paid change: V2 Starter compute (published $7/month) plus one 1 GB disk
(published $0.25/GB/month), approximately **$7.25/month**, excluding tax, API
usage and any workspace/usage charges. Reconfirm the displayed price before the
paid change. This is a new recurring charge, requiring user approval. The Render
Disks skill also establishes the single-instance and brief-deploy-downtime
constraints. No new Blueprint or service is proposed.

Activation sequence, only after approval:

1. Recheck the exact V2 service, commit, auto-deploy-off state and no-Blueprint
   status. Freeze V2 writes for the migration window. Before any plan/config/disk
   change that restarts the Free instance, obtain the authenticated owner's
   current `/backup` archive. Preserve it securely, verify its SQLite integrity
   and record user IDs/counts. Do not print account rows, hashes or credentials.
   If this backup cannot be obtained, stop before changing the service.
2. Review and merge the tested Phase 3 commit. Upgrade only this V2 service to
   Starter and attach one 1 GB disk at `/var/data`. These operations can restart
   the service; use their deployment behavior and do not trigger duplicate deploys.
   Saving remains disabled until restore and configuration are complete.
3. Upload the verified native database snapshot to the V2 disk through an
   authenticated Render/SSH operator path. Create the destination parent
   `/var/data/v2` with private directory permissions (0700). Use
   `python -m noise_lab.storage_admin restore-copy` to create
   `/var/data/v2/streetbanker.db`, without replacing an existing file. The helper
   requires an existing parent directory. Restore the **whole host database**,
   including existing user IDs, so ownership survives. The host resolves its
   uploads directory beside the database; restore required uploads from the
   owner's archive to `/var/data/v2/uploads` before activating the database path.
   Preserve archive contents and access permissions; do not silently discard them.
4. Set only these reviewed V2 settings, preserving all other environment entries:
   `DATABASE_PATH=/var/data/v2/streetbanker.db`,
   `NOISE_LAB_PERSISTENT_ROOT=/var/data`,
   `NOISE_LAB_PATCH_STORAGE_ENABLED=1`. The destination must be the verified
   restored database. Do not change the owner, session secret or provider keys.
5. Verify the resulting single deployment's exact merged commit. Check the owner
   login, cloud storage capability, a real save/reload/version/export/delete
   walkthrough, then controlled service restart/reopen persistence. Compare user
   IDs and validate existing V2 records. Record actual results and downtime.
6. Before enabling a musician pilot, save a native backup and rehearse recovery
   to a separate empty file. Establish an operator-owned backup schedule,
   retention destination and deletion-reconciliation procedure, or disclose that
   only manually exported recovery copies exist. No schedule is created here.

`storage_ready()` requires both the explicit flag and a real mounted persistent
root containing the resolved host database path. Tests bypass the physical mount
check only under Flask TESTING. Production has no ephemeral fallback. A storage
outage keeps local audio, manual presets and local exports available.

Safe local/operator commands (explicit paths; no overwrite):

```
python -m noise_lab.storage_admin snapshot --source /path/to/source.db --destination /path/to/new-snapshot.db
python -m noise_lab.storage_admin restore-copy --source /path/to/verified-snapshot.db --destination /var/data/v2/streetbanker.db --persistent-root /var/data
```

Rollback: disable `NOISE_LAB_PATCH_STORAGE_ENABLED` and, if necessary, roll back
the application commit on the same V2 service while retaining the persistent
database path and disk. Earlier releases ignore these additive tables. Do not
roll back by deleting data, downgrading to ephemeral storage or restoring a disk
snapshot. If a database restore is required, use a verified native copy and
review the records and deletions affected before reopening access.

References checked 2026-09-05: [Render pricing](https://render.com/pricing),
[persistent disks](https://render.com/docs/disks),
[Free service storage limits](https://render.com/docs/free).
