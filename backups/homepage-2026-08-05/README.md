# Homepage backup — 2026-08-05

Taken immediately before replacing the photography in **Sections 2 (Hero),
7 (Creative Studio) and 8 (Rollout Engine)** with real artist
photography.

Git state at the time of this backup: commit `b49a38c`, branch
`overview-redesign`, tag `pre-real-photography`. That tag is the
authoritative restore point — everything in this folder is also in that
commit. The folder exists so the *look* can be compared side by side
without checking anything out.

## Why the swap

The photography in Sections 4, 5, 7, 8, 9 and 10 was generated, and all
six arrived with fabricated text baked into the image — invented track
lists, malformed handwriting, made-up registration numbers, nonsense tour
routes. Each was repaired by surface-aware repaint (see
`docs/IMAGE_ASSET_MANIFEST.md`). That removed the false claims but not
the generated look. Sections 2, 7 and 8 are being replaced with real
photographs of a real artist instead.

## What is in here

| Path | Contents |
| --- | --- |
| `img/` | Every derivative of the three images being replaced: `hero-band-wide` (900/1100/1342), `hero-band-tall` (640/900), `creative-wide` (520/830), `creative-close` (400/600), `rollout-wide` (560/940), `rollout-close` (400/600) — AVIF, WebP and JPEG each |
| `config/` | `landing_config.py` (hero image block), `creative_config.py`, `rollout_config.py` |
| `templates/` | `landing.html` (the hero is inline in this file, not a partial), `creative_studio.html`, `rollout.html` |
| `css/` | `hero.css`, `creative-studio.css`, `rollout.css` |
| `rendered-homepage.html` | The live homepage as served by production on 2026-08-05, so the previous markup can be diffed against the new one |

## To restore

**This tag now predates two landed replacements.** The hero and Section 7
carry real owner-supplied photographs as of 2026-08-14; restoring from
here puts the generated frames back. For Section 7 alone, prefer
`backups/section07-2026-08-14/` and the `pre-section7-photo-2026-08-14`
tag, which also captures the stylesheet.

The stylesheets are listed above but were missing from this command,
which mattered once the CSS was retuned for the new photographs: restore
the pictures without them and a low-key frame sits under crop and veil
values tuned for a high-key one.

    git checkout pre-real-photography -- static/img/hero-band-* \
        static/img/creative-* static/img/rollout-* \
        static/css/hero.css static/css/creative-studio.css \
        static/css/rollout.css \
        landing_config.py creative_config.py rollout_config.py \
        templates/landing.html templates/partials/creative_studio.html \
        templates/partials/rollout.html

Then rebuild Tailwind if any class changed, bump `static/js/sw.js`
VERSION, and bump the `?v=` query on any asset whose bytes changed —
the service worker is cache-first on `/static` and will otherwise keep
serving the new files.
