# Image asset manifest

Every photograph on the Street Banker homepage, the crops generated from
it, and what was done to it. All of them exist in three formats — AVIF,
WebP and JPEG — at each listed width, and every `<picture>` declares the
master's intrinsic `width`/`height` so the browser reserves the box
before a byte arrives.

| Section | Stem | Widths | Master | Used for |
| --- | --- | --- | --- | --- |
| 2 Hero | `hero-band-wide` | 900, 1100, 1342 | 1342 | desktop |
| 2 Hero | `hero-band-tall` | 640, 900 | 900 | phone |
| 3 Artist EQ | `eq-room` | 900, 1200, 1600 | 1600 | all |
| 4 Departments | `departments` | 900, 1200, 1553 | 1553 | all |
| 5 AI Artist Twin | `artist-twin` | 480, 700, 893 | 893 | all |
| 6 Lanes | `lanes-unit` | 760, 1100, 1626 | 1626 | all |
| 7 Creative Studio | `creative-wide` / `creative-close` | 520, 830 / 400, 600 | 830 / 600 | desktop / phone |
| 8 Rollout Engine | `rollout-wide` / `rollout-close` | 560, 940 / 400, 600 | 940 / 600 | desktop / phone |
| 9 Royalty Sweep | `sweep-wide` / `sweep-close` | 900, 1400, 1672 / 430, 860 | 1672 / 860 | desktop / phone |
| 10 Distribution | `distro-wide` / `distro-close` | 760, 1180, 1402 / 480, 740 | 1402 / 740 | desktop / phone |
| 11 Metadata Passport | `passport-wide` / `passport-close` | 900, 1300, 1672 / 520, 1037 | 1672 / 1037 | desktop / phone |
| 12 Closing | `closing-wide` / `closing-close` | 960, 1440, 1672 / 520, 1070 | 1672 / 1070 | desktop / phone |

Loading: the hero is eager (it is the LCP element). Every other
photograph is `loading="lazy"`.

## What was done to each image

Sections 2 and 7 now carry real photographs supplied by the owner, built
from one original each through `tools/build_photo.py`, which crops,
resizes and encodes and does nothing else. Neither was retouched. Section
2 is a four-piece band in a venue backline; section 7 is a portrait
against a pale wall. The repair tool that once produced section 7's
bytes was deleted with the mockup it existed to repair.

Sections 4, 5, 8, 9 and 10 arrived as layout mockups with generated
text baked into the picture — invented track lists, malformed
handwriting, fabricated registration numbers, nonsensical tour routes and
repeated fake Street Banker branding. The brief for each section
forbids putting a flattened mockup on the page, and none of that text was
true. So in each case the photographic band was cropped out of the
mockup and the lettering removed by surface-aware repaint rather than
blur: boundary-bilinear fill plus a high-frequency grain residual lifted
from a clean patch of the same surface, with morphological open/close for
thin strokes and a mirrored patch for textured walls. Feather 3, with
each mask box grown roughly 6px past its text — a wider feather leaves
the lettering legible at both ends of the box.

Sections 11 and 12 needed none of this. Both are used unaltered, cropped
only.

Section 12 close crop: `(0.33W, 0.16H) – (0.97W, 0.99H)` of the master =
1070 × 781, which keeps the road case and the catalog trail toward the
stage. The wide frame keeps the full room, and the copy sits in the dark
left third under a two-stop gradient veil rather than a flat scrim.

## Alt text

Every photograph describes the scene, not the section. No alt text
repeats a heading, and none of them names a product feature. The closing
frame reads: *"Worn touring road case inside an empty venue with records,
tapes and hard drives creating a trail toward the stage."*

## Not verified

The rendered result of any of these images was never seen in a browser
during this work — every screenshot attempt in this environment timed
out. Crops, masks and dimensions were verified numerically against the
source files, and the section 2 and section 7 crops were inspected as
image files after building. That is not the same as seeing them laid out
at a real breakpoint: the CSS crops both further with `object-fit: cover`,
so a human should still look at the page.
