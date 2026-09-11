# Ask Reach grounding contract

Ask Reach is a deterministic command/search surface over REACH's persisted records.

- It may answer only from records already stored or verified by REACH.
- It must return an empty/unknown result when supporting data is absent.
- It does not fabricate outlets, deadlines, relationships, campaign outcomes, release readiness, comparable-artist signals, or causal claims.
- The Today dashboard Ask Reach controls open `/reach/ask`; Radar remains a separate `/reach/opportunities` destination.
- The JSON endpoint mirrors the same grounded result model used by the artist-facing page.
