#!/usr/bin/env python3
"""Resize/compress speaker photos to a sane size for the site.

Speaker photos should be roughly square and ~1080px on the long side
(see CLAUDE.md). This script downscales oversized uploads in place
(or to an output path) without upscaling smaller images.

Usage:
    python3 scripts/compress_photo.py static/images/speakers/photo.png
    python3 scripts/compress_photo.py photo.png --max-size 800
    python3 scripts/compress_photo.py photo.png -o photo-resized.png
"""

import argparse
import sys
from pathlib import Path

from PIL import Image

DEFAULT_MAX_SIZE = 1080


def compress(src: Path, dst: Path, max_size: int) -> None:
    before = src.stat().st_size
    im = Image.open(src)
    im = im.convert("RGBA" if im.mode in ("RGBA", "LA", "P") else "RGB")

    if max(im.size) > max_size:
        im.thumbnail((max_size, max_size), Image.LANCZOS)

    save_kwargs = {"optimize": True}
    if dst.suffix.lower() in (".jpg", ".jpeg"):
        save_kwargs["quality"] = 85
        if im.mode == "RGBA":
            im = im.convert("RGB")

    im.save(dst, **save_kwargs)
    after = dst.stat().st_size
    print(
        f"{src.name}: {im.width}x{im.height}, "
        f"{before / 1024:.0f}KB -> {after / 1024:.0f}KB"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("images", nargs="+", type=Path, help="Path(s) to image file(s)")
    parser.add_argument(
        "-o", "--output", type=Path,
        help="Output path (only valid with a single input file). Defaults to overwriting the input.",
    )
    parser.add_argument(
        "--max-size", type=int, default=DEFAULT_MAX_SIZE,
        help=f"Max width/height in pixels (default: {DEFAULT_MAX_SIZE})",
    )
    args = parser.parse_args()

    if args.output and len(args.images) > 1:
        print("ERROR: --output can only be used with a single input file", file=sys.stderr)
        sys.exit(1)

    for src in args.images:
        if not src.exists():
            print(f"ERROR: {src} not found", file=sys.stderr)
            sys.exit(1)
        dst = args.output or src
        compress(src, dst, args.max_size)


if __name__ == "__main__":
    main()
