#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from struct import unpack
from pathlib import Path

try:
    from PIL import Image, ImageChops  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    Image = None
    ImageChops = None


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def render_pages(pdf: Path, output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    prefix = output_dir / "page"
    command = ["pdftoppm", "-png", "-r", "144", str(pdf), str(prefix)]
    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "pdftoppm failed")
    return sorted(output_dir.glob("page-*.png"))


def read_png_size(path: Path) -> tuple[int | None, int | None]:
    try:
        with path.open("rb") as handle:
            header = handle.read(24)
        if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
            return None, None
        width, height = unpack(">II", header[16:24])
        return width, height
    except Exception:
        return None, None


def describe_pages(paths: list[Path]) -> list[dict]:
    pages: list[dict] = []
    for index, path in enumerate(paths, start=1):
        width, height = read_png_size(path)
        pages.append(
            {
                "page": index,
                "path": str(path),
                "sha256": sha256(path),
                "width_px": width,
                "height_px": height,
            }
        )
    return pages


def maybe_write_diff_image(left_page: Path, right_page: Path, output_dir: Path, page_number: int) -> str | None:
    if Image is None or ImageChops is None:
        return None
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        with Image.open(left_page) as left_image, Image.open(right_page) as right_image:
            if left_image.size != right_image.size:
                return None
            diff_image = ImageChops.difference(left_image.convert("RGBA"), right_image.convert("RGBA"))
            diff_path = output_dir / f"page-{page_number:04d}-diff.png"
            diff_image.save(diff_path)
            return str(diff_path)
    except Exception:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare two PDFs by binary hash and rasterized page hashes.")
    parser.add_argument("--left", required=True)
    parser.add_argument("--right", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--json-out")
    args = parser.parse_args()

    left = Path(args.left).resolve()
    right = Path(args.right).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    result = {
        "left_pdf": str(left),
        "right_pdf": str(right),
        "left_hash": None,
        "right_hash": None,
        "binary_equal": False,
        "left_page_count": 0,
        "right_page_count": 0,
        "left_render_dir": None,
        "right_render_dir": None,
        "diff_render_dir": None,
        "left_pages": [],
        "right_pages": [],
        "visual_equal": False,
        "visual_diff_pages": [],
        "visual_diff_images": [],
        "status": "ok",
        "error": None,
    }

    if not left.exists() or not right.exists():
        result["status"] = "missing_input"
        result["error"] = "One or both PDF inputs do not exist."
    else:
        try:
            result["left_hash"] = sha256(left)
            result["right_hash"] = sha256(right)
            result["binary_equal"] = result["left_hash"] == result["right_hash"]

            left_render_dir = output_dir / "left"
            right_render_dir = output_dir / "right"
            diff_render_dir = output_dir / "diff"
            left_pages = render_pages(left, left_render_dir)
            right_pages = render_pages(right, right_render_dir)
            left_pages_meta = describe_pages(left_pages)
            right_pages_meta = describe_pages(right_pages)

            result["left_page_count"] = len(left_pages)
            result["right_page_count"] = len(right_pages)
            result["left_render_dir"] = str(left_render_dir)
            result["right_render_dir"] = str(right_render_dir)
            result["diff_render_dir"] = str(diff_render_dir)
            result["left_pages"] = left_pages_meta
            result["right_pages"] = right_pages_meta

            if len(left_pages) == len(right_pages):
                diff_pages: list[int] = []
                diff_images: list[dict] = []
                for index, (left_page, right_page, left_meta, right_meta) in enumerate(
                    zip(left_pages, right_pages, left_pages_meta, right_pages_meta),
                    start=1,
                ):
                    if left_meta["sha256"] != right_meta["sha256"]:
                        diff_pages.append(index)
                        diff_path = maybe_write_diff_image(left_page, right_page, diff_render_dir, index)
                        diff_images.append({"page": index, "path": diff_path})
                result["visual_diff_pages"] = diff_pages
                result["visual_diff_images"] = diff_images
                result["visual_equal"] = not diff_pages
            else:
                result["status"] = "page_count_mismatch"
                result["visual_equal"] = False
        except Exception as exc:
            result["status"] = "error"
            result["error"] = str(exc)

    payload = json.dumps(result, ensure_ascii=False, indent=2)
    print(payload)

    if args.json_out:
        Path(args.json_out).write_text(payload + "\n", encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
