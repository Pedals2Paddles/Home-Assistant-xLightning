"""Generate Home Assistant brands artwork from the source logo.

Home Assistant does not read branding from custom_components/. The frontend
fetches it from brands.home-assistant.io, so these files exist to be submitted
to https://github.com/home-assistant/brands under
custom_integrations/xweather_lightning/.

Target sizes (verify against the brands repo README before opening the PR):
  icon.png      square, 256x256
  icon@2x.png   square, 512x512
  logo.png      max 512 wide, max 256 tall
  logo@2x.png   max 1024 wide, max 512 tall

All are trimmed to the alpha bounding box, transparent, and optimised.
"""

from __future__ import annotations

import pathlib
import sys

from PIL import Image

SOURCE = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else None
OUT = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else pathlib.Path("brands")


def trimmed(path: pathlib.Path) -> Image.Image:
    """Load the source and crop to its alpha bounding box."""
    img = Image.open(path).convert("RGBA")
    box = img.getbbox()
    if box is None:
        raise SystemExit("Source image is fully transparent")
    return img.crop(box)


def square(img: Image.Image, edge: int) -> Image.Image:
    """Fit onto a transparent square canvas without distorting the aspect."""
    scale = min(edge / img.width, edge / img.height)
    resized = img.resize(
        (max(1, round(img.width * scale)), max(1, round(img.height * scale))),
        Image.LANCZOS,
    )
    canvas = Image.new("RGBA", (edge, edge), (0, 0, 0, 0))
    canvas.paste(
        resized,
        ((edge - resized.width) // 2, (edge - resized.height) // 2),
        resized,
    )
    return canvas


def bounded(img: Image.Image, max_w: int, max_h: int) -> Image.Image:
    """Scale to fit within the bounds, preserving aspect. No padding."""
    scale = min(max_w / img.width, max_h / img.height)
    return img.resize(
        (max(1, round(img.width * scale)), max(1, round(img.height * scale))),
        Image.LANCZOS,
    )


def preview(img: Image.Image, background: tuple[int, int, int]) -> Image.Image:
    """Composite onto a solid background to check for edge fringing."""
    canvas = Image.new("RGBA", img.size, (*background, 255))
    return Image.alpha_composite(canvas, img).convert("RGB")


def main() -> None:
    """Write every brands asset plus dark and light previews."""
    if SOURCE is None or not SOURCE.exists():
        raise SystemExit("Usage: make_brand_assets.py <source.png> [outdir]")

    OUT.mkdir(parents=True, exist_ok=True)
    src = trimmed(SOURCE)
    print(f"source trimmed to {src.width}x{src.height}")

    assets = {
        "icon.png": square(src, 256),
        "icon@2x.png": square(src, 512),
        "logo.png": bounded(src, 512, 256),
        "logo@2x.png": bounded(src, 1024, 512),
    }

    for name, img in assets.items():
        path = OUT / name
        img.save(path, "PNG", optimize=True)
        has_alpha = img.getchannel("A").getextrema()[0] < 255
        print(
            f"  {name:<12} {img.width:>4}x{img.height:<4} "
            f"{path.stat().st_size / 1024:>6.1f} KB  "
            f"transparency: {'yes' if has_alpha else 'NO'}"
        )

    # Previews so fringing on HA's dark default theme is visible before a PR.
    preview(assets["icon@2x.png"], (17, 17, 17)).save(OUT / "preview-dark.png")
    preview(assets["icon@2x.png"], (250, 250, 250)).save(OUT / "preview-light.png")
    print("  previews: preview-dark.png, preview-light.png")


if __name__ == "__main__":
    main()
