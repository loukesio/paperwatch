"""Render the animated README banner (logo.gif) and a static icon (icon.png).

    pip install pillow
    python assets/make_logo.py

Fonts: IBM Plex Sans / Mono (SIL Open Font License). Set PLEX_DIR if they are elsewhere.
"""

from __future__ import annotations

import math
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).parent
FONT_DIR = Path(os.environ.get("PLEX_DIR", "/Library/Fonts"))

S = 3  # supersampling factor for smooth edges
W, H = 900, 300
FPS = 25
DURATION = 5.6  # seconds per loop

BG = (15, 23, 42)
CARD = (30, 41, 59)
PAGE = (248, 250, 252)
FOLD = (203, 213, 225)
LINE = (203, 213, 225)
TEAL = (45, 212, 191)
AMBER = (251, 191, 36)
TEXT = (226, 232, 240)
MUTED = (148, 163, 184)

OLD_NAME = "download (3).pdf"
NEW_NAME = "Harris_2020_Array programming with NumPy.pdf"


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_DIR / name), size * S)


F_BOLD = font("IBMPlexSans-Bold.otf", 66)
F_TAG = font("IBMPlexSans-Medium.otf", 23)
F_MONO = font("IBMPlexMono-Medium.otf", 18)
F_PILL = font("IBMPlexMono-Bold.otf", 13)


def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def phase(t, start, end):
    return clamp((t - start) / (end - start))


def ease_out_back(p, k=1.6):
    p -= 1
    return 1 + (k + 1) * p ** 3 + k * p ** 2


def ease_out(p):
    return 1 - (1 - p) ** 3


def s(*v):
    """Scale coordinates to the supersampled canvas."""
    return [round(x * S) for x in v]


# ---------------------------------------------------------------- page icon
PX, PY, PW, PH, FOLD_SZ = 72, 70, 124, 160, 30
LINES = [  # (x offset, width) of the gray "text" lines; index 3 is the DOI line
    (16, 92), (16, 78), (16, 92), (16, 64), (16, 92), (16, 84), (16, 50),
]


def draw_page(layer: Image.Image, t: float, dy: float):
    d = ImageDraw.Draw(layer)
    x, y = PX, PY + dy

    # shadow
    d.rounded_rectangle(s(x + 6, y + 8, x + PW + 6, y + PH + 8), radius=10 * S, fill=(0, 0, 0, 70))
    # page with folded top-right corner
    body = [(x, y), (x + PW - FOLD_SZ, y), (x + PW, y + FOLD_SZ), (x + PW, y + PH), (x, y + PH)]
    d.polygon([(px * S, py * S) for px, py in body], fill=PAGE)
    fold = [(x + PW - FOLD_SZ, y), (x + PW - FOLD_SZ, y + FOLD_SZ), (x + PW, y + FOLD_SZ)]
    d.polygon([(px * S, py * S) for px, py in fold], fill=FOLD)

    # title bar
    d.rounded_rectangle(s(x + 16, y + 22, x + 80, y + 31), radius=4 * S, fill=TEAL)

    scan = phase(t, 0.95, 1.75)
    beam_y = y + 14 + scan * (PH - 22)
    doi_found = t >= 0.95 + 0.8 * (3 / 6.5)
    for i, (ox, lw) in enumerate(LINES):
        ly = y + 50 + i * 14
        color = LINE
        if i == 3 and doi_found:
            color = AMBER
        d.rounded_rectangle(s(x + ox, ly, x + ox + lw, ly + 5), radius=2.5 * S, fill=color)

    # scanning beam
    if 0 < scan < 1:
        band = Image.new("RGBA", layer.size, (0, 0, 0, 0))
        bd = ImageDraw.Draw(band)
        bd.rectangle(s(x, beam_y - 16, x + PW, beam_y), fill=(*TEAL, 45))
        bd.rectangle(s(x - 6, beam_y - 1.5, x + PW + 6, beam_y + 1.5), fill=(*TEAL, 255))
        layer.alpha_composite(band)

    # "DOI" pill pops out next to the highlighted line
    pop = phase(t, 1.45, 1.8)
    if pop > 0:
        k = ease_out_back(pop)
        cx, cy = x + PW + 4, y + 50 + 3 * 14 + 2
        w, h = 44 * k, 20 * k
        d.rounded_rectangle(s(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2), radius=10 * S * k, fill=AMBER)
        if k > 0.7:
            d.text((cx * S, cy * S), "DOI", font=F_PILL, fill=BG, anchor="mm")

    # check mark badge when the rename is done
    done = phase(t, 3.85, 4.2)
    if done > 0:
        k = ease_out_back(done, 2.2)
        cx, cy, r = x + PW - 2, y + PH - 4, 21 * k
        d.ellipse(s(cx - r - 4, cy - r - 4, cx + r + 4, cy + r + 4), fill=BG)
        d.ellipse(s(cx - r, cy - r, cx + r, cy + r), fill=TEAL)
        if k > 0.5:
            pts = [(cx - 9 * k, cy + 1 * k), (cx - 3 * k, cy + 7 * k), (cx + 10 * k, cy - 7 * k)]
            d.line([(px * S, py * S) for px, py in pts], fill=BG, width=round(4.5 * S * k), joint="curve")


