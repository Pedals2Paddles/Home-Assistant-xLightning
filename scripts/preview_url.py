#!/usr/bin/env python3
"""Print the exact Raster Maps URLs this integration would request.

Uses the integration's own map.py, so what it prints is what Home Assistant
would fetch — no guessing.

Usage:
    python3 preview_url.py --lat 44.98 --lon -93.27 \
        --id abc123 --secret def456

    python3 preview_url.py --lat 44.98 --lon -93.27 --radius 50 \
        --window 5 --size 640 --style icons --frames 4 \
        --id abc123 --secret def456

Note: Raster Maps joins the two credentials into ONE path segment separated by
an underscore, unlike the Weather API which passes them as query parameters.

Paste the resulting URL into a browser to see the real image.
"""

from __future__ import annotations

import argparse
import importlib.util
import pathlib
import sys

HERE = pathlib.Path(__file__).parent
MAP_PY = HERE / "custom_components" / "xweather_lightning" / "map.py"


def load_map_module():
    """Import map.py directly, without pulling in Home Assistant."""
    if not MAP_PY.exists():
        sys.exit(f"Could not find {MAP_PY}. Run this from the repo root.")
    spec = importlib.util.spec_from_file_location("xw_map", MAP_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    """Parse arguments and print the URLs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lat", type=float, required=True, help="Latitude")
    parser.add_argument("--lon", type=float, required=True, help="Longitude")
    parser.add_argument("--radius", type=int, default=50, help="Search radius in km")
    parser.add_argument("--window", type=int, default=5, help="Lookback in minutes")
    parser.add_argument("--size", type=int, default=640, help="Square edge in pixels")
    parser.add_argument(
        "--style", default="icons", choices=["icons", "circles", "radar"]
    )
    parser.add_argument(
        "--frames", type=int, default=1, help="0 no map, 1 still, N animation frames"
    )
    parser.add_argument("--id", default="CLIENTID", help="Xweather client ID")
    parser.add_argument("--secret", default="SECRETKEY", help="Xweather secret key")
    args = parser.parse_args()

    xw = load_map_module()

    south, west, north, east = xw.bounding_box(args.lat, args.lon, args.radius)
    layers = xw.build_layers(args.window, args.style)

    print(f"Centre           {args.lat}, {args.lon}")
    print(f"Search radius    {args.radius} km")
    print(
        f"Framed to        {args.radius * xw.MAP_PADDING:.1f} km "
        f"(radius + {(xw.MAP_PADDING - 1) * 100:.0f}%)"
    )
    print(f"Bounding box     S {south}  W {west}  N {north}  E {east}")
    print(f"Layers           {layers}")
    print(f"Image            {args.size}x{args.size}")

    if args.frames <= 0:
        print("\nFrames is 0, so no image entity would be created.")
        return

    offsets = xw.frame_offsets(args.frames, 5)
    print(f"Frames           {args.frames}  ->  {', '.join(offsets)}")
    print(f"Cost per render  {len(offsets)} request(s), ~{len(offsets) * 10} units\n")

    for index, offset in enumerate(offsets, start=1):
        url = xw.static_map_url(
            client_id=args.id,
            client_secret=args.secret,
            latitude=args.lat,
            longitude=args.lon,
            radius_km=args.radius,
            window_minutes=args.window,
            size=args.size,
            style=args.style,
            offset=offset,
        )
        label = f"Frame {index}/{len(offsets)} ({offset})"
        print(f"{label}\n{url}\n")


if __name__ == "__main__":
    main()
