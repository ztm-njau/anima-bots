"""Draw Claudette's starter sticker pack (bots/claudette/memes/<tag>/01.png)."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1] / "bots" / "claudette" / "memes"
EMOJI = ImageFont.truetype("/System/Library/Fonts/Apple Color Emoji.ttc", 160)
TEXT = ImageFont.truetype("/System/Library/Fonts/Hiragino Sans GB.ttc", 46, index=1)
SMALL = ImageFont.truetype("/System/Library/Fonts/Hiragino Sans GB.ttc", 20, index=0)

PACK = [  # tag, emoji, caption, background
    ("收到", "👌", "收到！", "#FFE8D6"), ("笑死", "🤣", "笑死", "#FFF1B8"), ("救命", "😭", "救命", "#DDE7FF"),
    ("好耶", "🥳", "好耶！", "#FFE0E6"), ("晚安", "🌙", "晚安～", "#1E2448"), ("问号", "🤨", "？", "#EDE7FF"),
    ("摸鱼", "🐟", "摸鱼中", "#D9F4EA"), ("冲鸭", "🚀", "冲鸭", "#FFE3D3"), ("委屈", "🥺", "委屈", "#F3E8FF"),
    ("哼", "😤", "哼！", "#FFD9D2"), ("在吗", "👀", "在吗", "#E6F3FF"), ("谢谢", "🙏", "谢谢你", "#FFF4D6"),
    ("干饭", "🍜", "干饭！", "#FFEBD1"), ("无语", "😑", "……", "#ECEAE6"), ("比心", "🫶", "比心", "#FFE0E9"),
    ("困", "😪", "困了", "#E3E6F7"),
]


def draw(emoji: str, caption: str, bg: str) -> Image.Image:
    size = 300
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    card = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(card).rounded_rectangle((12, 12, size - 12, size - 12), radius=64, fill=bg)
    shadow = card.filter(ImageFilter.GaussianBlur(8))
    img.alpha_composite(Image.eval(shadow, lambda a: int(a * 0.35)), (0, 5))
    img.alpha_composite(card)
    glyph = Image.new("RGBA", (260, 260), (0, 0, 0, 0))
    ImageDraw.Draw(glyph).text((130, 130), emoji, font=EMOJI, embedded_color=True, anchor="mm")
    glyph = glyph.crop(glyph.getbbox() or (0, 0, 260, 260))
    glyph.thumbnail((150, 150), Image.LANCZOS)
    img.alpha_composite(glyph, ((size - glyph.width) // 2, 34 + (150 - glyph.height) // 2))
    d = ImageDraw.Draw(img)
    dark = bg == "#1E2448"
    d.text((size // 2, 228), caption, font=TEXT, fill="#FFFFFF" if dark else "#2A2420", anchor="mm",
           stroke_width=3, stroke_fill="#1E2448" if dark else "#FFFFFF")
    d.text((size - 34, size - 34), "★", font=SMALL, fill="#E5383B", anchor="mm")  # her mark
    return img


for tag, emoji, caption, bg in PACK:
    folder = ROOT / tag
    folder.mkdir(parents=True, exist_ok=True)
    draw(emoji, caption, bg).save(folder / "01.png")
print(f"{len(PACK)} stickers in {ROOT}")