# ---------------------------------------------------------------- right column
TX = 252


def draw_text(img: Image.Image, t: float):
    d = ImageDraw.Draw(img)
    d.text((TX * S, 62 * S), "paper", font=F_BOLD, fill=TEXT, anchor="la")
    pw = d.textlength("paper", font=F_BOLD)
    d.text((TX * S + pw, 62 * S), "watch", font=F_BOLD, fill=TEAL, anchor="la")
    d.text((TX * S, 152 * S), "Download a paper. It renames itself.", font=F_TAG, fill=MUTED, anchor="la")

    # terminal-style file name line
    d.rounded_rectangle(s(TX - 2, 196, W - 34, 240), radius=10 * S, fill=CARD)
    ty = 218
    d.text(((TX + 16) * S, ty * S), "›", font=F_MONO, fill=TEAL, anchor="lm")
    nx = (TX + 38) * S

    delete = phase(t, 1.95, 2.45)
    typing = phase(t, 2.55, 3.8)
    if t < 2.55:
        name = OLD_NAME[: round(len(OLD_NAME) * (1 - delete))]
        d.text((nx, ty * S), name, font=F_MONO, fill=MUTED, anchor="lm")
        end = nx + d.textlength(name, font=F_MONO)
    else:
        name = NEW_NAME[: round(len(NEW_NAME) * typing)]
        stem, dot, ext = name.partition(".pdf")
        d.text((nx, ty * S), stem, font=F_MONO, fill=TEXT, anchor="lm")
        end = nx + d.textlength(stem, font=F_MONO)
        if dot:
            d.text((end, ty * S), ".pdf", font=F_MONO, fill=MUTED, anchor="lm")
            end += d.textlength(".pdf", font=F_MONO)

    # blinking cursor (solid while editing)
    editing = 1.9 < t < 3.85
    if editing or int(t * 2.5) % 2 == 0:
        d.rectangle((end + 3 * S, (ty - 10) * S, end + 13 * S, (ty + 10) * S), fill=TEAL)


# ---------------------------------------------------------------- frames
def frame(t: float) -> Image.Image:
    img = Image.new("RGBA", (W * S, H * S), BG)

    # page drops in, then fades out at the end of the loop
    drop = phase(t, 0.0, 0.75)
    dy = -300 * (1 - ease_out_back(drop)) if drop < 1 else 0
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw_page(layer, t, dy)
    fade = 1 - phase(t, 5.15, 5.5)
    if fade < 1:
        a = layer.getchannel("A").point(lambda v: round(v * fade))
        layer.putalpha(a)
    img.alpha_composite(layer)

    draw_text(img, t if t < 5.3 else 0)  # reset the file name for the next loop
    return img.resize((W, H), Image.LANCZOS).convert("RGB")


def make_gif(path: Path):
    n = round(DURATION * FPS)
    frames = [frame(i / FPS) for i in range(n)]
    # One shared palette keeps colors stable between frames (no flicker).
    palette = frames[round(4.5 * FPS)].quantize(colors=96, method=Image.Quantize.MEDIANCUT)
    pal_frames = [f.quantize(palette=palette, dither=Image.Dither.NONE) for f in frames]
    durations = [1000 // FPS] * n
    pal_frames[0].save(path, save_all=True, append_images=pal_frames[1:], duration=durations,
                       loop=0, optimize=True, disposal=1)


def make_icon(path: Path, size: int = 512):
    """Static square icon: the page with the DOI highlight and the check mark."""
    global W, H
    img = Image.new("RGBA", (W * S, H * S), BG)
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw_page(layer, 5.0, 0)
    img.alpha_composite(layer)
    img = img.resize((W, H), Image.LANCZOS)
    cx, cy = PX + PW / 2 + 6, PY + PH / 2 + 4
    half = 125
    img = img.crop((round(cx - half), round(cy - half), round(cx + half), round(cy + half)))
    img = img.resize((size, size), Image.LANCZOS)
    # rounded app-icon mask
    mask = Image.new("L", (size * 4, size * 4), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size * 4, size * 4), radius=size * 4 * 0.22, fill=255)
    img.putalpha(mask.resize((size, size), Image.LANCZOS))
    img.save(path)


if __name__ == "__main__":
    make_gif(OUT / "logo.gif")
    make_icon(OUT / "icon.png")
    for f in ("logo.gif", "icon.png"):
        print(f, (OUT / f).stat().st_size // 1024, "KB")
