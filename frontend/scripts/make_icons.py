"""Draw the app icons (a bowl on green). Run: python3 scripts/make_icons.py (needs Pillow)."""

from pathlib import Path

from PIL import Image, ImageDraw

GREEN = (47, 107, 79, 255)
CREAM = (247, 245, 240, 255)
OUT = Path(__file__).resolve().parent.parent / "public" / "icons"


def draw(size: int, *, maskable: bool) -> Image.Image:
    scale = 4  # draw large, then downsample for smooth edges
    s = size * scale
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if maskable:
        d.rectangle((0, 0, s, s), fill=GREEN)
        inset = s * 0.2  # keep the glyph inside the 80% safe zone
    else:
        d.rounded_rectangle((0, 0, s - 1, s - 1), radius=s * 0.22, fill=GREEN)
        inset = s * 0.16
    box = (inset, inset, s - inset, s - inset)
    w = box[2] - box[0]
    # Bowl: lower half of a circle, with a rim.
    top = box[1] + w * 0.38
    d.pieslice((box[0], top - w / 2, box[2], top + w / 2), 0, 180, fill=CREAM)
    d.rounded_rectangle((box[0] - w * 0.04, top - w * 0.05, box[2] + w * 0.04, top + w * 0.03),
                        radius=w * 0.03, fill=CREAM)
    # Steam: three short strokes.
    for i, x in enumerate((0.32, 0.5, 0.68)):
        cx = box[0] + w * x
        y0 = box[1] + w * (0.06 if i == 1 else 0.12)
        d.rounded_rectangle((cx - w * 0.035, y0, cx + w * 0.035, top - w * 0.12), radius=w * 0.035,
                            fill=CREAM)
    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    draw(192, maskable=False).save(OUT / "icon-192.png")
    draw(512, maskable=False).save(OUT / "icon-512.png")
    draw(512, maskable=True).save(OUT / "icon-maskable-512.png")
    draw(180, maskable=True).convert("RGB").save(OUT / "apple-touch-icon.png")
    draw(64, maskable=False).save(OUT.parent / "favicon.png")


if __name__ == "__main__":
    main()
