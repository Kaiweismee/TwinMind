"""
去除「分身有術」Logo 白底 → 透明 PNG

用法：
  cd ~/Desktop/digital_twin_project
  ./venv/bin/python scripts/remove_icon_bg.py
  ./venv/bin/python scripts/remove_icon_bg.py --input web/static/brand-icon-white-bg.png
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
DEFAULT = ROOT / "web/static/brand-icon.png"
WHITE_THRESH = 235


def remove_white_bg(img: Image.Image) -> Image.Image:
    img = img.convert("RGBA")
    px = img.load()
    w, h = img.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if r >= WHITE_THRESH and g >= WHITE_THRESH and b >= WHITE_THRESH:
                px[x, y] = (r, g, b, 0)
            elif r > 200 and g > 200 and b > 200 and max(r, g, b) - min(r, g, b) < 30:
                px[x, y] = (r, g, b, 0)
    bbox = img.getbbox()
    if bbox:
        img = img.crop(bbox)
        pad = 8
        cw, ch = img.size
        canvas = Image.new("RGBA", (cw + 2 * pad, ch + 2 * pad), (0, 0, 0, 0))
        canvas.paste(img, (pad, pad), img)
        img = canvas
    return img


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT)
    parser.add_argument("--no-backup", action="store_true")
    args = parser.parse_args()

    src = args.input.resolve()
    if not src.exists():
        raise SystemExit(f"找不到：{src}")

    backup = src.with_name(src.stem + "-white-bg" + src.suffix)
    if not args.no_backup and not backup.exists():
        shutil.copy2(src, backup)
        print(f"已備份：{backup}")

    out = remove_white_bg(Image.open(src))
    out.save(src, "PNG", optimize=True)

    static = src.parent
    for size, name in [(32, "favicon-32.png"), (192, "icon-192.png")]:
        small = out.copy()
        small.thumbnail((size, size), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        ox = (size - canvas.width) // 2
        oy = (size - canvas.height) // 2
        canvas.paste(small, ((size - small.width) // 2, (size - small.height) // 2), small)
        canvas.save(static / name, "PNG")

    print(f"完成：{src}（透明背景）")


if __name__ == "__main__":
    main()
