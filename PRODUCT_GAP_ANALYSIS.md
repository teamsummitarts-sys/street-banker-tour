# Product Gap Analysis

Written from an audit of the running code, not from a feature wishlist.

## The finding that matters

Street Banker's product thesis is a closed loop: measure something real,
feed it back so the next decision is better. Nearly every *feature* the
five-year directive asks for already exists as a route. What did not
exist was the loop.

The proof is concrete rather than rhetorical.

### The Rack measured, and nothing listened

`static/js/loudness.js` implements ITU-R BS.1770-4 properly — K-weighting
derived per sample rate, 400 ms gated integrated loudness, EBU 3342
loudness range, true peak by 4× oversampling, verified against the
published EBU Tech 3341 compliance cases. `tempokey.js` detects tempo and
key with confidence scores.

All of it died when the browser tab closed.

`/rack/save` persisted a preset blob. `get_rack_preset` was read in
exactly two places in the entire codebase:

| Site | What it does with the value |
|---|---|
| `app.py:3954` | JSON-dumps it into the page so the knobs restore |
| `app.py:1279` | `bool(...)` — presence only, values never inspected |

No engine — `artist_twin.py`, `artist_os.py`, `insights_engine.py`,
`command_center.py`, `qualification.py`, `rollout_engine.py` — imported
the rack table or referenced the measurements.

### Meanwhile Release Readiness scored paperwork

`qualification.calculate()` built its "Release Readiness" category from:
best campaign link score, live campaigns with 3+ destinations, email
capture flag, fan count, approved rollout posts, EPK photo/assets/covers,
tracks carrying an ISRC, social handle count, bio and press presence.

Every input administrative. **None of them the record.**

The consequence, stated plainly: an artist could score *Release Ready*
on a master that clips on every platform it is sent to, and nothing in
the app would say a word. The one thing Street Banker measures to a
published broadcast standard was the one thing the readiness score
ignored.

## Fixed in this pass

`audio_readiness.py` turns stored measurements into rulings. A new
`track_analysis` table persists what the Rack measured; `/rack/analysis`
receives it; `qualification.py` gained a **Master Quality** category —
the only one that listens to the audio — and `artist_twin.py` gained
`rack` as a consentable source.

Verified on a real record (−12.5 LUFS, 4.2 LU, −0.03 dBTP): the score
now falls to 5/25 and names the reason.

## Discipline this establishes

1. **Absent evidence is not a pass.** An unmeasured master scores 0, not
   a default. The score should mean the record was checked.
2. **Only quote what was measured confidently.** A 0.3-confidence tempo
   is hedged, never stated as fact.
3. **Every ruling carries its evidence** and the threshold it was judged
   against, so a disagreeing artist can see exactly what was compared.

## Still open

A background audit is tracing the other severed signals — smart-link
geography and per-variant CTR, statement line items, stem separation
results, per-post click heat — for the same pattern: computed, real,
and read by nothing.
