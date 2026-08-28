"""Audio conversion that the browser cannot do.

The Rack already converts in the tab: WAV and AIFF, any bit depth, any
sample rate, dithered, without a byte leaving the machine. That covers
mastering deliverables and nothing else, which is why a track could go in
as an MP3 and never come back out as one - there is no MP3 encoder in a
browser, and this app ships no build step and loads nothing from a CDN.

There is an ffmpeg on the server, with libmp3lame, flac, aac, alac,
libopus and libvorbis. So the compressed formats happen here instead.

Two rules this module holds to:

  Nothing is guessed at the command line. Every codec, bitrate, rate and
  channel count is looked up in the tables below and passed as separate
  argv entries. No user string is ever interpolated into an argument, and
  the shell is never involved.

  It says when it cannot. If ffmpeg is missing the caller gets told, so
  the UI can hide server formats rather than offering a button that
  fails.

The privacy trade is real and belongs to the user: local conversion keeps
the file in the tab, this does not. The caller is responsible for saying
so before the upload happens.
"""
import os
import shutil
import subprocess
import tempfile

# Enough for a long lossless master; past this, the answer is to bounce
# something smaller rather than to tie up the box.
MAX_BYTES = 200 * 1024 * 1024

# ffmpeg is fast, but a pathological file should not hold a worker open.
TIMEOUT = 300

# What we accept in. Extensions only decide the temp file's suffix -
# ffmpeg sniffs the actual content, so a mislabelled file fails cleanly
# rather than being trusted.
INPUT_EXTS = (".wav", ".mp3", ".flac", ".m4a", ".aiff", ".aif", ".ogg",
              ".opus", ".aac", ".wma", ".alac", ".mp4", ".webm")

# The formats worth offering, each with the exact arguments to produce it.
# "lossy" drives the UI's warning; "bitrates" empty means the quality
# knob does not apply.
FORMATS = {
    "mp3": {
        "label": "MP3",
        "ext": "mp3",
        "mime": "audio/mpeg",
        "lossy": True,
        "args": ["-c:a", "libmp3lame"],
        "bitrates": (320, 256, 192, 160, 128),
        "default_bitrate": 320,
        "note": "Plays everywhere. 320 is the highest MP3 there is.",
    },
    "flac": {
        "label": "FLAC",
        "ext": "flac",
        "mime": "audio/flac",
        "lossy": False,
        # -compression_level 8 is slower to write, identical to decode.
        "args": ["-c:a", "flac", "-compression_level", "8"],
        "bitrates": (),
        "note": "Lossless, about half the size of WAV. Taken by most "
                "distributors and every mastering house.",
    },
    "alac": {
        "label": "ALAC (Apple Lossless)",
        "ext": "m4a",
        "mime": "audio/mp4",
        "lossy": False,
        "args": ["-c:a", "alac"],
        "bitrates": (),
        "note": "Lossless, and what Apple Music wants.",
    },
    "aac": {
        "label": "AAC (M4A)",
        "ext": "m4a",
        "mime": "audio/mp4",
        "lossy": True,
        "args": ["-c:a", "aac"],
        "bitrates": (256, 192, 160, 128),
        "default_bitrate": 256,
        "note": "Better than MP3 at the same size. The usual choice for "
                "video and for Apple.",
    },
    "opus": {
        "label": "Opus",
        "ext": "opus",
        "mime": "audio/opus",
        "lossy": True,
        "args": ["-c:a", "libopus"],
        "bitrates": (192, 128, 96, 64),
        "default_bitrate": 128,
        "note": "The most music per byte of anything here. Newer players "
                "only.",
    },
    "vorbis": {
        "label": "OGG Vorbis",
        "ext": "ogg",
        "mime": "audio/ogg",
        "lossy": True,
        "args": ["-c:a", "libvorbis"],
        "bitrates": (256, 192, 160, 128),
        "default_bitrate": 192,
        "note": "Open format. What Spotify streams behind the scenes.",
    },
    "wav": {
        "label": "WAV",
        "ext": "wav",
        "mime": "audio/wav",
        "lossy": False,
        "args": ["-c:a", "pcm_s24le"],
        "bitrates": (),
        "note": "Uncompressed. The Rack can also do this in the tab, "
                "without uploading.",
    },
    "aiff": {
        "label": "AIFF",
        "ext": "aiff",
        "mime": "audio/aiff",
        "lossy": False,
        "args": ["-c:a", "pcm_s24be"],
        "bitrates": (),
        "note": "Uncompressed, big-endian. The Rack can also do this in "
                "the tab.",
    },
}

RATES = (22050, 32000, 44100, 48000, 88200, 96000)
CHANNELS = (1, 2)

