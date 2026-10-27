"""Draw Claudette's starter sticker pack (bots/claudette/memes/<tag>/01.png).

Original artwork, drawn here with plain shapes (no emoji fonts, no third-party images), so the
pack can ship under the project's MIT license. Ink lines on soft paper colours, a small vermilion
seal in the corner. Run again after editing PACK to redraw everything.
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1] / "bots" / "claudette" / "memes"
S = 3  # supersampling factor: draw big, scale down for smooth lines
SIZE = 300
INK = (43, 41, 38)
FACE = (255, 236, 196)
BLUSH = (244, 154, 140)
TEAR = (120, 170, 214)
SEAL = (176, 64, 44)

FONT_PATHS = [
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc",
]


def font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_PATHS:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size * S, index=1 if "Hiragino" in path else 0)
            except OSError:
                continue
    return ImageFont.load_default(size * S)


class Pen:
    """Coordinates are in the 300-px design space; everything is scaled by S."""

    def __init__(self, draw: ImageDraw.ImageDraw):
        self.d = draw

    def _p(self, *xy: float) -> list[float]:
        return [v * S for v in xy]

    def circle(self, cx, cy, r, fill=None, outline=INK, width=6):
        self.d.ellipse(self._p(cx - r, cy - r, cx + r, cy + r), fill=fill, outline=outline, width=width * S if outline else 0)

    def ellipse(self, x0, y0, x1, y1, fill=None, outline=None, width=0):
        self.d.ellipse(self._p(x0, y0, x1, y1), fill=fill, outline=outline, width=width * S)

    def arc(self, x0, y0, x1, y1, start, end, width=6, fill=INK):
        self.d.arc(self._p(x0, y0, x1, y1), start, end, fill=fill, width=width * S)

    def line(self, *xy, width=6, fill=INK):
        self.d.line(self._p(*xy), fill=fill, width=width * S, joint="curve")
        for x, y in (xy[:2], xy[-2:]):  # round caps
            self.d.ellipse(self._p(x - width / 2, y - width / 2, x + width / 2, y + width / 2), fill=fill)

    def poly(self, points, fill, outline=None, width=0):
        self.d.polygon([v * S for p in points for v in p], fill=fill, outline=outline, width=width * S)

    def text(self, x, y, s, size, fill=INK, stroke=None):
        self.d.text((x * S, y * S), s, font=font(size), fill=fill, anchor="mm",
                    stroke_width=(4 * S if stroke else 0), stroke_fill=stroke)


# ------------------------------------------------------------------ face parts

def eyes(p: Pen, kind: str, cx=150, cy=118):
    lx, rx = cx - 34, cx + 34
    if kind == "dot":
        for x in (lx, rx):
            p.ellipse(x - 8, cy - 10, x + 8, cy + 10, fill=INK)
    elif kind == "happy":  # ^ ^
        for x in (lx, rx):
            p.arc(x - 16, cy - 8, x + 16, cy + 20, 200, 340, width=6)
    elif kind == "laugh":  # > <
        p.line(lx - 12, cy - 10, lx + 10, cy, lx - 12, cy + 10, width=6)
        p.line(rx + 12, cy - 10, rx - 10, cy, rx + 12, cy + 10, width=6)
    elif kind == "flat":
        for x in (lx, rx):
            p.line(x - 14, cy, x + 14, cy, width=6)
    elif kind == "sleepy":
        for x in (lx, rx):
            p.arc(x - 15, cy - 14, x + 15, cy + 10, 20, 160, width=6)
    elif kind == "big":  # glossy, teary
        for x in (lx, rx):
            p.ellipse(x - 15, cy - 17, x + 15, cy + 17, fill=INK)
            p.ellipse(x - 7, cy - 11, x + 3, cy - 1, fill=(255, 255, 255))
            p.ellipse(x + 3, cy + 3, x + 8, cy + 8, fill=(255, 255, 255))
    elif kind == "wide":
        for x in (lx, rx):
            p.ellipse(x - 13, cy - 13, x + 13, cy + 13, fill=(255, 255, 255), outline=INK, width=5)
            p.ellipse(x - 5, cy - 4, x + 5, cy + 6, fill=INK)
    elif kind == "side":  # suspicious side glance
        for x in (lx, rx):
            p.line(x - 15, cy - 2, x + 15, cy - 2, width=5)
            p.ellipse(x + 2, cy - 2, x + 14, cy + 10, fill=INK)
    elif kind == "up":  # peeking up
        for x in (lx, rx):
            p.ellipse(x - 12, cy - 14, x + 12, cy + 10, fill=(255, 255, 255), outline=INK, width=5)
            p.ellipse(x - 5, cy - 14, x + 5, cy - 2, fill=INK)


def brows(p: Pen, kind: str, cx=150, cy=88):
    if kind == "angry":
        p.line(cx - 52, cy - 8, cx - 18, cy + 6, width=6)
        p.line(cx + 52, cy - 8, cx + 18, cy + 6, width=6)
    elif kind == "worried":
        p.line(cx - 50, cy + 6, cx - 18, cy - 6, width=5)
        p.line(cx + 50, cy + 6, cx + 18, cy - 6, width=5)
    elif kind == "raised":
        p.arc(cx - 52, cy - 14, cx - 18, cy + 10, 200, 330, width=5)
        p.line(cx + 18, cy, cx + 50, cy, width=5)


def mouth(p: Pen, kind: str, cx=150, cy=168):
    if kind == "smile":
        p.arc(cx - 26, cy - 22, cx + 26, cy + 10, 20, 160, width=6)
    elif kind == "open":  # big laugh, with a tongue
        p.d.chord(p._p(cx - 34, cy - 28, cx + 34, cy + 34), 0, 180, fill=INK)
        p.d.chord(p._p(cx - 16, cy + 6, cx + 16, cy + 30), 180, 360, fill=(229, 112, 101))
    elif kind == "o":
        p.ellipse(cx - 10, cy - 8, cx + 10, cy + 14, fill=INK)
    elif kind == "flat":
        p.line(cx - 18, cy, cx + 18, cy, width=6)
    elif kind == "wavy":
        pts = []
        for i in range(0, 41, 2):
            pts += [cx - 20 + i, cy + 5 * math.sin(i / 40 * math.pi * 3)]
        p.line(*pts, width=5)
    elif kind == "frown":
        p.arc(cx - 22, cy - 2, cx + 22, cy + 26, 200, 340, width=6)
    elif kind == "pout":
        p.arc(cx - 12, cy - 10, cx + 4, cy + 6, 270, 90, width=5)
        p.arc(cx - 12, cy - 2, cx + 4, cy + 14, 270, 90, width=5)
    elif kind == "cry":  # wide open wail
        p.d.chord(p._p(cx - 30, cy - 18, cx + 30, cy + 32), 180, 360, fill=INK)


def blush(p: Pen, cx=150, cy=146):
    for x in (cx - 62, cx + 62):
        p.ellipse(x - 16, cy - 8, x + 16, cy + 8, fill=BLUSH)


def tears(p: Pen, cx=150, cy=132, streams=False):
    for x in (cx - 34, cx + 34):
        if streams:
            p.d.rounded_rectangle(p._p(x - 7, cy, x + 7, cy + 70), radius=7 * S, fill=TEAR)
        else:
            p.poly([(x, cy), (x - 8, cy + 18), (x + 8, cy + 18)], fill=TEAR)
            p.ellipse(x - 8, cy + 10, x + 8, cy + 26, fill=TEAR)


def sweat(p: Pen, x=208, y=72):
    p.poly([(x, y), (x - 10, y + 22), (x + 10, y + 22)], fill=TEAR)
    p.ellipse(x - 10, y + 12, x + 10, y + 32, fill=TEAR)


def face(p: Pen, cx=150, cy=132, r=82):
    p.circle(cx, cy, r, fill=FACE, outline=INK, width=6)


# ------------------------------------------------------------------ props

def heart(p: Pen, cx, cy, s, fill=(224, 92, 92)):
    p.ellipse(cx - s, cy - s * 0.6, cx, cy + s * 0.4, fill=fill)
    p.ellipse(cx, cy - s * 0.6, cx + s, cy + s * 0.4, fill=fill)
    p.poly([(cx - s * 0.98, cy), (cx + s * 0.98, cy), (cx, cy + s * 1.1)], fill=fill)


def fish(p: Pen, cx, cy):
    p.ellipse(cx - 44, cy - 22, cx + 30, cy + 22, fill=(150, 196, 214), outline=INK, width=5)
    p.poly([(cx + 24, cy), (cx + 54, cy - 22), (cx + 54, cy + 22)], fill=(150, 196, 214), outline=INK, width=4)
    p.ellipse(cx - 30, cy - 8, cx - 20, cy + 2, fill=INK)


def bowl(p: Pen, cx, cy):
    p.line(cx - 6, cy - 70, cx + 40, cy - 6, width=5, fill=(140, 96, 58))
    p.line(cx + 10, cy - 74, cx + 52, cy - 10, width=5, fill=(140, 96, 58))
    p.d.chord(p._p(cx - 56, cy - 40, cx + 56, cy + 52), 0, 180, fill=(236, 120, 88), outline=INK, width=5 * S)
    for i in range(-36, 40, 14):
        p.arc(cx + i - 8, cy - 10, cx + i + 8, cy + 8, 180, 360, width=4, fill=(246, 214, 140))


def moon(p: Pen, cx, cy, r, bg):
    p.ellipse(cx - r, cy - r, cx + r, cy + r, fill=(240, 228, 190))
    p.ellipse(cx - r + 18, cy - r - 6, cx + r + 18, cy + r - 6, fill=bg)


def check(p: Pen, cx, cy):
    p.line(cx - 26, cy, cx - 6, cy + 22, cx + 32, cy - 24, width=12, fill=(79, 130, 115))


def speed_lines(p: Pen):
    for y, length in ((86, 60), (126, 80), (166, 54)):
        p.line(20, y, 20 + length, y, width=6, fill=(200, 180, 150))


def confetti(p: Pen):
    for x, y, c in ((44, 58, (224, 92, 92)), (252, 70, (79, 130, 115)), (60, 196, (230, 180, 70)),
                    (246, 190, (120, 150, 210)), (232, 32, (230, 180, 70)), (70, 28, (120, 150, 210))):
        p.d.rounded_rectangle(p._p(x - 6, y - 4, x + 6, y + 4), radius=2 * S, fill=c)


def zzz(p: Pen):
    p.text(238, 52, "Z", 28, fill=(120, 140, 170))
    p.text(262, 30, "z", 20, fill=(120, 140, 170))


# ------------------------------------------------------------------ the pack

def sticker(tag: str, caption: str, bg: tuple, draw_face) -> Image.Image:
    img = Image.new("RGBA", (SIZE * S, SIZE * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((10 * S, 10 * S, (SIZE - 10) * S, (SIZE - 10) * S), radius=60 * S, fill=bg)
    p = Pen(d)
    draw_face(p, bg)
    dark = sum(bg[:3]) < 200
    p.text(150, 252, caption, 40, fill=(250, 246, 236) if dark else INK, stroke=bg)
    p.d.rounded_rectangle(p._p(256, 256, 276, 276), radius=4 * S, fill=SEAL)  # her seal
    return img.resize((SIZE, SIZE), Image.LANCZOS)


def basic(e, m, *extras, br=None):
    def draw(p: Pen, bg):
        face(p)
        if br:
            brows(p, br)
        eyes(p, e)
        mouth(p, m)
        for extra in extras:
            extra(p)
    return draw


PACK = [
    ("收到", "收到！", (255, 232, 214), lambda p, bg: (basic("happy", "smile")(p, bg), check(p, 236, 72))),
    ("笑死", "笑死", (255, 241, 184), basic("laugh", "open", lambda p: tears(p, cy=124))),
    ("救命", "救命", (221, 231, 255), basic("big", "cry", lambda p: tears(p, streams=True), br="worried")),
    ("好耶", "好耶！", (255, 224, 230), lambda p, bg: (confetti(p), basic("happy", "open", blush)(p, bg))),
    ("晚安", "晚安～", (30, 36, 72), lambda p, bg: (moon(p, 230, 64, 30, bg), basic("sleepy", "smile", blush)(p, bg))),
    ("问号", "？", (237, 231, 255), basic("side", "flat", br="raised")),
    ("摸鱼", "摸鱼中", (217, 244, 234), lambda p, bg: (basic("sleepy", "smile")(p, bg), fish(p, 210, 196))),
    ("冲鸭", "冲鸭", (255, 227, 211), lambda p, bg: (speed_lines(p), basic("dot", "open", br="angry")(p, bg))),
    ("委屈", "委屈", (243, 232, 255), basic("big", "wavy", blush, lambda p: tears(p), br="worried")),
    ("哼", "哼！", (255, 217, 210), basic("flat", "pout", blush, br="angry")),
    ("在吗", "在吗", (230, 243, 255), lambda p, bg: (basic("up", "o")(p, bg), p.line(52, 60, 70, 84, width=5),
                                                     p.line(40, 92, 64, 100, width=5))),
    ("谢谢", "谢谢你", (255, 244, 214), lambda p, bg: (basic("happy", "smile", blush)(p, bg), heart(p, 236, 66, 20))),
    ("干饭", "干饭！", (255, 235, 209), lambda p, bg: (basic("wide", "o")(p, bg), bowl(p, 214, 196))),
    ("无语", "……", (236, 234, 230), basic("flat", "flat", lambda p: sweat(p))),
    ("比心", "比心", (255, 224, 233), lambda p, bg: (basic("happy", "smile", blush)(p, bg), heart(p, 236, 70, 26))),
    ("困", "困了", (227, 230, 247), lambda p, bg: (zzz(p), basic("sleepy", "o")(p, bg))),
]

if __name__ == "__main__":
    for tag, caption, bg, draw in PACK:
        folder = ROOT / tag
        folder.mkdir(parents=True, exist_ok=True)
        for old in folder.glob("*.png"):
            old.unlink()
        sticker(tag, caption, bg, draw).save(folder / "01.png", optimize=True)
    print(f"{len(PACK)} stickers in {ROOT}")
