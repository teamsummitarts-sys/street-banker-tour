# Five-year product roadmap

**Nothing in this document is live.** These are specifications and
architecture notes. No item here appears on the homepage as a capability,
and none may be described publicly as anything other than Coming soon
until it ships. See `CAPABILITY_STATUS.md` for what is actually real.

Ordering is by when the value lands, not by ambition.

---

## Tier 1 — immediate product value

### 1. Street Banker Today

**User problem.** The artist opens the app and sees eleven modules, each
of which could be worked on. Nothing tells them what matters this
morning. The result is that the highest-leverage task — usually an
unsigned split or an unfiled registration — loses to whatever is
visually loudest.

**Product behavior.** One feed of next-best actions. Each carries: the
source that produced it, the reason it fired, a confidence band, the
expected impact, the action itself, an owner, and a deadline. Actions
dismiss with a reason, and the reason trains the ordering.

**Data required.** Passport completeness per release, split signature
state, registration state per work, campaign dates, statement arrival
gaps, catalog age.

**Permissions.** Owner and any collaborator with a role on the release.
An action must never surface a release the viewer cannot already see.

**Dependencies.** Metadata Passport (live), Rights (live), Royalty Sweep
findings (live), Rollout dates (live).

**Risks.** A feed that fires low-value actions gets ignored within a
week, permanently. Ship with fewer, higher-confidence rules and let it be
quiet on days when nothing matters.

**Monetization.** Retention rather than a line item. Included in every
lane.

**MVP.** Six deterministic rules, no learning, no confidence model —
confidence stated as the rule's own reliability.

**V2.** Dismissal reasons feed ordering. Owners can be assigned to
collaborators.

---

### 2. Contributor Lock

**User problem.** Splits get agreed in a voice note and never written
down. Two years later the money is uncollectable because nobody can prove
who agreed to what.

**Product behavior.** One record per contributor per work: identity,
roles, splits, producer points, PRO and IPI, publishing, agreements,
credit approval, and AI/voice/likeness permissions. A work reaches
"rights-ready" only when every named contributor has signed their own
line. Structured for DDEX RIN compatibility so the record can be exported
rather than retyped.

**Data required.** Contributor identity, IPI/ISNI where held, signed
agreements, per-work role and share.

**Permissions.** Each contributor sees their own line and the work's
total, not the other contributors' agreements. This is the single most
important permission boundary in the product.

**Dependencies.** Metadata Passport, Rights & Ownership, e-signature.

**Risks.** Asking for signatures too early in the creative process makes
the product feel like paperwork. Trigger it at the point the release is
scheduled, not at upload.

**Monetization.** Development lane and above.

**MVP.** Identity, roles, splits, signature, rights-ready state.

**V2.** Producer points, publishing chain, AI/likeness permissions, DDEX
RIN export.

---

### 3. Royalty Sweep Watch

**User problem.** The sweep is a one-off. Income stops arriving from a
source and nobody notices for three quarters.

**Product behavior.** Continuous monitoring of arriving statements.
Flags missing periods, unexplained drops, identifier conflicts and
approaching claim deadlines. Each finding assembles an evidence packet
and moves through estimated → submitted → verified → recovered.

**Data required.** Statement history with periods, per-source baselines,
identifier registry, deadline calendar per society.

**Permissions.** Owner only by default; a manager role may be granted.

**Dependencies.** Royalty Sweep (live), statement ingestion (live).

**Risks.** False positives are expensive here — chasing a society over a
drop that was a reporting-calendar artifact costs the artist credibility.
Require two periods of evidence before flagging.

**Monetization.** The clearest paid feature in the product.

**MVP.** Missing-period and drop detection on uploaded statements.

**V2.** Deadline calendar, evidence packets, recovery state machine.

---

## Tier 2 — growth and revenue

### 4. Adaptive Fan Journey

**Problem.** Every fan gets the same link and the same email regardless of
whether they have been listening for six years or six minutes.

**Behavior.** Journeys keyed on observed behavior — first visit, repeat
visit, pre-saved, bought, attended. Consent state governs everything.

**Data.** Smart-link events, consent records, purchase and attendance
where the artist holds it.

**Risks.** This is the feature most likely to drift into surveillance
marketing. Hold the line: artist-held data, consent-gated, no third-party
enrichment.

**MVP.** Three journeys, manual triggers. **V2.** Behavioral triggers.

---

### 5. Catalog Reactivation Engine

**Problem.** Catalog earns quietly and nobody works it.

**Behavior.** Identifies back-catalog with live audience signal but no
recent campaign, and proposes a specific reactivation — a sync pitch, a
playlist push, an anniversary, a re-cut.

**Data.** Per-track earnings trend, audience signal, campaign history.

**Risks.** Recommending reactivation of tracks whose rights are unclear.
Gate on rights-ready.

---

### 6. Tour and Merch Demand Engine

**Problem.** Routing decided on instinct; merch printed on hope.

**Behavior.** Where listeners actually are, against where the artist can
afford to play. Merch quantities from observed demand rather than
optimism.

**Data.** Geographic listener data (needs a market-data partner), tour
history, merch sell-through.

**Dependencies.** A market-data partnership that does not exist yet — see
`PUBLIC_ROUTE_MAP.md` and the partner page.

---

## Tier 3 — the five-year moat

### 7. Release Scenario Lab

Model a release against alternatives — this date versus that one, single
first versus album, this lane versus the next — using the artist's own
history rather than an industry average. **Never a prediction of
outcome**; a comparison of shapes. The distinction has to survive
contact with marketing, or the feature becomes a hit predictor and the
product loses its credibility.

### 8. Creative Provenance and AI Rights Vault

Every asset carries where it came from: shot by whom, generated by which
model with which prompt, approved by whom, licensed for what and until
when. As AI-generated material becomes contested, provable provenance
becomes the difference between a usable catalog and an unclearable one.
This is the item with the longest-dated payoff and the strongest moat.

### 9. Private Deal Room

One export a label, distributor or investor actually accepts: income on
record, rights position, catalog shape, audience, provenance. Permissioned
per recipient, watermarked, revocable, expiring, with a log of what was
opened.

### 10. Permissioned AI Label Team

Role-scoped agents — A&R, marketing, rights, finance — that can read only
what their role permits and can propose but never execute. Every action
requires human approval and is logged. The permission model is the
product; the agents are the easy part.

---

## Cross-cutting rules

1. **Nothing ships as a prediction.** Comparison, description and
   completeness are defensible; forecasts are not.
2. **Every recommendation shows its evidence**, its confidence band and
   what it could not see.
3. **Permissions before features.** Contributor Lock and Deal Room are
   both fundamentally permission systems.
4. **Provider-neutral adapters** for anything external — the mistake to
   avoid is a hundred references to one vendor's field names, which is
   why `release_signal.py` is built the way it is.
5. **No item appears on a public surface** until it is real. Roadmap
   items may be discussed on the partner page as things we are building
   toward, never as capabilities.
