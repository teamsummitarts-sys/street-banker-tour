"""Team-Up Board taxonomy: regions, metros, genres, and best-effort parsers.

Structure over free text, kept small and readable. Every region/metro has
a stable CODE (what gets stored), a LABEL (what gets shown), ALIASES
(what people actually type) and a rough LAT/LNG (for routing epics later).
Parsers are deliberately conservative: they return None rather than
guess, and the caller keeps the original text as a fallback.
"""
import re
from datetime import date

# (code, label, parent, aliases, lat, lng)
REGIONS = [
    ("us-northeast", "Northeast US", None, ["northeast", "north east", "new england", "ne us", "the northeast", "tri-state"], 42.4, -72.5),
    ("us-midatlantic", "Mid-Atlantic", None, ["mid-atlantic", "mid atlantic", "midatlantic", "dmv"], 39.3, -76.8),
    ("us-southeast", "Southeast US", None, ["southeast", "south east", "se us", "the south", "deep south", "southeast us", "southeastern"], 33.6, -84.2),
    ("us-midwest", "Midwest", None, ["midwest", "mid-west", "mid west", "great lakes", "rust belt"], 41.6, -88.0),
    ("us-southcentral", "South Central / Texas", None, ["south central", "texas", "tx", "gulf coast", "texas triangle"], 31.2, -97.6),
    ("us-mountain", "Mountain West", None, ["mountain west", "mountain", "rockies", "rocky mountains", "front range"], 40.0, -105.8),
    ("us-southwest", "Southwest US", None, ["southwest", "south west", "desert southwest", "sw us"], 34.2, -111.4),
    ("us-westcoast", "West Coast", None, ["west coast", "westcoast", "california", "ca", "socal", "norcal", "bay area"], 36.8, -120.9),
    ("us-pnw", "Pacific Northwest", None, ["pacific northwest", "pnw", "cascadia", "northwest"], 46.2, -122.4),
    ("us-anywhere", "US — anywhere", None, ["us", "usa", "united states", "anywhere us", "nationwide", "national", "anywhere", "open to anywhere"], 39.8, -98.6),
    ("ca", "Canada", None, ["canada", "canadian"], 49.3, -96.0),
    ("uk", "United Kingdom", None, ["uk", "united kingdom", "britain", "england", "scotland", "wales", "ireland"], 53.5, -2.0),
    ("eu", "Europe", None, ["europe", "eu", "european", "continental europe"], 50.1, 9.0),
    ("au", "Australia / NZ", None, ["australia", "aus", "oz", "new zealand", "nz", "australasia"], -33.9, 148.0),
    ("latam", "Latin America", None, ["latin america", "latam", "mexico", "south america", "central america"], 19.4, -99.1),
    ("other", "Somewhere else", None, ["other", "elsewhere", "international", "worldwide"], 0.0, 0.0),
]

