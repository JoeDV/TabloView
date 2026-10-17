"""TabloView app icon, drawn with Pillow (used by the tray icon and to build the .ico)."""

from PIL import Image, ImageDraw


def draw_icon(size: int = 256) -> Image.Image:
    scale = 4  # supersample for smooth edges
    s = size * scale
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))

    # Blue-to-violet rounded square
    grad = Image.new("RGBA", (s, s))
    gd = ImageDraw.Draw(grad)
    top, bottom = (91, 140, 255), (139, 91, 255)
    for y in range(s):
        t = y / (s - 1)
        gd.line([(0, y), (s, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)) + (255,))
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, s - 1, s - 1], radius=int(s * 0.22), fill=255)
    img.paste(grad, (0, 0), mask)

    # White TV outline with antenna
    d = ImageDraw.Draw(img)
    w = max(2, int(s * 0.065))
    d.rounded_rectangle([s * 0.2, s * 0.36, s * 0.8, s * 0.78], radius=int(s * 0.07), outline="white", width=w)
    d.line([(s * 0.36, s * 0.2), (s * 0.5, s * 0.34), (s * 0.64, s * 0.2)], fill="white", width=w, joint="curve")
    # Play triangle inside the screen
    d.polygon([(s * 0.44, s * 0.46), (s * 0.44, s * 0.68), (s * 0.62, s * 0.57)], fill="white")

    return img.resize((size, size), Image.LANCZOS)


def save_ico(path: str) -> None:
    draw_icon(256).save(path, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


def save_msix_assets(folder: str) -> None:
    """Tile, Start menu and taskbar images referenced by packaging/msix/AppxManifest.xml."""
    from pathlib import Path
    out = Path(folder)
    out.mkdir(parents=True, exist_ok=True)

    def square(name, size, pad=0.0):
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        inner = max(1, round(size * (1 - 2 * pad)))
        canvas.paste(draw_icon(inner), ((size - inner) // 2,) * 2)
        canvas.save(out / name)

    square("StoreLogo.png", 50)
    square("Square44x44Logo.png", 44)
    square("Square150x150Logo.png", 150, pad=0.2)
    for s in (16, 24, 32, 48, 256):
        # Taskbar / Start list icons drawn without the tile plate
        square(f"Square44x44Logo.targetsize-{s}.png", s)
        square(f"Square44x44Logo.targetsize-{s}_altform-unplated.png", s)
    wide = Image.new("RGBA", (310, 150), (0, 0, 0, 0))
    wide.paste(draw_icon(96), ((310 - 96) // 2, (150 - 96) // 2))
    wide.save(out / "Wide310x150Logo.png")
