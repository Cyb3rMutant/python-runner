import io

from PIL import Image, ImageColor

_HEX_DIGITS = set("0123456789abcdefABCDEF")


def hex_to_rgba(s: str) -> tuple[int, int, int, int]:
    """Accepts a CSS colour name ("red"), or hex in 3/4/6/8-digit form,
    with or without a leading '#' ("f00", "#f00", "ff0000", "#ff0000ff")."""
    s = s.strip()
    if s.lower() in ("transparent", "none"):
        return (0, 0, 0, 0)

    body = s.lstrip("#")
    is_hex = len(body) in (3, 4, 6, 8) and all(c in _HEX_DIGITS for c in body)
    candidate = f"#{body}" if is_hex else s

    try:
        r, g, b, a = ImageColor.getcolor(candidate, "RGBA")
    except ValueError as exc:
        raise ValueError(f"bad color: {s!r}") from exc

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


def restyle(img: Image.Image, fg: str, bg: str, threshold: int) -> Image.Image:
    mask = module_mask(img, threshold)
    fg_layer = Image.new("RGBA", img.size, hex_to_rgba(fg))

    out = Image.new("RGBA", img.size, hex_to_rgba(bg))
    out.paste(fg_layer, (0, 0), mask)
    return out


def run(
    file: bytes | None = None,
    *,
    data: str | None = None,
    fg: str = "#000000",
    bg: str = "#ffffff",
    threshold: str = "128",
):
    if bool(file) == bool(data):
        raise ValueError("provide exactly one of: an image `file`, or `data` text to encode")

    img = Image.open(io.BytesIO(file)).convert("RGBA") if file else generate_qr(data)
    out = restyle(img, fg, bg, int(threshold))

    buffer = io.BytesIO()
    out.save(buffer, format="PNG")
    return buffer.getvalue(), "png"