METROS = [
    ("metro-nyc", "New York, NY", "us-northeast", ["new york", "nyc", "new york city", "brooklyn", "manhattan", "queens", "ny"], 40.71, -74.01),
    ("metro-boston", "Boston, MA", "us-northeast", ["boston", "bos", "cambridge ma", "somerville"], 42.36, -71.06),
    ("metro-philly", "Philadelphia, PA", "us-midatlantic", ["philadelphia", "philly"], 39.95, -75.17),
    ("metro-dc", "Washington, DC", "us-midatlantic", ["washington dc", "dc", "washington, dc", "d.c.", "baltimore"], 38.9, -77.04),
    ("metro-pittsburgh", "Pittsburgh, PA", "us-midatlantic", ["pittsburgh"], 40.44, -80.0),
    ("metro-richmond", "Richmond, VA", "us-southeast", ["richmond", "rva"], 37.54, -77.44),
    ("metro-raleigh", "Raleigh-Durham, NC", "us-southeast", ["raleigh", "durham", "chapel hill", "carrboro", "the triangle", "raleigh-durham"], 35.78, -78.64),
    ("metro-charlotte", "Charlotte, NC", "us-southeast", ["charlotte", "clt"], 35.23, -80.84),
    ("metro-asheville", "Asheville, NC", "us-southeast", ["asheville"], 35.6, -82.55),
    ("metro-atlanta", "Atlanta, GA", "us-southeast", ["atlanta", "atl", "athens ga"], 33.75, -84.39),
    ("metro-nashville", "Nashville, TN", "us-southeast", ["nashville", "nash", "music city"], 36.16, -86.78),
    ("metro-memphis", "Memphis, TN", "us-southeast", ["memphis"], 35.15, -90.05),
    ("metro-birmingham", "Birmingham, AL", "us-southeast", ["birmingham", "bham"], 33.52, -86.81),
    ("metro-charleston", "Charleston, SC", "us-southeast", ["charleston", "chs"], 32.78, -79.93),
    ("metro-savannah", "Savannah, GA", "us-southeast", ["savannah"], 32.08, -81.09),
    ("metro-jacksonville", "Jacksonville, FL", "us-southeast", ["jacksonville", "jax"], 30.33, -81.66),
    ("metro-orlando", "Orlando, FL", "us-southeast", ["orlando"], 28.54, -81.38),
    ("metro-tampa", "Tampa, FL", "us-southeast", ["tampa", "st pete", "st. petersburg"], 27.95, -82.46),
    ("metro-miami", "Miami, FL", "us-southeast", ["miami", "fort lauderdale", "south florida"], 25.76, -80.19),
    ("metro-neworleans", "New Orleans, LA", "us-southcentral", ["new orleans", "nola"], 29.95, -90.07),
    ("metro-houston", "Houston, TX", "us-southcentral", ["houston", "htx"], 29.76, -95.37),
    ("metro-austin", "Austin, TX", "us-southcentral", ["austin", "atx"], 30.27, -97.74),
    ("metro-dallas", "Dallas–Fort Worth, TX", "us-southcentral", ["dallas", "fort worth", "dfw", "denton"], 32.78, -96.8),
    ("metro-sanantonio", "San Antonio, TX", "us-southcentral", ["san antonio"], 29.42, -98.49),
    ("metro-okc", "Oklahoma City, OK", "us-southcentral", ["oklahoma city", "okc", "tulsa"], 35.47, -97.52),
    ("metro-kc", "Kansas City, MO", "us-midwest", ["kansas city", "kc", "kcmo"], 39.1, -94.58),
    ("metro-stlouis", "St. Louis, MO", "us-midwest", ["st louis", "st. louis", "stl"], 38.63, -90.2),
    ("metro-chicago", "Chicago, IL", "us-midwest", ["chicago", "chi"], 41.88, -87.63),
    ("metro-milwaukee", "Milwaukee, WI", "us-midwest", ["milwaukee", "madison"], 43.04, -87.91),
    ("metro-minneapolis", "Minneapolis–St. Paul, MN", "us-midwest", ["minneapolis", "twin cities", "st paul", "msp"], 44.98, -93.27),
    ("metro-detroit", "Detroit, MI", "us-midwest", ["detroit", "ann arbor"], 42.33, -83.05),
    ("metro-cleveland", "Cleveland, OH", "us-midwest", ["cleveland", "akron"], 41.5, -81.69),
    ("metro-columbus", "Columbus, OH", "us-midwest", ["columbus", "cbus"], 39.96, -83.0),
    ("metro-cincinnati", "Cincinnati, OH", "us-midwest", ["cincinnati", "cincy", "louisville"], 39.1, -84.51),
    ("metro-indianapolis", "Indianapolis, IN", "us-midwest", ["indianapolis", "indy"], 39.77, -86.16),
    ("metro-denver", "Denver, CO", "us-mountain", ["denver", "boulder", "fort collins"], 39.74, -104.99),
    ("metro-slc", "Salt Lake City, UT", "us-mountain", ["salt lake city", "slc", "salt lake"], 40.76, -111.89),
    ("metro-phoenix", "Phoenix, AZ", "us-southwest", ["phoenix", "tempe", "tucson"], 33.45, -112.07),
    ("metro-albuquerque", "Albuquerque, NM", "us-southwest", ["albuquerque", "abq", "santa fe"], 35.08, -106.65),
    ("metro-lasvegas", "Las Vegas, NV", "us-southwest", ["las vegas", "vegas"], 36.17, -115.14),
    ("metro-la", "Los Angeles, CA", "us-westcoast", ["los angeles", "la", "l.a.", "hollywood", "long beach"], 34.05, -118.24),
    ("metro-sandiego", "San Diego, CA", "us-westcoast", ["san diego", "sd"], 32.72, -117.16),
    ("metro-sf", "San Francisco Bay Area, CA", "us-westcoast", ["san francisco", "sf", "oakland", "berkeley", "san jose", "bay area"], 37.77, -122.42),
    ("metro-sacramento", "Sacramento, CA", "us-westcoast", ["sacramento", "sac"], 38.58, -121.49),
    ("metro-portland", "Portland, OR", "us-pnw", ["portland", "pdx"], 45.52, -122.68),
    ("metro-seattle", "Seattle, WA", "us-pnw", ["seattle", "tacoma", "sea"], 47.61, -122.33),
    ("metro-boise", "Boise, ID", "us-mountain", ["boise"], 43.62, -116.2),
    ("metro-toronto", "Toronto, ON", "ca", ["toronto", "gta"], 43.65, -79.38),
    ("metro-montreal", "Montréal, QC", "ca", ["montreal", "montréal"], 45.5, -73.57),
    ("metro-vancouver", "Vancouver, BC", "ca", ["vancouver"], 49.28, -123.12),
    ("metro-london", "London, UK", "uk", ["london"], 51.51, -0.13),
    ("metro-manchester", "Manchester, UK", "uk", ["manchester", "leeds", "liverpool"], 53.48, -2.24),
    ("metro-glasgow", "Glasgow, UK", "uk", ["glasgow", "edinburgh"], 55.86, -4.25),
    ("metro-dublin", "Dublin, IE", "uk", ["dublin"], 53.35, -6.26),
    ("metro-berlin", "Berlin, DE", "eu", ["berlin"], 52.52, 13.41),
    ("metro-paris", "Paris, FR", "eu", ["paris"], 48.86, 2.35),
    ("metro-amsterdam", "Amsterdam, NL", "eu", ["amsterdam"], 52.37, 4.9),
    ("metro-sydney", "Sydney, AU", "au", ["sydney"], -33.87, 151.21),
    ("metro-melbourne", "Melbourne, AU", "au", ["melbourne"], -37.81, 144.96),
    ("metro-mexicocity", "Mexico City, MX", "latam", ["mexico city", "cdmx"], 19.43, -99.13),
]

