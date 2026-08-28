"""Sync Deal Simulator: structured analysis of a sync offer.

Heuristic market ranges and risk flags — workflow support, not legal or
financial advice. The ranges are indicative industry ballparks for
independent catalog and always shown as ranges, never as a promise.
"""

MEDIA_TYPES = [
    ("web_social", "Web / Social Content", (500, 1500)),
    ("indie_film", "Indie Film / Festival", (1000, 3000)),
    ("tv_episode", "TV Episodic", (2500, 7500)),
    ("streaming_series", "Streaming Series", (4000, 12000)),
    ("national_ad", "National Ad / Brand", (10000, 50000)),
    ("trailer", "Film / Game Trailer", (25000, 75000)),
    ("video_game", "Video Game", (2000, 10000)),
]
MEDIA_LABELS = {k: label for k, label, _ in MEDIA_TYPES}

TERMS = [("1y", "1 year"), ("3y", "3 years"), ("5y", "5 years"),
         ("perpetuity", "In perpetuity")]
TERRITORIES = [("single", "Single territory"), ("multi", "Multi-territory"),
               ("worldwide", "Worldwide")]


def simulate(inp):
    """inp: fee (float), media, term, territory, exclusive (bool),
    all_media (bool), mfn (bool), buyout (bool). Returns analysis dict."""
    fee = float(inp.get("fee") or 0)
    media = inp.get("media") if inp.get("media") in MEDIA_LABELS else "web_social"
    base_low, base_high = next(r for k, _, r in MEDIA_TYPES if k == media)

    mult = 1.0
    if inp.get("territory") == "worldwide":
        mult *= 1.5
    elif inp.get("territory") == "multi":
        mult *= 1.25
    if inp.get("term") == "perpetuity":
        mult *= 2.0
    elif inp.get("term") == "5y":
        mult *= 1.5
    elif inp.get("term") == "3y":
        mult *= 1.25
    if inp.get("exclusive"):
        mult *= 2.0
    if inp.get("all_media"):
        mult *= 1.5
    quote_low = round(base_low * mult)
    quote_high = round(base_high * mult)

    flags = []
    if inp.get("buyout") or inp.get("term") == "perpetuity":
        flags.append(("high", "Perpetuity / buyout language: you are selling this "
                              "use forever. Price it like a sale, not a rental — "
                              "or counter with a fixed term plus renewal option."))
    if inp.get("exclusive") and fee and fee < quote_low:
        flags.append(("high", "Exclusivity below the range floor: exclusivity blocks "
                              "every other licensing opportunity for this track. "
                              "It should cost them real money."))
    if inp.get("all_media") and inp.get("territory") == "worldwide" and fee and fee < quote_low:
        flags.append(("medium", "All media + worldwide at a below-range fee — that "
                                "combination is the broadest grant possible."))
    if inp.get("mfn"):
        flags.append(("info", "MFN (most favored nations): your fee ties to what "
                              "other rights holders get. Confirm who else is on "
                              "the project before agreeing."))
    if fee == 0:
        flags.append(("high", "Gratis / exposure-only offer: fine only if the "
                              "placement itself is the payment (major trailer, "
                              "prestige film). Get the credit in writing."))

    if not fee:
        position = "no_offer"
    elif fee < quote_low:
        position = "below"
    elif fee > quote_high:
        position = "above"
    else:
        position = "within"

    counter = None
    if position in ("below", "no_offer"):
        counter = ("Thanks for the interest in the track. For %s use, %s, %s%s%s, "
                   "our quote is $%s–$%s all-in (master + publishing, one-stop). "
                   "Happy to discuss scope adjustments if budget is fixed." % (
                       MEDIA_LABELS[media].lower(),
                       dict(TERRITORIES).get(inp.get("territory"), "single territory").lower(),
                       dict(TERMS).get(inp.get("term"), "1 year").lower(),
                       ", exclusive" if inp.get("exclusive") else "",
                       ", all media" if inp.get("all_media") else "",
                       "{:,}".format(quote_low), "{:,}".format(quote_high)))

    return {"quote_low": quote_low, "quote_high": quote_high, "position": position,
            "flags": flags, "counteroffer": counter, "media_label": MEDIA_LABELS[media]}
