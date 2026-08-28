"""Free public music APIs: iTunes Search (real tracks, artwork, 30-second
previews — no key) and Odesli/Songlink (universal all-platform links —
no key, 10 req/min). Responses are cached in SQLite to respect rate
limits and keep pages fast. `_fetch_json` is the seam tests monkeypatch
so no test ever touches the network.
"""

import json
import time
import urllib.parse
import urllib.request

import db as store

_TIMEOUT = 12
_UA = "StreetBanker/1.0 (team.summitarts@gmail.com)"

ITUNES_TTL = 24 * 3600        # searches refresh daily
ODESLI_TTL = 7 * 24 * 3600    # platform link sets are stable


def _fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_image_bytes(url, timeout=60):
    """Raw image download (used by the artwork generator save). Seam for tests."""
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _fetch_text(url):
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return resp.read().decode("utf-8", "replace")


def itunes_search(term, limit=18):
    """Real songs from the iTunes catalog: title, artist, art, preview."""
    term = (term or "").strip()
    if not term:
        return []
    key = "itunes:%d:%s" % (limit, term.lower())
    data = store.cache_get(key, ITUNES_TTL)
    if data is None:
        url = "https://itunes.apple.com/search?" + urllib.parse.urlencode(
            {"term": term, "entity": "song", "limit": limit})
        try:
            data = _fetch_json(url)
        except Exception:
            return []
        store.cache_set(key, data)
    out = []
    for t in data.get("results", []):
        art = (t.get("artworkUrl100") or "").replace("100x100", "300x300")
        if not (t.get("trackName") and art):
            continue
        out.append({
            "title": t.get("trackName"),
            "artist": t.get("artistName") or "",
            "album": t.get("collectionName") or "",
            "art": art,
            "preview": t.get("previewUrl") or "",
            "url": t.get("trackViewUrl") or "",
        })
    return out


def odesli_lookup(source_url):
    """One track URL in -> every platform's link out. None on failure."""
    source_url = (source_url or "").strip()
    if not source_url.startswith("http"):
        return None
    key = "odesli:" + source_url
    data = store.cache_get(key, ODESLI_TTL)
    if data is None:
        url = "https://api.song.link/v1-alpha.1/links?" + urllib.parse.urlencode(
            {"url": source_url})
        try:
            data = _fetch_json(url)
        except Exception:
            return None
        store.cache_set(key, data)
    try:
        uid = data.get("entityUniqueId")
        ent = (data.get("entitiesByUniqueId") or {}).get(uid, {})
        links = {p: v.get("url") for p, v in (data.get("linksByPlatform") or {}).items()
                 if v.get("url")}
        if not links:
            return None
        return {
            "title": ent.get("title") or "",
            "artist": ent.get("artistName") or "",
            "art": ent.get("thumbnailUrl") or "",
            "page": data.get("pageUrl") or "",
            "links": links,
        }
    except Exception:
        return None


DEEZER_TTL = 30 * 24 * 3600   # ISRC/UPC assignments never change


def deezer_track_metadata(title, artist):
    """Industry identifiers for a track from Deezer's free API: ISRC, and
    the album's UPC, label, release date. Returns a dict or None."""
    title = (title or "").strip()
    artist = (artist or "").strip()
    if not title:
        return None
    key = "deezer2:%s|%s" % (title.lower(), artist.lower())
    data = store.cache_get(key, DEEZER_TTL)
    if data is None:
        # Plain keyword query — Deezer's quoted advanced syntax 404s when urlencoded.
        url = "https://api.deezer.com/search?" + urllib.parse.urlencode(
            {"q": ("%s %s" % (title, artist)).strip(), "limit": 1})
        try:
            hits = (_fetch_json(url).get("data") or [])
            if not hits:
                data = {}
            else:
                track = _fetch_json("https://api.deezer.com/track/%s" % hits[0]["id"])
                album_id = (track.get("album") or {}).get("id")
                album = _fetch_json("https://api.deezer.com/album/%s" % album_id) if album_id else {}
                data = {"track": track, "album": album}
        except Exception:
            return None
        store.cache_set(key, data)
    track = data.get("track") or {}
    if not track:
        return None
    album = data.get("album") or {}
    genres = [g.get("name") for g in ((album.get("genres") or {}).get("data") or [])
              if g.get("name")]
    return {
        "isrc": track.get("isrc") or "",
        "upc": album.get("upc") or "",
        "label": album.get("label") or "",
        "release_date": album.get("release_date") or track.get("release_date") or "",
        "album": album.get("title") or (track.get("album") or {}).get("title") or "",
        "genre": genres[0] if genres else "",
        "duration": track.get("duration") or 0,
        "track_count": album.get("nb_tracks") or 0,
    }