US_STATE_REGION = {
    "me": "us-northeast", "nh": "us-northeast", "vt": "us-northeast", "ma": "us-northeast", "ri": "us-northeast", "ct": "us-northeast", "ny": "us-northeast",
    "nj": "us-midatlantic", "pa": "us-midatlantic", "de": "us-midatlantic", "md": "us-midatlantic", "dc": "us-midatlantic", "wv": "us-midatlantic",
    "va": "us-southeast", "nc": "us-southeast", "sc": "us-southeast", "ga": "us-southeast", "fl": "us-southeast", "al": "us-southeast", "ms": "us-southeast", "tn": "us-southeast", "ky": "us-southeast", "ar": "us-southeast",
    "oh": "us-midwest", "mi": "us-midwest", "in": "us-midwest", "il": "us-midwest", "wi": "us-midwest", "mn": "us-midwest", "ia": "us-midwest", "mo": "us-midwest", "ks": "us-midwest", "ne": "us-midwest", "sd": "us-midwest", "nd": "us-midwest",
    "tx": "us-southcentral", "ok": "us-southcentral", "la": "us-southcentral",
    "co": "us-mountain", "ut": "us-mountain", "wy": "us-mountain", "mt": "us-mountain", "id": "us-mountain",
    "az": "us-southwest", "nm": "us-southwest", "nv": "us-southwest",
    "ca": "us-westcoast", "or": "us-pnw", "wa": "us-pnw", "ak": "us-pnw", "hi": "us-westcoast",
}

