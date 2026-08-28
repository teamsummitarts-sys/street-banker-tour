# Drop real photography here

Originals at full resolution. Do not pre-resize or pre-crop — every
derivative is generated from the original, and cropping twice costs
quality that cannot be recovered.

## Slots

Two anonymous documentary frames — a crowd shot and a backstage corridor
— were selected first, on the reasoning that a homepage selling
infrastructure for any artist should not read as one artist's press kit.
Neither ever reached disk. What the owner delivered instead, and what
ships now, is different.

| Slot | Section | Aspect | Master | Source | Status |
| --- | --- | --- | --- | --- | --- |
| `hero-wide` | 2 Hero, desktop | 1342 x 775 | 1342 | `hero-band.webp` | shipped 2026-08-14 |
| `hero-tall` | 2 Hero, phone | 900 x 1200 | 900 | `hero-band.webp` | shipped 2026-08-14 |
| `creative-wide` | 7 Creative Studio, desktop | 830 x 980 | 830 | `creative-portrait.jpg` | shipped 2026-08-14 |
| `creative-close` | 7 Creative Studio, phone | 600 x 520 | 600 | `creative-portrait.jpg` | shipped 2026-08-14 |
| `rollout-wide` | 8 Rollout Engine, desktop | 940 x 710 | 940 | waiting | — |
| `rollout-close` | 8 Rollout Engine, phone | 600 x 630 | 600 | waiting | — |

**The anonymity rule was overtaken, and narrowed rather than dropped.**
This file used to record that Section 7 keeps its generated image because
an artist portrait would put the same recognisable person across three
sections. Section 7 now carries a recognisable face, at the owner's
direction. What that rule existed to prevent — one subject recurring
until the page reads as their press kit — is still enforced, by keeping
each subject to a single section: the hero is a four-piece band, Section
7 is one portrait, and Sections 5 and 8 must reuse neither.

## What was actually run

Recorded because a crop that cannot be reproduced is a crop that cannot
be retuned. `tests/test_creative_studio.py` re-runs the Section 7 pair
and compares pixels, so these cannot quietly drift.

    python tools/build_photo.py incoming/artist-photos/hero-band.webp hero-wide --focus 0.52,0.5
    python tools/build_photo.py incoming/artist-photos/hero-band.webp hero-tall --focus 0.53,0.30
    python tools/build_photo.py incoming/artist-photos/creative-portrait.jpg creative-wide --focus 0.53,0.42
    python tools/build_photo.py incoming/artist-photos/creative-portrait.jpg creative-close --focus 0.53,0.0

`creative-portrait.jpg` arrived as a 1080 x 1080 export rather than a
camera original — the thing the rule at the top of this file warns
against. It does not upscale at the sizes shipped today (the 830px master
is cut from a 915 x 1080 crop) but there is no headroom above that, so a
larger master, a retina variant or a wider recrop all need a new file
from the owner.

## Building

    python tools/build_photo.py incoming/artist-photos/<file> <slot> --focus x,y

`--focus` is the point that must survive the crop, as fractions of the
original's width and height. `0.5,0.5` is the centre and is usually
wrong: put it on the face, the hands, or whatever the frame is about.

Check the crop before writing anything:

    python tools/build_photo.py incoming/artist-photos/<file> hero-wide --focus 0.4,0.3 --dry-run

## After building

1. Update the `alt` text in the config to describe the new scene.
2. Bump the `?v=` on any changed asset and bump `VERSION` in
   `static/js/sw.js` — the service worker is cache-first on `/static`
   and will keep serving the old picture otherwise.

This folder is for source material and is not served. Nothing in it
reaches the site until it has been through `build_photo.py`.

## Credit

None. These photographs are the owner's own work, so there is no
photographer to attribute and no licence to acknowledge. The credit
partial that briefly existed for this was removed rather than left
unused.

The alt text still describes the scene, because that is an accessibility
requirement rather than a credit — and it does not name anyone in the
picture as a Street Banker artist, because a face on a marketing page is
read as an endorsement and that would be a claim about a business
relationship.