def deezer_artist_fans(name):
    """Deezer fan count for an artist by name — a second platform signal
    for Artist Pulse. Returns {name, fans, url} or None."""
    name = (name or "").strip()
    if not name:
        return None
    key = "deezerartist:%s" % name.lower()
    data = store.cache_get(key, DEEZER_TTL)
    if data is None:
        url = "https://api.deezer.com/search/artist?" + urllib.parse.urlencode(
            {"q": name, "limit": 1})
        try:
            hits = _fetch_json(url).get("data") or []
        except Exception:
            return None
        data = hits[0] if hits else {}
        store.cache_set(key, data)
    if not data.get("id"):
        return None
    return {"name": data.get("name") or name,
            "fans": data.get("nb_fan") or 0,
            "url": data.get("link") or ""}


PRESS_TTL = 24 * 3600  # news results refresh daily


def press_mentions(term, limit=10):
    """Real press coverage from Google News RSS (no key). Returns
    [{title, source, url, date}] for the artist to pick from."""
    term = (term or "").strip()
    if not term:
        return []
    key = "press:" + term.lower()
    cached = store.cache_get(key, PRESS_TTL)
    if cached is not None:
        return cached[:limit]
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(
        {"q": term, "hl": "en-US", "gl": "US", "ceid": "US:en"})
    try:
        import xml.etree.ElementTree as ET
        root = ET.fromstring(_fetch_text(url))
        out = []
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            source = (item.findtext("source") or "").strip()
            link = (item.findtext("link") or "").strip()
            date = (item.findtext("pubDate") or "").strip()
            if not title:
                continue
            # Google News titles end with " - Publication"; keep the headline.
            if source and title.endswith(" - " + source):
                title = title[: -len(" - " + source)]
            out.append({"title": title, "source": source or "News",
                        "url": link, "date": date[:16]})
    except Exception:
        return []
    store.cache_set(key, out)
    return out[:limit]


MUSICBRAINZ_TTL = 30 * 24 * 3600
_MB = "https://musicbrainz.org/ws/2"
_WRITER_ROLES = {"composer", "lyricist", "writer"}


def musicbrainz_credits(isrc):
    """Songwriters and publishers for a recording, looked up by ISRC in the
    open MusicBrainz database (no key, 1 request/second). Returns
    {"writers": [...], "publishers": [...]} or None."""
    isrc = (isrc or "").strip().upper()
    if not isrc:
        return None
    key = "mb:" + isrc
    data = store.cache_get(key, MUSICBRAINZ_TTL)
    if data is None:
        try:
            recs = _fetch_json("%s/isrc/%s?fmt=json" % (_MB, isrc)).get("recordings", [])
            works, relations = [], []
            if recs:
                time.sleep(1.05)  # MusicBrainz rate limit
                rec = _fetch_json("%s/recording/%s?fmt=json&inc=work-rels" % (_MB, recs[0]["id"]))
                works = [rel["work"]["id"] for rel in rec.get("relations", [])
                         if rel.get("work")]
            if works:
                time.sleep(1.05)
                w = _fetch_json("%s/work/%s?fmt=json&inc=artist-rels+label-rels" % (_MB, works[0]))
                relations = w.get("relations", [])
            data = {"relations": relations}
        except Exception:
            return None
        store.cache_set(key, data)
    writers, publishers = [], []
    for rel in data.get("relations", []):
        name = ((rel.get("artist") or rel.get("label")) or {}).get("name")
        if not name:
            continue
        bucket = writers if rel.get("type") in _WRITER_ROLES else (
            publishers if rel.get("type") == "publisher" else None)
        if bucket is not None and name not in bucket:
            bucket.append(name)
    if not writers and not publishers:
        return None
    return {"writers": writers, "publishers": publishers}


# Display order + branding for the universal landing page.
PLATFORM_DISPLAY = [
    ("spotify", "Spotify", "spotify"),
    ("appleMusic", "Apple Music", "apple"),
    ("itunes", "iTunes", "apple"),
    ("youtube", "YouTube", "youtube"),
    ("youtubeMusic", "YouTube Music", "youtube"),
    ("tidal", "TIDAL", "other"),
    ("deezer", "Deezer", "other"),
    ("amazonMusic", "Amazon Music", "other"),
    ("soundcloud", "SoundCloud", "other"),
    ("pandora", "Pandora", "other"),
    ("audiomack", "Audiomack", "other"),
]


def ordered_platform_links(links):
    """[(label, logo_key, url)] in display order, then any extras."""
    out, seen = [], set()
    for key, label, logo in PLATFORM_DISPLAY:
        if links.get(key):
            out.append((label, logo, links[key]))
            seen.add(key)
    for key, url in links.items():
        if key not in seen:
            out.append((key.replace("Music", " Music").title(), "other", url))
    return out
