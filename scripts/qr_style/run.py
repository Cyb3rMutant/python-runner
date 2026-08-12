import io

from PIL import Image


def hex_to_rgba(s: str) -> tuple[int, int, int, int]:
    s = s.strip()
    if s.lower() in ("transparent", "none"):
        return (0, 0, 0, 0)
    s = s.lstrip("#")
    if len(s) == 6:
        s += "ff"
    if len(s) != 8:
        raise ValueError(f"bad color: {s!r}")
    r, g, b, a = (int(s[i : i + 2], 16) for i in (0, 2, 4, 6))
    return (r, g, b, a)


def generate_qr(data: str) -> Image.Image:
    import qrcode

    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    return img.convert("RGBA")


def module_mask(img: Image.Image, threshold: int) -> Image.Image:
    """Return an 'L' mask: 255 where a dark QR module is, else 0."""
    gray = img.convert("L")
    return gray.point(lambda p: 255 if p < threshold else 0)


def gradient_layer(size, c1, c2, direction="diagonal") -> Image.Image:
    w, h = size
    layer = Image.new("RGBA", size)
    px = layer.load()
    for y in range(h):
        for x in range(w):
            if direction == "horizontal":
                t = x / max(w - 1, 1)
            elif direction == "vertical":
                t = y / max(h - 1, 1)
            else:  # diagonal
                t = (x + y) / max(w + h - 2, 1)
            px[x, y] = tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(4))
    return layer


def restyle(img: Image.Image, fg: str, fg2: str | None, bg: str, direction: str, threshold: int) -> Image.Image:
    mask = module_mask(img, threshold)

    if fg2:
        fg_layer = gradient_layer(img.size, hex_to_rgba(fg), hex_to_rgba(fg2), direction)
    else:
        fg_layer = Image.new("RGBA", img.size, hex_to_rgba(fg))

    out = Image.new("RGBA", img.size, hex_to_rgba(bg))
    out.paste(fg_layer, (0, 0), mask)
    return out


def run(
    file: bytes | None = None,
    *,
    data: str | None = None,
    fg: str = "#000000",
    fg2: str | None = None,
    bg: str = "#ffffff",
    direction: str = "diagonal",
    threshold: str = "128",
):
    if bool(file) == bool(data):
        raise ValueError("provide exactly one of: an image `file`, or `data` text to encode")

    img = Image.open(io.BytesIO(file)).convert("RGBA") if file else generate_qr(data)
    out = restyle(img, fg, fg2 or None, bg, direction, int(threshold))

    buffer = io.BytesIO()
    out.save(buffer, format="PNG")
    return buffer.getvalue(), "png"