GENRES = [
    ("indie", "Indie", ["indie", "indie rock", "indie pop", "alt", "alternative", "alt rock"]),
    ("rock", "Rock", ["rock", "hard rock", "classic rock", "garage rock", "garage"]),
    ("punk", "Punk", ["punk", "pop punk", "hardcore", "post-punk", "post punk", "emo"]),
    ("metal", "Metal", ["metal", "heavy metal", "metalcore", "doom", "thrash", "death metal", "black metal"]),
    ("pop", "Pop", ["pop", "synthpop", "synth pop", "dream pop", "bedroom pop"]),
    ("synthwave", "Synthwave", ["synthwave", "retrowave", "outrun", "darkwave", "new wave"]),
    ("electronic", "Electronic", ["electronic", "electronica", "edm", "dance", "idm", "downtempo"]),
    ("house", "House", ["house", "deep house", "tech house", "disco"]),
    ("techno", "Techno", ["techno", "minimal", "acid"]),
    ("dnb", "Drum & Bass", ["drum and bass", "drum & bass", "dnb", "d&b", "jungle", "breaks"]),
    ("hiphop", "Hip-Hop", ["hip-hop", "hip hop", "hiphop", "rap", "trap", "drill", "boom bap"]),
    ("rnb", "R&B", ["r&b", "rnb", "r and b", "neo soul", "neo-soul"]),
    ("soul", "Soul / Funk", ["soul", "funk", "motown", "groove"]),
    ("jazz", "Jazz", ["jazz", "fusion", "bebop", "nu jazz"]),
    ("blues", "Blues", ["blues", "blues rock", "delta blues"]),
    ("country", "Country", ["country", "alt-country", "alt country", "country rock", "red dirt", "outlaw country"]),
    ("americana", "Americana / Folk", ["americana", "folk", "folk rock", "singer-songwriter", "singer songwriter", "roots", "acoustic"]),
    ("bluegrass", "Bluegrass", ["bluegrass", "newgrass", "old-time", "old time", "string band"]),
    ("reggae", "Reggae / Dub", ["reggae", "dub", "ska", "dancehall", "roots reggae"]),
    ("latin", "Latin", ["latin", "latin pop", "reggaeton", "cumbia", "salsa", "bachata", "regional mexican"]),
    ("world", "World / Global", ["world", "afrobeat", "afrobeats", "afropop", "global", "highlife", "amapiano"]),
    ("ambient", "Ambient / Experimental", ["ambient", "experimental", "drone", "noise", "avant-garde", "avant garde"]),
    ("classical", "Classical / Chamber", ["classical", "chamber", "orchestral", "neoclassical", "contemporary classical"]),
    ("gospel", "Gospel / Worship", ["gospel", "worship", "christian", "ccm"]),
    ("comedy", "Comedy / Spoken", ["comedy", "spoken word", "storytelling", "podcast"]),
    ("dj", "DJ Sets", ["dj", "dj set", "dj sets", "open format", "club night"]),
    ("cover", "Covers / Tribute", ["covers", "cover band", "tribute", "tribute act", "wedding band", "party band"]),
]

_REGION_BY_CODE = {r[0]: r for r in REGIONS}
_METRO_BY_CODE = {m[0]: m for m in METROS}
_GENRE_BY_CODE = {g[0]: g for g in GENRES}


def region_label(code):
    if code in _METRO_BY_CODE:
        return _METRO_BY_CODE[code][1]
    if code in _REGION_BY_CODE:
        return _REGION_BY_CODE[code][1]
    return ""


def region_parent(code):
    if code in _METRO_BY_CODE:
        return _METRO_BY_CODE[code][2]
    return code if code in _REGION_BY_CODE else None


def region_latlng(code):
    row = _METRO_BY_CODE.get(code) or _REGION_BY_CODE.get(code)
    return (row[4], row[5]) if row else None


def region_options():
    """For the datalist / typeahead: regions first, then metros A-Z."""
    out = [(r[0], r[1], "region") for r in REGIONS]
    out += sorted([(m[0], m[1], "metro") for m in METROS], key=lambda x: x[1])
    return out


def genre_label(code):
    return _GENRE_BY_CODE[code][1] if code in _GENRE_BY_CODE else code


def genre_options():
    return [(g[0], g[1]) for g in GENRES]


def _norm(s):
    return re.sub(r"\s+", " ", (s or "").strip().lower().replace("—", " ").replace("–", " ").replace("/", " ").replace(",", " ")).strip()


