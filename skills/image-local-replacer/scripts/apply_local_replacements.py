#!/usr/bin/env python3
"""Apply deterministic local replacements to bitmap images."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any, Iterable

from PIL import Image, ImageColor, ImageDraw, ImageFont


DEFAULT_RED_THRESHOLD = {
    "r_min": 120,
    "g_max": 120,
    "b_max": 120,
    "delta": 40,
}


def parse_color(value: Any) -> tuple[int, int, int]:
    if isinstance(value, str):
        rgb = ImageColor.getrgb(value)
        return int(rgb[0]), int(rgb[1]), int(rgb[2])
    if isinstance(value, list) and len(value) >= 3:
        return int(value[0]), int(value[1]), int(value[2])
    raise ValueError(f"Invalid color value: {value!r}")


def clamp_box(box: Iterable[int], width: int, height: int, padding: int = 0) -> tuple[int, int, int, int]:
    left, top, right, bottom = [int(v) for v in box]
    return (
        max(0, left - padding),
        max(0, top - padding),
        min(width, right + padding),
        min(height, bottom + padding),
    )


def sample_background(image: Image.Image, box: tuple[int, int, int, int]) -> tuple[int, int, int]:
    width, height = image.size
    left, top, right, bottom = box
    outer = (
        max(0, left - 6),
        max(0, top - 6),
        min(width, right + 6),
        min(height, bottom + 6),
    )

    pixels: list[tuple[int, int, int]] = []
    rgb_image = image.convert("RGB")
    for y in range(outer[1], outer[3]):
        for x in range(outer[0], outer[2]):
            in_inner = left <= x < right and top <= y < bottom
            if not in_inner:
                pixels.append(rgb_image.getpixel((x, y)))

    if not pixels:
        return 255, 255, 255

    channels = zip(*pixels)
    return tuple(int(statistics.median(channel)) for channel in channels)  # type: ignore[return-value]


def load_font(font_path: str | None, font_size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = []
    if font_path:
        candidates.append(font_path)
    candidates.extend(
        [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/Library/Fonts/Arial Bold.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
        ]
    )

    for candidate in candidates:
        path = Path(candidate).expanduser()
        if path.exists():
            return ImageFont.truetype(str(path), font_size)

    return ImageFont.load_default()


def merge_options(defaults: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    merged = dict(defaults)
    merged.update(item)
    return merged


def output_path(input_root: Path, file_name: str, output_dir: Path | None, overwrite: bool) -> Path:
    source = input_root / file_name
    if overwrite:
        return source
    if output_dir is None:
        raise ValueError("Either --overwrite or --output-dir is required.")
    return output_dir / file_name


def apply_replacements(input_root: Path, config: dict[str, Any], output_dir: Path | None, overwrite: bool) -> None:
    defaults = config.get("default", {})
    items = config.get("items", [])
    if not isinstance(items, list) or not items:
        raise ValueError("Config must contain a non-empty items list.")

    for item in items:
        options = merge_options(defaults, item)
        file_name = options["file"]
        source_path = input_root / file_name
        target_path = output_path(input_root, file_name, output_dir, overwrite)
        target_path.parent.mkdir(parents=True, exist_ok=True)

        with Image.open(source_path) as original:
            image = original.convert("RGBA")
            width, height = image.size
            cover = clamp_box(options["cover"], width, height, int(options.get("padding", 0)))
            background = parse_color(options["background"]) if "background" in options else sample_background(image, cover)
            draw = ImageDraw.Draw(image)
            draw.rectangle(cover, fill=background + (255,))

            text_value = options.get("text", options.get("new"))
            if text_value is not None:
                text_xy = options.get("text_xy")
                if not isinstance(text_xy, list):
                    raise ValueError(f"Text replacement for {file_name} requires text_xy.")
                text_x, text_y = [int(v) for v in text_xy]
                fill = parse_color(options.get("fill", "#d71920"))
                font = load_font(options.get("font"), int(options.get("font_size", 24)))
                stroke_width = int(options.get("stroke_width", 0))
                stroke_fill = parse_color(options.get("stroke_fill", options.get("fill", "#d71920")))
                draw.text(
                    (text_x, text_y),
                    str(text_value),
                    fill=fill + (255,),
                    font=font,
                    stroke_width=stroke_width,
                    stroke_fill=stroke_fill + (255,),
                )

            if original.mode == "RGBA":
                result = image
            else:
                result = image.convert(original.mode)
            result.save(target_path)

        description = options.get("description", "")
        print(f"OUTPUT: {target_path.resolve()} {description}".rstrip())


def make_red_masks(input_root: Path, config: dict[str, Any], mask_dir: Path) -> None:
    thresholds = dict(DEFAULT_RED_THRESHOLD)
    thresholds.update(config.get("red_threshold", {}))
    files = sorted({item["file"] for item in config.get("items", [])})
    mask_dir.mkdir(parents=True, exist_ok=True)

    for file_name in files:
        source_path = input_root / file_name
        with Image.open(source_path) as original:
            rgb_image = original.convert("RGB")
            mask = Image.new("RGB", rgb_image.size, "white")
            pixels = rgb_image.load()
            mask_pixels = mask.load()
            width, height = rgb_image.size
            for y in range(height):
                for x in range(width):
                    red, green, blue = pixels[x, y]
                    is_red = (
                        red >= thresholds["r_min"]
                        and green <= thresholds["g_max"]
                        and blue <= thresholds["b_max"]
                        and red - max(green, blue) >= thresholds["delta"]
                    )
                    if is_red:
                        mask_pixels[x, y] = (255, 0, 0)
            target = mask_dir / file_name
            target.parent.mkdir(parents=True, exist_ok=True)
            mask.save(target)
            print(f"MASK: {target.resolve()}")


def read_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("Config root must be a JSON object.")
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply local bitmap replacements with Pillow.")
    parser.add_argument("input_root", help="Directory containing source images.")
    parser.add_argument("config", help="JSON config describing local cover boxes and optional text.")
    parser.add_argument("-o", "--output-dir", help="Directory for edited images. Keeps original file names.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite source images in place.")
    parser.add_argument("--red-mask-dir", help="Optional directory for red-pixel mask previews.")
    args = parser.parse_args()

    if args.overwrite and args.output_dir:
        parser.error("--overwrite and --output-dir are mutually exclusive.")
    if not args.overwrite and not args.output_dir and not args.red_mask_dir:
        parser.error("Use --output-dir, --overwrite, or --red-mask-dir.")

    input_root = Path(args.input_root)
    config = read_config(Path(args.config))

    if args.red_mask_dir:
        make_red_masks(input_root, config, Path(args.red_mask_dir))
    if args.output_dir or args.overwrite:
        apply_replacements(input_root, config, Path(args.output_dir) if args.output_dir else None, args.overwrite)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
