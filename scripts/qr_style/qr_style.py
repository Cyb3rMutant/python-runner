#!/usr/bin/env python3
"""Restyle QR codes: recolor, add transparency, two-tone modules, gradients.

Works on an existing QR code image (assumes black modules on a white/plain
background) or generates a fresh one from data.

Examples:
  # Recolor an existing QR: blue modules, transparent background
  python qr_style.py -i qr.png -o out.png --fg "#1a5fb4" --bg transparent

  # Two-color modules via a diagonal gradient, generated fresh from a URL
  python qr_style.py --data "https://example.com" -o out.png \\
      --fg "#ff0000" --fg2 "#0000ff" --bg transparent

  # Solid two-tone (dark background, light modules)
  python qr_style.py -i qr.png -o out.png --fg "#ffffff" --bg "#111111"
"""
import argparse
import sys

from PIL import Image


def hex_to_rgba(s: str) -> tuple[int, int, int, int]:
    s = s.strip()
    if s.lower() in ("transparent", "none"):
        return (0, 0, 0, 0)
    s = s.lstrip("#")
    if len(s) == 6:
        s += "ff"
    if len(s) != 8:
        raise argparse.ArgumentTypeError(f"bad color: {s!r}")
    r, g, b, a = (int(s[i : i + 2], 16) for i in (0, 2, 4, 6))
    return (r, g, b, a)


def load_or_generate(args) -> Image.Image:
    if args.input:
        return Image.open(args.input).convert("RGBA")

    import qrcode

    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(args.data)
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


def restyle(img: Image.Image, args) -> Image.Image:
    mask = module_mask(img, args.threshold)

    if args.fg2:
        fg_layer = gradient_layer(img.size, hex_to_rgba(args.fg), hex_to_rgba(args.fg2), args.direction)
    else:
        fg_layer = Image.new("RGBA", img.size, hex_to_rgba(args.fg))

    bg_rgba = hex_to_rgba(args.bg)
    out = Image.new("RGBA", img.size, bg_rgba)
    out.paste(fg_layer, (0, 0), mask)
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("-i", "--input", help="existing QR code image to restyle")
    src.add_argument("--data", help="text/URL to encode into a fresh QR code")

    p.add_argument("-o", "--output", required=True, help="output image path")
    p.add_argument("--fg", default="#000000", help="module color (hex, or 'transparent')")
    p.add_argument("--fg2", default=None, help="second module color; makes a gradient with --fg")
    p.add_argument("--bg", default="#ffffff", help="background color (hex, or 'transparent')")
    p.add_argument(
        "--direction",
        choices=["horizontal", "vertical", "diagonal"],
        default="diagonal",
        help="gradient direction when --fg2 is set",
    )
    p.add_argument(
        "--threshold",
        type=int,
        default=128,
        help="grayscale cutoff (0-255) below which a pixel counts as a module (default 128)",
    )
    args = p.parse_args()

    img = load_or_generate(args)
    out = restyle(img, args)
    out.save(args.output)
    print(f"wrote {args.output} ({out.size[0]}x{out.size[1]}, mode={out.mode})")


if __name__ == "__main__":
    sys.exit(main())