def parse_region(text):
    """-> (code, confidence 'exact'|'alias'|'state'|None). Longest alias wins so
    'new york' beats 'ny' and 'kansas city' beats 'kansas'."""
    t = _norm(text)
    if not t:
        return (None, None)
    best = None
    for code, label, parent, aliases, lat, lng in METROS + REGIONS:
        for a in [label.lower()] + aliases:
            a_n = _norm(a)
            if not a_n:
                continue
            if re.search(r"(?<![a-z])" + re.escape(a_n) + r"(?![a-z])", t):
                if best is None or len(a_n) > best[2]:
                    best = (code, "exact" if a_n == t else "alias", len(a_n))
    # An explicit trailing state wins over a bare city alias. City names
    # collide across states and countries - "Manchester, NH" must not file
    # as Manchester UK, and "Portland, ME" is not Portland OR. When the
    # writer named a state, believe the state.
    m = re.search(r"\b([a-z]{2})$", t)
    state_region = US_STATE_REGION.get(m.group(1)) if m else None
    if best and state_region and region_parent(best[0]) != state_region:
        return (state_region, "state")
    if best:
        return (best[0], best[1])
    # trailing state abbreviation: "Boone, NC" -> southeast
    if state_region:
        return (state_region, "state")
    return (None, None)


_MONTHS = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
_SEASONS = {"spring": (3, 5), "summer": (6, 8), "fall": (9, 11), "autumn": (9, 11), "winter": (12, 2)}


def _month_end(y, m):
    if m == 12:
        return date(y, 12, 31)
    return date(y, m + 1, 1).fromordinal(date(y, m + 1, 1).toordinal() - 1)


