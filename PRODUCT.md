# Street Banker V2 Product Architecture

<!-- impeccable:product-schema 2 -->

## Platform

Web application suite. V2 is operationally and technically isolated from V1.

## Users

Independent artists and artist-led companies operating releases, rights, revenue,
campaigns, production, opportunities and touring without a conventional full-time staff.
Specialist products may also serve managers, producers, tour managers and small teams
who do not use every Street Banker workflow.

## Product Purpose

Street Banker is the artist operating system. It turns artist, song, audience,
rights, revenue and campaign information into accountable next actions and stored
work. Insights are not the end product: the system must connect intelligence to a
real decision, task, workflow, deliverable or measurable result.

## Customer-Facing Product Architecture

Street Banker is the parent operating system. Four specialist products sit beside it
as distinct V2 product experiences:

1. **Reach** — opportunity discovery, prioritization, submissions and tracking.
2. **The Room** — creation, Analyze & Improve, Sound DNA, reference comparison,
   tempo/key experimentation, structured blueprints and collaboration.
3. **Noise Lab** — sound design and processing: source audio, validated effect
   recipes, macros, A/B, undo, private patches and export.
4. **TOUR** — touring operations: days, shows, advancing, schedules, travel, hotels,
   people, guests, VIP, production, money, merch, marketing, content, files, tasks,
   setlists, team permissions, exports and share links.

Canonical product shorthand:

- **Street Banker runs the artist.**
- **The Room builds the music.**
- **Noise Lab shapes the sound.**
- **Reach finds the opportunity.**
- **TOUR runs the road.**

These products share Street Banker identity and selected underlying records where
appropriate, but each specialist product should have a focused product shell rather
than inheriting the entire Street Banker navigation.

## Street Banker Core

The parent OS owns the cross-product operating layer and the business systems that do
not need their own product identity:

- Command Center
- Artist Twin
- artist profile / Artist OS architecture
- Metadata Passport
- Rights & Ownership
- Artist EQ intelligence
- Fan Intelligence
- Readiness / qualification
- Trust Score inputs
- Capital / advance qualification
- Rollout Studio
- Smart Links
- Creative Studio, including artwork generation
- Studio Split
- Hours Desk
- Royalty Sweep and recovery workflows
- account, team, files and business infrastructure

**Royalty Sweep is a major Street Banker workflow, not a fifth specialist product in
the app switcher.** Its value proposition remains direct financial recovery: find
missing money, identify the rights or metadata problem, open the recovery workflow,
and track the result.

## Intelligence Model

Three intelligence layers must remain distinct in language and implementation:

- **Artist Twin understands the artist** — a living intelligence model of the artist,
  catalog, audience and activity. It is an intelligence spine, not a standalone app.
- **Sound DNA understands the music** — a named feature inside The Room. The duplicate
  term "Song DNA" is retired.
- **Signal understands market movement** — internal comparative intelligence used by
  Street Banker operators and, where appropriate, downstream product logic.

Artist EQ, Trust Score, qualification logic, Rack/audio-readiness logic and similar
engines may remain valuable internal components without becoming separate products.

## Internal-Only Systems

The following are company operating systems and must not appear as ordinary artist
products or navigation destinations:

- Operator Desk
- Signal
- voice-agent framework
- meeting intelligence / transcription
- lead and task escalation
- internal support and operational tools

Operator Desk is the company cockpit. Command Center is the artist cockpit.

## Development / Gated Surfaces

A route or module is not production merely because it renders.

- **Release Signal** remains development / coming soon until its real-data loop is
  production-ready.
- **Portable Song Builder** remains separately flagged and default-off. Useful
  technology may feed The Room, but the development route must not be advertised as
  a production The Room destination merely to complete navigation.
- Demo/config-backed surfaces must identify themselves honestly and must never present
  illustrative values as the user's real intelligence.

## TOUR Product Boundary

TOUR is a full specialist product, not a buried Street Banker feature. It keeps shared
Street Banker authentication and underlying V2 records where appropriate, but owns its
application experience. Its primary information architecture is:

- **Today** — Tour Home, My Day, changes, Ask TOUR
- **Tour** — calendar, shows, route
- **Show** — schedule, venue and show command workflows
- **Travel** — travel, hotels, people
- **Operations** — tasks, files, guests, marketing, content, import and exports
- **Money** — settlements/finance and merch
- **Team** — share links, members and settings

Server-side scope enforcement remains authoritative. Sensitive money, travel, hotel,
people and management data must never rely on template hiding alone.

## Operating Context

Street Banker Core should increasingly organize work around a universal action model:
what needs attention now, why it matters, who owns it, what project/release/song it
belongs to, and what happens next. Specialist products should exchange meaningful
outcomes with that operating layer rather than becoming disconnected dashboards.

The long-term shared intelligence graph is:

**Artist -> Song -> Market -> Opportunity -> Action -> Result**

That connected loop is more important than maximizing the number of visible features.

## Production Intelligence Gate

A capability should not be labeled Production Intelligence unless it passes all five:

1. **Real data** — no fabricated or config fallback result presented as real.
2. **Persistence** — important results and history survive sessions.
3. **Provenance** — the system can explain where a conclusion came from.
4. **Action** — the output drives a meaningful next step.
5. **Feedback** — the system can eventually measure whether the recommendation worked.

If it fails real data, it is Demo. If it has real data but lacks persistence,
provenance or action, it is a maturing/beta engine rather than finished intelligence.

## Infrastructure and Access

- Registration is closed for the current private V2 deployment unless explicitly
  changed by the owner.
- V2 must never share deployments, databases, storage, secrets, service configuration
  or code changes with V1.
- The active V2 database is expected on the persistent Render disk at
  `/var/data/v2/streetbanker.db` in the configured production environment.
- External providers remain environment-gated and must degrade honestly when absent.
- Rights guidance identifies issues and prepares materials; it is not legal
  representation.

## Brand Commitments

Street Banker is authoritative, direct, premium and music-industry specific. The
signed-in parent OS uses a dense black / graphite / warm-brass control-room language.
Each specialist product can have its own focused expression while remaining visibly
part of Street Banker. The suite must not become a generic SaaS dashboard, a wall of
oversized cards or a collection of duplicate product names.

## Product Principles

1. Street Banker is the OS; specialist products stay focused.
2. Every status must be backed by stored work or clearly labeled illustrative state.
3. Intelligence must lead to action.
4. One artist/release/song should remain the same object across relevant workflows.
5. Product names describe customer outcomes, not every internal engine.
6. Server-side authorization and data scoping are non-negotiable.
7. V2 remains operationally and technically isolated from V1.

## Accessibility & Inclusion

Keyboard access, visible focus, semantic labels, reduced-motion support, WCAG-AA text
contrast and responsive mobile operation are required across Street Banker and every
specialist product.
