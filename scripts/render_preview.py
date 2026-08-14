#!/usr/bin/env python3
"""Render a MOCKUP of how the lightning map sits in a Home Assistant card.

This does NOT contact Xweather. The map imagery and strike positions are
invented so the geometry and card layout can be checked offline. It is
watermarked accordingly so it cannot be mistaken for real weather data.

Layout, bounding box, and framing come from the integration's own map.py.
"""

from __future__ import annotations

import importlib.util
import math
import pathlib
import random

from PIL import Image, ImageDraw, ImageFont

HERE = pathlib.Path(__file__).parent
MAP_PY = HERE / "custom_components" / "xweather_lightning" / "map.py"

# Example location: the one used throughout the Xweather docs.
LAT, LON = 44.98, -93.27
RADIUS_KM = 50
WINDOW_MIN = 5
MAP_PX = 640

# Home Assistant default dark theme values.
BG = (17, 17, 17)
CARD = (28, 28, 30)
CARD_EDGE = (56, 56, 58)
TEXT = (255, 255, 255)
TEXT_DIM = (154, 154, 158)
ACCENT = (3, 169, 244)
AMBER = (255, 152, 0)
LAND = (38, 42, 48)
WATER = (26, 32, 40)
ROAD = (58, 62, 70)
BOUNDARY = (78, 84, 94)