# Some codecs do not accept every rate. Opus is the strict one: it works
# at 8/12/16/24/48 kHz and nothing else, so asking it for 44.1 fails the
# whole conversion. Rather than refuse, resample to the nearest rate the
# codec does support and say so - a 48 kHz Opus is what the user wanted,
# and 44.1 was never available to them.
CODEC_RATES = {
    "opus": (8000, 12000, 16000, 24000, 48000),
}


def resolve_rate(fmt, rate):
    """(rate to use, note) - the note is None when nothing was changed."""
    allowed = CODEC_RATES.get(fmt)
    if rate not in RATES:
        rate = None
    if not allowed:
        return rate, None
    if rate is None:
        return 48000, None                    # Opus's own default
    if rate in allowed:
        return rate, None
    best = min(allowed, key=lambda r: (abs(r - rate), -r))
    return best, "%s cannot store %d kHz; written at %d kHz instead." % (
        FORMATS[fmt]["label"], rate // 1000 if rate >= 1000 else rate,
        best // 1000)

# Bit depth only means anything for the PCM containers.
DEPTHS = {
    "wav": {16: "pcm_s16le", 24: "pcm_s24le", 32: "pcm_f32le"},
    "aiff": {16: "pcm_s16be", 24: "pcm_s24be", 32: "pcm_f32be"},
}


def ffmpeg_path():
    return shutil.which("ffmpeg")


def available():
    """Can this box convert at all?"""
    return bool(ffmpeg_path())


def format_list():
    """The menu, for the UI. Lossless first - they are the safe default."""
    order = ("flac", "alac", "wav", "aiff", "mp3", "aac", "opus", "vorbis")
    out = []
    for key in order:
        spec = FORMATS[key]
        out.append({
            "value": key,
            "label": spec["label"],
            "lossy": spec["lossy"],
            "bitrates": list(spec["bitrates"]),
            "default_bitrate": spec.get("default_bitrate"),
            "note": spec["note"],
            "ext": spec["ext"],
        })
    return out


def build_args(src, dst, fmt, bitrate=None, rate=None, channels=None,
               depth=None):
    """The exact argv for one conversion.

    Split out from convert() so a test can read the command without
    running ffmpeg - which is the only way to be sure no user value ever
    reaches it unchecked.
    """
    spec = FORMATS[fmt]
    args = [ffmpeg_path() or "ffmpeg", "-nostdin", "-y",
            "-i", src, "-map_metadata", "0", "-vn"]

    codec = list(spec["args"])
    if fmt in DEPTHS and depth in DEPTHS[fmt]:
        codec = ["-c:a", DEPTHS[fmt][depth]]     # a real choice for PCM
    args += codec

    if spec["bitrates"]:
        want = bitrate if bitrate in spec["bitrates"] \
            else spec.get("default_bitrate")
        if want:
            args += ["-b:a", "%dk" % want]

    use_rate, _ = resolve_rate(fmt, rate)
    if use_rate:
        args += ["-ar", str(use_rate)]
    if channels in CHANNELS:
        args += ["-ac", str(channels)]

    args.append(dst)
    return args


def convert(data, filename, fmt, bitrate=None, rate=None, channels=None,
            depth=None):
    """Returns (bytes, download_name, None) or (None, None, error)."""
    # The request is checked before the environment. A bad format or an
    # oversized file is wrong on any box, and saying "no encoder here"
    # would send someone looking in entirely the wrong place.
    if fmt not in FORMATS:
        return None, None, "unknown format"
    if not data:
        return None, None, "no audio"
    if len(data) > MAX_BYTES:
        return None, None, "file is over %d MB" % (MAX_BYTES // (1024 * 1024))
    if not available():
        return None, None, "no encoder installed on this server"

    in_ext = os.path.splitext(filename or "")[1].lower()
    if in_ext not in INPUT_EXTS:
        in_ext = ".bin"          # let ffmpeg sniff it rather than refuse
    spec = FORMATS[fmt]

    tmp = tempfile.mkdtemp(prefix="sbconv")
    src = os.path.join(tmp, "in" + in_ext)
    dst = os.path.join(tmp, "out." + spec["ext"])
    try:
        with open(src, "wb") as fh:
            fh.write(data)
        proc = subprocess.run(
            build_args(src, dst, fmt, bitrate, rate, channels, depth),
            capture_output=True, timeout=TIMEOUT)
        if proc.returncode != 0 or not os.path.isfile(dst):
            # ffmpeg's last line is the useful one; the banner is not.
            tail = (proc.stderr or b"").decode("utf8", "replace").strip()
            tail = tail.splitlines()[-1] if tail else "conversion failed"
            return None, None, tail[:300]
        with open(dst, "rb") as fh:
            out = fh.read()
        stem = os.path.splitext(os.path.basename(filename or "audio"))[0]
        return out, "%s.%s" % (stem or "audio", spec["ext"]), None
    except subprocess.TimeoutExpired:
        return None, None, "conversion took too long and was stopped"
    except OSError as exc:
        return None, None, "conversion failed: %s" % exc
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
