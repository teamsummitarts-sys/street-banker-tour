# Street Banker V2: direct Render deployment

This repository deploys only to the existing V2 comparison service. It does
not use a Render Blueprint because name-based Blueprint sync can create or
adopt a different service.

## Immutable target

- Service ID: `srv-dad6q3gae00c7393s02g`
- Service name: `street-banker-v2-workflows`
- Repository: `teamsummitarts-sys/v2-street-banker`
- Branch: `main`
- Public URL: `https://street-banker-v2-workflows.onrender.com`
- Auto-deploy: off
- Plan: Free, with ephemeral local data

Never select a deployment target by name. Never apply a Blueprint or create a
new service for this release. Any service ID or hostname other than the V2
target above is outside this runbook and must not be inspected or changed.

## Preflight

1. Fetch the service by the exact ID above and verify its name, repository,
   branch, URL, plan, and auto-deploy state match this document.
2. Confirm in Render that no active Blueprint manages this service. If the
   service is Blueprint-managed, stop: detach it from that Blueprint or disable
   its sync before changing environment settings or deploying. Deleting a
   Blueprint file from Git does not detach an already-managed service.
3. Verify the build command is `pip install -r requirements.txt` and the start
   command is the `web` process in `Procfile`.
4. Confirm the service has no disk. V2 records and the bootstrapped owner may
   be recreated after a restart or redeploy because Free local storage is
   ephemeral.
5. Replace the environment as one reviewed set. The only required settings
   are `APP_ENV=staging`, the exact V2 `PUBLIC_BASE_URL`,
   `SIGNUP_MODE=closed`, a strong `SECRET_KEY`, exactly one `OWNER_EMAILS`, a
   matching `OWNER_BOOTSTRAP_EMAIL`, and a valid Werkzeug
   `OWNER_BOOTSTRAP_PASSWORD_HASH`.
6. Confirm the environment has no `DEMO_PASSWORD`, production database or
   storage path, bucket, Stripe secret, provider credential, or non-V2 URL.
   Secret values must remain in Render and must never be committed.

## Release and verification

1. Record the reviewed commit SHA after CI passes.
2. Merge that SHA to `main`.
3. Trigger one manual deploy using the exact V2 service ID.
4. Require Render status `live` and confirm the deployed commit SHA matches.
5. Verify the login page exposes no signup or demo path. Sign in as the sole
   owner, confirm `/team` is the first destination, and exercise the Manager
   objective, plan approval, assignment, evidence, review, and closure loop.
6. Inspect V2 deploy logs for application errors. If verification fails, roll
   back only within the same V2 service ID.

There is no cross-service cutover in this process. The public comparison URL
stays attached to the existing V2 service throughout the deployment.