_MONTH_FULL = {"january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
               "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12}
# Month names that are also ordinary English words. On their own they are not
# evidence of a date; they need a year or a day number beside them.
_AMBIGUOUS_MONTHS = {"may", "march", "august"}


def _month_of(token):
    """A month only when the word IS a month - not merely starts like one.

    Matching on the first three letters turned "may be flexible" into May,
    "junction" into June and "december"-ish typos into anything, writing a
    date window the poster never stated and making the listing answer date
    filters it should not.
    """
    t = (token or "").lower()
    if t in _MONTH_FULL:
        return _MONTH_FULL[t]
    if len(t) == 3 and t in _MONTHS:
        return _MONTHS[t]
    # "sept" is the one abbreviation people write with four letters
    if t == "sept":
        return 9
    return None


def parse_window(text, today=None):
    """-> (start_iso, end_iso) or (None, None). Understands ISO dates,
    'Oct 12-15 2026', 'Sep-Oct 2026', 'October 2026', 'Fall 2026',
    'Q4 2026'. A missing year means the next time that period comes
    around."""
    today = today or date.today()
    t = (text or "").strip()
    if not t:
        return (None, None)
    iso = re.findall(r"\b(20\d{2}-\d{2}-\d{2})\b", t)
    if len(iso) >= 2:
        return (min(iso[0], iso[1]), max(iso[0], iso[1]))
    if len(iso) == 1:
        return (iso[0], iso[0])
    low = t.lower().replace("–", "-").replace("—", "-")
    year_m = re.search(r"\b(20\d{2})\b", low)
    year = int(year_m.group(1)) if year_m else None

    def year_for(month, day=1):
        if year:
            return year
        y = today.year
        try:
            return y if date(y, month, day) >= today else y + 1
        except ValueError:
            return y
    # "oct 12-15" / "october 12 - 15" / "oct 12 to 15"
    m = re.search(r"\b([a-z]{3,9})\.?\s+(\d{1,2})\s*(?:-|to|through|thru)\s*(?:([a-z]{3,9})\.?\s+)?(\d{1,2})\b", low)
    if m and _month_of(m.group(1)):
        m1 = _month_of(m.group(1)); m2 = _month_of(m.group(3)) if m.group(3) else m1
        if m2:
            y1 = year_for(m1, int(m.group(2)))
            try:
                s = date(y1, m1, int(m.group(2)))
                e = date(y1 if m2 >= m1 else y1 + 1, m2, int(m.group(4)))
                return (s.isoformat(), e.isoformat())
            except ValueError:
                pass
    # "sep-oct 2026" / "sep - nov"
    m = re.search(r"\b([a-z]{3,9})\.?\s*(?:-|to|through|thru)\s*([a-z]{3,9})\.?\b", low)
    if m and _month_of(m.group(1)) and _month_of(m.group(2)):
        m1, m2 = _month_of(m.group(1)), _month_of(m.group(2))
        y1 = year_for(m1)
        y2 = y1 if m2 >= m1 else y1 + 1
        return (date(y1, m1, 1).isoformat(), _month_end(y2, m2).isoformat())
    # single month "october 2026" / "oct" / "oct 12".
    # Scan every candidate word rather than only the first, and treat the
    # month names that are also ordinary English words as months only when
    # something corroborates them - a year or a day number. Otherwise
    # "may be flexible" and "we march on" become date windows the poster
    # never stated, and the listing answers date filters it should not.
    for m in re.finditer(r"\b([a-z]{3,9})\.?(?:\s+(\d{1,2}))?\b", low):
        mo = _month_of(m.group(1))
        if not mo:
            continue
        if m.group(1) in _AMBIGUOUS_MONTHS and not year and not m.group(2):
            continue
        if m.group(2):
            d = int(m.group(2))
            try:
                y = year_for(mo, d)
                return (date(y, mo, d).isoformat(), date(y, mo, d).isoformat())
            except ValueError:
                pass
        y = year_for(mo)
        return (date(y, mo, 1).isoformat(), _month_end(y, mo).isoformat())
    # seasons / quarters
    for name, (ms, me) in _SEASONS.items():
        if name in low:
            y = year or (today.year if date(today.year, ms, 1) >= today else today.year + 1)
            if name == "winter":
                return (date(y, 12, 1).isoformat(), _month_end(y + 1, 2).isoformat())
            return (date(y, ms, 1).isoformat(), _month_end(y, me).isoformat())
    m = re.search(r"\bq([1-4])\b", low)
    if m:
        q = int(m.group(1)); ms = (q - 1) * 3 + 1
        y = year or (today.year if date(today.year, ms, 1) >= today else today.year + 1)
        return (date(y, ms, 1).isoformat(), _month_end(y, ms + 2).isoformat())
    if year and not re.search(r"[a-z]", low.replace("q", "")):
        return (date(year, 1, 1).isoformat(), date(year, 12, 31).isoformat())
    return (None, None)


def parse_genres(text):
    """-> (codes, leftovers). Splits on the usual separators and matches
    aliases; what it cannot place comes back so the poster can see it."""
    t = (text or "").strip().lower()
    if not t:
        return ([], [])
    tokens = [x.strip() for x in re.split(r"[,/·|;+&]|\band\b", t) if x.strip()]
    codes, left = [], []
    for tok in tokens:
        hit = None
        for code, label, aliases in GENRES:
            for a in [label.lower()] + aliases:
                if re.search(r"(?<![a-z])" + re.escape(a) + r"(?![a-z])", tok):
                    if hit is None or len(a) > hit[1]:
                        hit = (code, len(a))
        if hit and hit[0] not in codes:
            codes.append(hit[0])
        elif not hit:
            left.append(tok)
    return (codes, left)


def parse_draw(text):
    """'draw 150-200', 'pull about 200', 'cap 250' -> (min, max) or (None, None).
    Capacity is not draw: 'cap' and 'capacity' are ignored."""
    low = (text or "").lower().replace(",", "")
    m = re.search(r"\b(?:draw|pull|bring|average|avg)\w*\s*(?:of|about|around|~|is|:)?\s*(\d{2,5})\s*(?:-|to|–)\s*(\d{2,5})", low)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        return (min(a, b), max(a, b))
    m = re.search(r"\b(?:draw|pull|bring|average|avg)\w*\s*(?:of|about|around|~|is|:)?\s*(\d{2,5})\b", low)
    if m:
        n = int(m.group(1))
        return (n, n)
    m = re.search(r"\b(\d{2,5})\s*(?:-|to|–)\s*(\d{2,5})\s*(?:people|heads|fans|paid|draw|tickets)\b", low)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        return (min(a, b), max(a, b))
    return (None, None)


def region_distance_km(code_a, code_b):
    import math
    a, b = region_latlng(code_a), region_latlng(code_b)
    if not a or not b:
        return None
    lat1, lon1 = map(math.radians, a); lat2, lon2 = map(math.radians, b)
    d = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return round(2 * 6371 * math.asin(math.sqrt(d)))


def regions_related(code_a, code_b):
    """Same region, same metro, or a metro inside the region."""
    if not code_a or not code_b:
        return False
    if code_a == code_b:
        return True
    return region_parent(code_a) == region_parent(code_b) or region_parent(code_a) == code_b or region_parent(code_b) == code_a \
        or code_a == "us-anywhere" or code_b == "us-anywhere"