def load_map_module():
    """Import the integration's map helpers."""
    spec = importlib.util.spec_from_file_location("xw_map", MAP_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def font(size: int, bold: bool = False):
    """Best-effort font lookup with a graceful fallback."""
    names = (
        ["DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"]
        if bold
        else ["DejaVuSans.ttf", "LiberationSans-Regular.ttf"]
    )
    for name in names:
        for root in ("/usr/share/fonts/truetype/dejavu/",
                     "/usr/share/fonts/truetype/liberation/", ""):
            try:
                return ImageFont.truetype(root + name, size)
            except OSError:
                continue
    return ImageFont.load_default()


def rounded(draw, box, radius, fill=None, outline=None, width=1):
    """Rounded rectangle helper."""
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def draw_bolt(draw, x, y, scale, colour):
    """A lightning bolt glyph, matching the -icons layer style."""
    pts = [(0, -10), (-4.5, 0.5), (-0.8, 0.5), (-3, 10), (5, -1.5), (0.8, -1.5), (3.5, -10)]
    draw.polygon(
        [(x + px * scale, y + py * scale) for px, py in pts],
        fill=colour,
        outline=(255, 255, 255),
    )


def render_map(size: int, strikes: list[tuple[float, float, str]]) -> Image.Image:
    """Draw a stand-in for the Raster Maps tile: base, boundaries, strikes."""
    img = Image.new("RGB", (size, size), LAND)
    d = ImageDraw.Draw(img, "RGBA")

    rng = random.Random(7)

    # A lake and a river, so the base layer reads as a real map.
    d.ellipse([size * 0.60, size * 0.12, size * 0.86, size * 0.34], fill=WATER)
    d.ellipse([size * 0.08, size * 0.68, size * 0.30, size * 0.80], fill=WATER)
    river = [(size * 0.72, size * 0.30)]
    for i in range(1, 14):
        river.append(
            (
                size * (0.72 - i * 0.035 + rng.uniform(-0.02, 0.02)),
                size * (0.30 + i * 0.045),
            )
        )
    d.line(river, fill=WATER, width=max(3, size // 140))

    # County grid (admin-dk / counties-dk layers).
    for i in range(1, 4):
        d.line([(size * i / 4, 0), (size * i / 4, size)], fill=BOUNDARY, width=1)
        d.line([(0, size * i / 4), (size, size * i / 4)], fill=BOUNDARY, width=1)

    # A couple of highways.
    d.line([(0, size * 0.58), (size, size * 0.44)], fill=ROAD, width=max(2, size // 220))
    d.line([(size * 0.38, 0), (size * 0.52, size)], fill=ROAD, width=max(2, size // 220))

    # Synthetic strikes, clustered into a storm cell.
    for fx, fy, kind in strikes:
        x, y = fx * size, fy * size
        if kind == "cg":
            d.ellipse(
                [x - size * 0.035, y - size * 0.035, x + size * 0.035, y + size * 0.035],
                fill=(255, 214, 0, 55),
            )
            draw_bolt(d, x, y, size / 430, (255, 214, 0))
        else:
            d.ellipse(
                [x - size * 0.026, y - size * 0.026, x + size * 0.026, y + size * 0.026],
                fill=(120, 190, 255, 45),
            )
            draw_bolt(d, x, y, size / 620, (140, 200, 255))

    # Attribution, as the real imagery carries.
    f = font(max(10, size // 52))
    d.text((10, size - 10), "Vaisala Xweather", font=f, fill=(190, 190, 190), anchor="ls")

    # Unmistakable mockup watermark.
    fw = font(max(13, size // 30), bold=True)
    label = "SIMULATED — NOT REAL WEATHER DATA"
    bbox = d.textbbox((0, 0), label, font=fw)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    wy = size * 0.86
    d.rectangle(
        [size / 2 - w / 2 - 12, wy - h / 2 - 8, size / 2 + w / 2 + 12, wy + h / 2 + 10],
        fill=(0, 0, 0, 165),
    )
    d.text((size / 2, wy), label, font=fw, fill=(255, 120, 120), anchor="mm")
    return img


def annotate_framing(img: Image.Image, xw) -> Image.Image:
    """Overlay the radius circle and the 10% padding ring."""
    size = img.width
    out = img.copy()
    d = ImageDraw.Draw(out, "RGBA")

    # The box spans radius * MAP_PADDING in each direction from centre, so the
    # search radius occupies 1/MAP_PADDING of the half-width.
    half = size / 2
    r_search = half / xw.MAP_PADDING
    cx = cy = half

    d.ellipse([cx - half, cy - half, cx + half, cy + half],
              outline=(255, 255, 255, 90), width=2)
    d.ellipse([cx - r_search, cy - r_search, cx + r_search, cy + r_search],
              outline=(ACCENT[0], ACCENT[1], ACCENT[2], 220), width=3)

    # Centre marker.
    d.ellipse([cx - 7, cy - 7, cx + 7, cy + 7], fill=ACCENT, outline=(255, 255, 255), width=2)

    f = font(max(11, size // 46), bold=True)
    d.text((cx, cy - r_search + 10), f"search radius {RADIUS_KM} km",
           font=f, fill=ACCENT, anchor="ma")
    d.text((cx, 12), f"image edge = radius + {(xw.MAP_PADDING - 1) * 100:.0f}%  "
                     f"({RADIUS_KM * xw.MAP_PADDING:.0f} km)",
           font=f, fill=(255, 255, 255, 210), anchor="ma")
    # centre label, offset so it does not sit under the marker
    d.text((cx + 14, cy + 4), "your coordinates", font=font(max(10, size // 54)),
           fill=(255, 255, 255, 200), anchor="lm")
    return out


def card(map_img: Image.Image, title: str, subtitle: str, footer: str) -> Image.Image:
    """Wrap a map in a Home Assistant style picture-entity card."""
    pad, head, foot = 16, 54, 40
    w = map_img.width + pad * 2
    h = map_img.height + head + foot + pad
    img = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(img)

    rounded(d, [6, 6, w - 6, h - 6], 14, fill=CARD, outline=CARD_EDGE, width=1)
    d.text((pad + 4, 22), title, font=font(17, bold=True), fill=TEXT)
    d.text((w - pad - 4, 24), subtitle, font=font(13), fill=TEXT_DIM, anchor="ra")

    img.paste(map_img, (pad, head))
    d.text((pad + 4, head + map_img.height + 16), footer, font=font(12), fill=TEXT_DIM)
    return img


def main() -> None:
    """Render the mockups."""
    xw = load_map_module()
    south, west, north, east = xw.bounding_box(LAT, LON, RADIUS_KM)
    layers = xw.build_layers(WINDOW_MIN, "icons")

    rng = random.Random(11)
    storm = []
    for _ in range(22):
        angle, dist = rng.uniform(0, math.tau), rng.uniform(0, 0.16)
        storm.append(
            (0.36 + math.cos(angle) * dist, 0.40 + math.sin(angle) * dist * 0.8,
             "cg" if rng.random() < 0.55 else "ic")
        )
    for _ in range(8):
        storm.append((rng.uniform(0.15, 0.85), rng.uniform(0.15, 0.85),
                      "ic" if rng.random() < 0.7 else "cg"))

    active = render_map(MAP_PX, storm)
    quiet = render_map(MAP_PX, [])

    card(
        active,
        "Lightning map",
        "Home Lightning",
        f"{layers}   |   {MAP_PX}x{MAP_PX}   |   bbox {south}, {west}, {north}, {east}",
    ).save(HERE / "preview-active.png")

    card(
        quiet,
        "Lightning map",
        "Home Lightning  ·  Clear",
        "Quiet sky: the entity holds its last render and makes no new requests.",
    ).save(HERE / "preview-clear.png")

    card(
        annotate_framing(active, xw),
        "Lightning map — framing",
        f"centre {LAT}, {LON}",
        f"Blue = {RADIUS_KM} km search radius.  White = image edge at "
        f"radius + {(xw.MAP_PADDING - 1) * 100:.0f}%.",
    ).save(HERE / "preview-framing.png")

    print("Wrote preview-active.png, preview-clear.png, preview-framing.png")


if __name__ == "__main__":
    main()
