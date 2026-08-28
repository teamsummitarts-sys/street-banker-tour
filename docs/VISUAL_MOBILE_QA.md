# Visual, mobile and performance QA

## The caveat that governs this whole document

**Nothing here was seen rendered.** Every browser screenshot attempt in
this environment timed out — on every page, for the whole duration of
this project. What follows was derived by reading the CSS, the rendered
markup and the asset files. It is a design specification and a set of
structural checks, not an observation. A human should walk the six widths
before this is called finished.

## Visual consistency

One palette across all twelve sections and the four new public pages:

| Token | Value | Use |
| --- | --- | --- |
| Ink | `#080807` | every dark background |
| Ivory | `#EEE8DC` | headings, body copy on dark |
| Brass | `#C9A86A` | eyebrows, links, accents, primary CTA fill |
| Brass lit | `#E1C48F` | hover only |
| Muted | `#A7A198` | supporting copy |
| Line | `rgb(201 168 106 / 0.22)` | every rule and border |

Consistent across sections: eyebrow at 10–13px / 0.3em tracking / brass ·
section headings uppercase, tight tracking, `clamp()` sized · body copy
14–17px at 1.6–1.65 line-height · primary CTA brass-filled with `#14120E`
label, secondary outlined ivory · 2px radius on buttons, 3–4px on cards ·
focus ring 2px brass at 3px offset everywhere.

The footer is dark. It has to be: the closing frame fades to `#080807` at
its bottom edge, and the previous pale footer would have drawn a hard
line under the last photograph.

## Mobile (≤ 767px)

| Section | Behaviour |
| --- | --- |
| Header | Drawer, with both studios named separately |
| 3 Artist EQ | Faders stack; presets wrap |
| 4 Departments | Horizontal swipe, one department per view |
| 5 Artist Twin | Rows collapse to a stack, expandable |
| 6 Lanes | Channels stack vertically |
| 7 Creative Studio | Capability strip swipes; close crop |
| 8 Rollout Engine | Image below copy; close crop |
| 9 Royalty Sweep | Stage list stacks; close crop |
| 10 Distribution | Stages stack; close crop |
| 11 Passport | Category list replaces the blueprint hotspots; close crop |
| 11.5 Trust band | 4 → 2 → 1 column; the policy link centres |
| 12 Closing | **Copy above the picture, not over it** |
| Footer | Columns stack; every link gets `-my-2 py-3.5` for a 44px target |
| Tour | Step number moves above its body below 520px |
| Fan table | Collapses to stacked rows; the header row is visually hidden |

Section 12's mobile rule is the one worth stating plainly: a tight crop
with text laid over it loses either the road case or the words. The copy
goes above the photograph instead, using `flex-direction: column` with
explicit `order`.

CTAs go full width below 640px in the closing section.

## Breakpoints

`640px` (2-column grids) · `767/768px` (mobile picture sources) ·
`1024px` (the closing section's overlay layout) · `1100px` (trust band to
4 columns) · `1180px` (the header's wide variant — set here rather than
1024 because the full nav overflowed 1024 by 13px).

## Performance

| Measure | Value |
| --- | --- |
| Homepage HTML | 123 KB uncompressed |
| `<picture>` elements | 11 |
| Images with AVIF + WebP + JPEG | all |
| Images with intrinsic `width`/`height` | all |
| Lazy-loaded | all but the hero (the LCP element) |
| Blocking stylesheets | Tailwind + 12 section sheets |
| JavaScript | 10 deferred component files, no framework, no third-party script |
| Service worker | `sb-v95`, cache-first on `/static` |

Every section renders completely with JavaScript disabled — the scripts
add analytics, the swipe affordances and the EQ-to-CTA carry, and remove
nothing when absent.

**Worth improving later:** the twelve separate section stylesheets are
twelve requests in the critical path. They are individually small and
HTTP/2 makes it tolerable, but concatenating them at build time would be
the single biggest first-paint win available on this page.
