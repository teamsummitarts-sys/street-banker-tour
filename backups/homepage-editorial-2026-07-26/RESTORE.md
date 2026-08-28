# Homepage backup — editorial version, 2026-07-26

Self-contained snapshot of the Street Banker homepage as it stands after
the editorial rewrite. Everything needed to bring this exact version
back is in this folder.

## What's here

| File | What it is |
|---|---|
| `COPY.md` | Every word on the page, in order, with links |
| `landing_config.py` | All homepage content and image wiring |
| `templates/landing.html` | The full page — self-contained, no macros |
| `static/img/sb-hero-photo.jpg` | Hero: performer + crowd |
| `static/img/sb-lane-01..03.jpg` | The three rack-unit lane cards |
| `static/img/sb-patchbay.jpg` | Royalty Sweep visual |
| `static/img/sb-band.jpg` | Full-bleed band (front-of-house + arena) |
| `static/img/streetbanker-logo-dark.svg` | Header + footer logo |
| `rendered-homepage.html` | The live page's HTML as served on this date |

## Restore — either method

**Method 1 — git tag:**

```bash
git checkout homepage-editorial-2026-07-26 -- landing_config.py templates/landing.html static/img/sb-hero-photo.jpg static/img/sb-lane-01.jpg static/img/sb-lane-02.jpg static/img/sb-lane-03.jpg static/img/sb-patchbay.jpg static/img/sb-band.jpg
```

**Method 2 — copy from this folder.** From the repo root:

```bash
cp backups/homepage-editorial-2026-07-26/landing_config.py . && cp backups/homepage-editorial-2026-07-26/templates/landing.html templates/ && cp backups/homepage-editorial-2026-07-26/static/img/* static/img/
```

After either: bump `VERSION` in `static/js/sw.js` (currently `sb-v17`)
and the `?v=` numbers in `landing_config.py`, or phones keep serving the
cached previous version.

## The page

1. **Nav** — logo + tagline, four links, Login + Start Free Scan
2. **Hero** — THE ARTIST BACK OFFICE. beside the performer photograph
3. **Three Lanes** — three rack-unit cards: release, build, own
4. **Royalty Sweep** — the only dark section, ILLUSTRATIVE DEMO DATA label
5. **Signature Tools** — five real modules, icon + name, one row
6. **Band** — full-bleed strip, no text, no link
7. **Final CTA** — your music is the product, your catalog is the asset
8. **Minimal footer** — four columns, socials, copyright

## Rules this version follows

- Homepage explains the promise; interior pages carry the detail
- No section makes more than one point; paragraphs are two lines max
- Every link resolves to a real route
- No invented client names, partner logos, or statistics; any figure in
  a product visual is labeled illustrative
- Gold is an accent only — labels, active states, the Sweep CTA
- One dark section; the rest stays white/ivory editorial
- Mobile: copy stacks before imagery, buttons are full-width and tappable

## Earlier version

The previous artwork-led homepage is still available:
tag `homepage-approved-2026-07-26`, folder
`backups/homepage-2026-07-26/`. Its unused artwork
(`sb-hero.jpg`, `sb-engines.jpg`, `sb-distro-lanes.jpg`,
`sb-ownership.jpg`) remains in `static/img/`.
