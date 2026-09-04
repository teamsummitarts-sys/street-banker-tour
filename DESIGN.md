# Street Banker V2 Company OS Design System

## Direction

Street Banker V2 is an artist's already-staffed music company, not a generic
project dashboard or a visual copy of the public V1 site. The signed-in product
opens with the Manager, presents all ten operating seats, and makes the path
from objective to approved deliverable visible.

The interface adapts the control-room character in the owner-supplied Tour,
Studio, and Remix Lab references: near-black equipment surfaces, warm brass
rules, dense operational rows, restrained glow, numbered desks, and one clear
gold action. It does not reproduce any one reference screen.

## Locked design flow

The owner has locked the three supplied references as the permanent interaction
grammar for the V2 signed-in product. They are a sequence, not three alternate
skins:

1. **Manager Control Room — Studio reference.** The first view behaves like an
   executive recording console: compact project intake, a live operating chain,
   the Manager in command, and the full company present as working equipment.
2. **Guided Desk Workflow — Remix Lab reference.** Opening any team member
   exposes that desk's two capabilities as a deliberate path from assignment to
   evidence to a Manager-ready output. The user always knows the current step
   and the next valid action.
3. **Mission Control — Tour reference.** Persisted deadlines, blockers,
   approvals, and recorded activity resolve into a narrow decision surface with
   one clear next executive action.

The references set density, hierarchy, material finish, and action clarity.
Their sample artists, track data, tour data, percentages, maps, photography,
and exact screen compositions are not product data and must never be copied or
presented as real. V2 must remain a distinct Company OS rather than a duplicate
of V1, Claude's implementation, or any individual reference.

## Product hierarchy

1. **Manager command:** the owner records an objective, success condition, and
   decision deadline.
2. **Ten-person company:** Manager is seat 01 and all ten desks, including both
   capabilities per desk, are findable in the first desktop viewport.
3. **Operating plan:** the Manager proposes accountable work without claiming
   that anyone has started it.
4. **Guided desk workflow:** assignments, status transitions, evidence, and
   deliverables remain tied to their responsible specialist.
5. **Mission Control:** only persisted approvals, blockers, reviews, deadlines,
   and activity are surfaced.

## Visual tokens

The Company OS tokens are scoped under `.sb2-company-os` so the challenger
surface cannot leak styling into existing V2 modules.

| Token | Value | Use |
|---|---:|---|
| Ground | `#060707` | Page and console base |
| Surface | `#0d0f0f` | Primary panels |
| Raised surface | `#111313` | Interactive work areas |
| Warm surface | `#15130e` | Selected or executive emphasis |
| Brass | `#e3aa45` | Rules, active state, decisive action |
| Bright brass | `#f4c26a` | High-emphasis labels and focus-adjacent accents |
| Primary text | `#f2efe8` | Headings and critical records |
| Muted text | `#a7abb0` | Supporting copy with readable contrast |
| Danger | `#e19170` | Blocked work and validation failure |
| Success | `#a6bf78` | Approved or delivered records |

Typography uses the repository's existing Archivo display token. Uppercase,
tracked labels are reserved for operational metadata; titles and record copy
remain readable sentence case. The build adds no new font dependency.

## Form and component rules

- Panels share one-pixel rules and restrained five-to-ten-pixel radii. Avoid
  floating glass cards, oversized pills, and decorative gradients.
- The only filled gold control in the first viewport is the Manager's primary
  action. Specialist and review controls stay outlined until their decision is
  relevant.
- The roster is one ordered ten-seat matrix, never a carousel, accordion, or
  horizontally scrolling row. Manager is always seat 01.
- Status words remain visible. Color, dots, rings, and borders never carry
  meaning by themselves.
- Empty and failed states explain which verified record is absent. The UI must
  not fabricate online presence, progress, deadlines, readiness, or activity.
- All changing records use server-owned versions. A stale mutation refreshes
  the latest state rather than visually pretending it succeeded.
- Deliverables require a title, completion summary, and an HTTP(S) or owned
  record reference. Delivery cannot close until evidence has been approved.

## Responsive behavior

- Source order is Manager command, ten-seat matrix, active workspace, then
  Mission Control. Visual reordering must not diverge from reading order.
- At large desktop widths, the operational surface and Mission Control form a
  main-and-rail layout. The rail may become sticky only when viewport height
  supports it.
- On tablet and mobile, all areas become one page-level vertical flow. There is
  no nested vertical scrolling.
- The roster renders all ten seats immediately in two columns, collapsing to a
  single column only in exceptionally narrow containers.
- Every grid child can shrink, long objectives wrap, full role names remain
  visible, and no action depends on horizontal page scrolling.

## Accessibility

- A skip link targets the Manager objective field.
- Interactive targets are at least 44 by 44 CSS pixels.
- Keyboard focus uses a two-pixel bright-brass ring with dark separation.
- The two capability controls are real ARIA tabs with arrow, Home, and End key
  navigation. Desk selection and mutations use buttons.
- Validation identifies and returns focus to the invalid field. Async controls
  expose busy state; status and errors use appropriate live regions.
- Reduced-motion, higher-contrast, and forced-colors preferences are supported.
- The ten-seat ordered list has an explicit accessible company label, and each
  seat announces number, full role, record-backed state, and action.

## Isolation and access

- This system belongs only to the V2 repository and
  `street-banker-v2-workflows` service.
- V1 code, routes, deployment, data, storage, and configuration are not inputs
  to this design.
- Deployed registration and demo access are closed. Only addresses explicitly
  allowlisted in the V2 service may authenticate.
- The current free comparison deployment uses ephemeral storage and must say so
  honestly until durable storage is separately authorized.

## Asset provenance

No raster image ships in this Company OS change. Branding marks and controls
are inline vector/CSS primitives authored for this build. The owner-supplied
Tour, Studio, and Remix Lab screenshots are direction references only and are
not bundled, copied, or redistributed by the application.

## Finish gate

Unreviewed and undocumented is unfinished. A release requires passing tests,
desktop and mobile inspection, an independent finish verdict, this document,
and provenance for every future shipping raster.
