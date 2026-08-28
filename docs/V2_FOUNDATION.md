# Street Banker V2 foundation

## Rebuild contract

V2 is developed and verified independently from the current production site.
The production branch, database, uploads, domains, billing account, provider
credentials, and deploy service are not migration inputs. Production data is
introduced only through a reviewed, reversible migration after V2 passes its
security and product acceptance gates.

The homepage is migrated last. Until then, it remains a visual and messaging
reference rather than an active V2 work surface.

## Product invariants

1. A real account never receives sample earnings, activity, offers, fans, or
   analytics under language that describes the data as theirs.
2. Every user-owned record belongs to an account or organization. Paid plans
   change entitlements; they never grant operator access to other tenants.
3. Public assets are explicitly published. Uploaded contracts, statements,
   masters, stems, drafts, and vault files are private by default.
4. An existing account must authenticate before an invitation can attach it to
   a team, roster, label, or partner.
5. Deployment-dependent features use one capability registry and state exactly
   whether they are live, partner-delivered, integration-ready, or examples.
6. Every external claim must be supported by connected behavior or clearly
   marked as a preview before the user sees figures or actions.

## Canonical operating model

V2 has one source of truth for each core object:

| Object | Owns | Replaces or consolidates |
|---|---|---|
| Account | Authentication and personal identity | Duplicated identity assumptions |
| Organization | Artist team, label, partner, roles, permissions | Plan-as-admin authorization |
| Artist | Public identity and organization membership | Account-level artist assumptions |
| Track | Recording, composition, identifiers, ownership | `catalog_tracks` plus `os_tracks` |
| Release | Track grouping, schedule, delivery and campaign state | Competing release surfaces |
| Asset | Storage key, owner, visibility, purpose and retention | Anonymous `/uploads` filenames |
| Statement row | Source financial evidence | Global demonstration royalty songs |
| Fan | Consent, source, artist relationship and activity | Global community state |
| Tour | Tour, show day, crew, settlement and production links | `/tour` plus `/tours` |
| Submission | Music, applicant, review state, reviewer and decision | Mail links plus account scoring |

## Migration sequence

1. Security and tenant boundaries.
2. Canonical Track and Release model.
3. Command Center and onboarding.
4. Distribution, metadata, ownership and collaborator history.
5. Royalties, revenue, reporting and recovery.
6. Smart Links, fan CRM, rollout and Press Desk.
7. Tour OS, Stage Plot, Rack, Lights and production tools.
8. Submit Music and Label Review as one persisted workflow.
9. Services, Lanes and all remaining non-home public pages.
10. Homepage.

## First security gate

Before feature migration begins, V2 must prove:

- existing-account invitations require the invited authenticated session;
- real accounts cannot self-assign paid tiers;
- database backup and infrastructure diagnostics are operator-only;
- post-login redirects remain on the Street Banker origin;
- staging and production refuse to start without a strong session secret;
- assets have explicit ownership and public/private visibility.

The first five controls are implemented in the initial V2 foundation slice.
Asset visibility is the next schema migration because public campaign artwork
and private contracts currently share the legacy upload route.
