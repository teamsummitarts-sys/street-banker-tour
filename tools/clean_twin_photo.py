"""Take the photograph out of the Section 5 reference and clear the
generated text from it.

The supplied frame carries an invented album track list on the wall
("4. CHECOUNG PPLS", "6. DED CLOCK"), a visual-direction list, release
notes on the table, and Street Banker lettering on a poster, a print, a
cap and the rug. All of it is generated text, and the brief for this
section rules out generated track lists, malformed handwriting and fake
merchandise inside the photograph.

Each marked area is filled from its own edges - a smooth surface
interpolated between the pixels bordering the patch, so the fill starts
at exactly the tone of the wall, paper or cloth around it and carries
the same light falloff - and then given back the grain of a clean piece
of the same surface. A blurred rectangle reads as a censored photograph
and a pasted patch reads as a stain; this reads as a wall with nothing
written on it.

Nothing else is touched: the artist, the room, the prints, the moving
figures and the light are as supplied.
"""
from PIL import Image, ImageFilter, ImageDraw

SRC = r"C:\Users\17049\Downloads\05EAF14F-DD45-47B7-A2FF-34B09F3E0308.png"
SCRATCH = (r"C:\Users\17049\AppData\Local\Temp\claude"
           r"\C--Users-17049-OneDrive-Desktop-claude"
           r"\ca78877a-8c3c-431b-9d12-aa3b4f805e2d\scratchpad")

PHOTO = (0, 0, 893, 941)
FEATHER = 5
GRAIN_SOURCE = (120, 46)        # plain concrete, left of the wall writing

# (box, grain amount). Paper and cloth carry less texture than concrete.
ZONES = [
    ((332, 52, 472, 252), 0.85),      # album line + track list
    ((548, 334, 660, 444), 0.85),     # visual direction list
    ((744, 192, 852, 306), 0.35),     # poster on the wall
    ((475, 655, 662, 802), 0.35),     # release notes sheet
    ((0, 650, 210, 766), 0.45),       # rug
    ((402, 648, 512, 722), 0.30),     # print on the table
    ((735, 752, 815, 815), 0.30),     # cap
    ((552, 552, 632, 604), 0.30),     # small print by the artist
]

# The table runs towards the camera, so it falls out of focus the way it
# would through a fast lens. This finishing pass carries the edge fills
# on the table into that falloff instead of leaving them as flat repairs.
FOREGROUND = (640, 941, 0.0, 4.5)     # from y, to y, from radius, to radius


def _mask(size, feather):
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).rectangle(
        [feather, feather, size[0] - feather - 1, size[1] - feather - 1], fill=255)
    return m.filter(ImageFilter.GaussianBlur(feather * 0.8))


def _fill_from_edges(photo, box):
    """A smooth surface pinned to the pixels just outside the box."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    px = photo.load()
    left = [px[x0 - 1, y] for y in range(y0, y1)]
    right = [px[x1, y] for y in range(y0, y1)]
    top = [px[x, y0 - 1] for x in range(x0, x1)]
    bottom = [px[x, y1] for x in range(x0, x1)]

    out = Image.new("RGB", (w, h))
    op = out.load()
    for j in range(h):
        for i in range(w):
            u = (i + 0.5) / w                      # 0 at the left edge
            v = (j + 0.5) / h
            # Distance to the nearer horizontal edge decides how much the
            # horizontal interpolation is trusted against the vertical one.
            wh = min(v, 1 - v) + 1e-6
            wv = min(u, 1 - u) + 1e-6
            total = wh + wv
            value = []
            for c in range(3):
                horizontal = left[j][c] * (1 - u) + right[j][c] * u
                vertical = top[i][c] * (1 - v) + bottom[i][c] * v
                value.append(int(round((horizontal * wh + vertical * wv) / total)))
            op[i, j] = tuple(value)
    return out


def _grain(photo, size, amount):
    """The high-frequency part of a clean piece of the same room."""
    w, h = size
    sx, sy = GRAIN_SOURCE
    patch = photo.crop((sx, sy, sx + min(w, 200), sy + min(h, 210)))
    if patch.size != size:                          # mirror out to fit
        tile = Image.new("RGB", size)
        for ox in range(0, w, patch.width):
            for oy in range(0, h, patch.height):
                flip = patch.transpose(Image.FLIP_LEFT_RIGHT) if (ox // patch.width) % 2 else patch
                if (oy // patch.height) % 2:
                    flip = flip.transpose(Image.FLIP_TOP_BOTTOM)
                tile.paste(flip, (ox, oy))
        patch = tile
    base = patch.filter(ImageFilter.GaussianBlur(3))
    pp, bp = patch.load(), base.load()
    out = Image.new("RGB", size)
    op = out.load()
    for j in range(h):
        for i in range(w):
            op[i, j] = tuple(int(round((pp[i, j][c] - bp[i, j][c]) * amount)) + 128
                             for c in range(3))
    return out


def _depth_of_field(photo):
    y_from, y_to, r_from, r_to = FOREGROUND
    steps = 9
    for step in range(steps):
        top = int(y_from + (y_to - y_from) * step / steps)
        bottom = int(y_from + (y_to - y_from) * (step + 1) / steps)
        radius = r_from + (r_to - r_from) * (step + 0.5) / steps
        if radius < 0.4 or bottom <= top:
            continue
        pad = int(radius * 3) + 2
        y0, y1 = max(0, top - pad), min(photo.height, bottom + pad)
        strip = photo.crop((0, y0, photo.width, y1)).filter(
            ImageFilter.GaussianBlur(radius))
        photo.paste(strip.crop((0, top - y0, photo.width, bottom - y0)), (0, top))
    return photo


def clean(photo):
    for box, amount in ZONES:
        w, h = box[2] - box[0], box[3] - box[1]
        fill = _fill_from_edges(photo, box).filter(ImageFilter.GaussianBlur(2))
        grain = _grain(photo, (w, h), amount)
        fp, gp = fill.load(), grain.load()
        for j in range(h):
            for i in range(w):
                fp[i, j] = tuple(max(0, min(255, fp[i, j][c] + gp[i, j][c] - 128))
                                 for c in range(3))
        photo.paste(fill, (box[0], box[1]), _mask((w, h), FEATHER))
    return _depth_of_field(photo)


if __name__ == "__main__":
    photo = clean(Image.open(SRC).convert("RGB").crop(PHOTO))
    photo.save(SCRATCH + r"\twin-photo-clean.png")
    print("clean:", photo.size)
    for name, box in [("wall", (300, 30, 700, 470)), ("table", (380, 600, 893, 840)),
                      ("rug", (0, 620, 260, 800))]:
        photo.crop(box).save(SCRATCH + r"\clean-%s.png" % name)
