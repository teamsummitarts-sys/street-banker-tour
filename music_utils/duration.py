import re

_FEAT_OR_AMP = re.compile(r"\bfeaturing\b|\bfeat\.?(?!\w)|&", re.IGNORECASE)


def format_duration(seconds):
    """Format a track length in seconds as mm:ss, or h:mm:ss past one hour."""
    if seconds < 0:
        raise ValueError("seconds must be non-negative")
    seconds = int(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def parse_artist_list(raw):
    """Split a credit string like 'A, B & C feat. D' into a list of names."""
    if not raw:
        return []
    normalized = _FEAT_OR_AMP.sub(",", raw)
    return [name.strip() for name in normalized.split(",") if name.strip()]
