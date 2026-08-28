# Capability status

One source of truth: `capability_status.py`. Every public surface reads
from it — homepage, product tour, product pages, partner page and the
privacy language. Before this, the same capability could read Live on
one page and Integration ready on another and nothing failed.

Six statuses and no others. Colour is never the only signal: every chip
carries its own word, so the meaning survives greyscale and
colour-blindness.

| Status | Means |
| --- | --- |
| **Live** | Working in the product today. |
| **Example** | A worked example, not an artist's data. |
| **Partner delivered** | Carried out through a named partner. |
| **Integration ready** | Built here; the outside connection is not live. |
| **Coming soon** | Not built yet. |
| **Requires verification** | A finding a person must check before it is acted on. |

## Resolved against the deployment

Some capabilities are only live when credentials are actually present.
A hardcoded "Live" on a marketing page silently becomes false the
moment a key is missing, so these carry a probe instead of a fixed
status and the page states what is true of the running deployment.

| Capability | Probe | If present | If absent |
| --- | --- | --- | --- |
| Spotify pre-save | `SPOTIFY_CLIENT_ID` + `SPOTIFY_CLIENT_SECRET` | Live | Integration ready |
| Release-day email | `RESEND_API_KEY` | Live | Integration ready |
| Subscriptions and billing | `STRIPE_SECRET_KEY` | Live | Coming soon |

**On this deployment right now** (as generated):

- **Spotify pre-save** — Integration ready. The flow is built and not connected on this deployment. Pre-save buttons collect a notify-me instead, and no Spotify token is requested, stored or processed.
- **Release-day email** — Integration ready. Built, and no email provider is connected on this deployment.
- **Subscriptions and billing** — Coming soon. No payment provider is connected on this deployment.

### Why this matters for Spotify pre-save

The OAuth flow, token storage and release-day save are all implemented,
and all of them are gated on credentials. With those unset the feature
falls back to notify-me and no token is ever requested. The privacy
page's statement about encrypting pre-save tokens is therefore
conditional on the same probe: with credentials absent it says instead
that no Spotify token is requested, stored or processed.

## TOUR

Four entries, so the module cannot over-claim:

- **TOUR (tour operating system)** — Live. Tours, days, Show Command,
  schedule, advance, travel, hotels and rooms, people, guests, VIP,
  files, money, merch, marketing, content, set lists, imports, exports,
  share links, team permissions, What Changed, Ask Tour — on your own
  data, enforced server-side.
- **Advance inbox extraction** — Live, *rule-based*. Pasted text is read
  with patterns; every proposal carries its source line and a
  confidence and goes through a review step before anything is written.
  There is no language model on this deployment, and PDFs must be
  pasted as text (no extraction library is installed).
- **Offline** — Live. Tour Home, My Day and Show Command are
  network-first with a cached fallback after a visit.
- **Route map with drive times** — Integration ready. Route order, day
  gaps, back-to-back flags and straight-line distances from entered
  coordinates are live; map tiles and drive-time estimates need a
  provider, and a Directions link opens the real route instead.

## Every capability

### Live (10, plus TOUR's three above)

- Artist EQ
- Starting plan
- Metadata Passport
- Rights & Ownership
- Creative Studio
- Artwork generator
- Smart Links
- Email capture with consent
- Rollout plans
- Three Street Banker Lanes

### Example (2)

- Artist Twin assessment
- Fan Intelligence

### Partner delivered (1)

- Delivery to platforms — Street Banker assembles and validates the package; delivery goes out through the distribution partnership.

### Integration ready (6)

- Spotify pre-save — The flow is built and not connected on this deployment. Pre-save buttons collect a notify-me instead, and no Spotify token is requested, stored or processed.
- Release-day email — Built, and no email provider is connected on this deployment.
- Social publishing
- Streaming destination links
- Geographic response
- Conversion events

### Coming soon (6)

- Subscriptions and billing — No payment provider is connected on this deployment.
- SMS capture
- QR codes
- Motion and video assets
- Print-ready separations
- Release Signal

### Requires verification (1)

- Royalty Sweep finding

## Rules for adding a capability

1. If it is not built, it is **Coming soon**. There is no label meaning "nearly".
2. If the interface exists and the outside connection does not, it is
   **Integration ready** — never Live.
3. If somebody else performs it, it is **Partner delivered**, and the partner is named.
4. If the data on screen is invented, the label is **Example** and the
   surrounding copy says so in words as well as in a chip.
5. If it depends on a credential, give it a **probe**, not a fixed status.
6. No figure appears on any public surface that was not computed from a
   real input. No recovery totals, stream counts, artist counts, country
   counts, earnings or accuracy percentages.
