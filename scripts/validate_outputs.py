"""Structural acceptance plus a contact sheet; visual quality needs review."""
import argparse
import hashlib
import itertools
import json
from pathlib import Path

PASSES = ("basecolor", "normal", "depth", "roughness", "metallic")


def inspect(paths, height, width):
    import numpy as np
    from PIL import Image
    records = []
    arrays = []
    for path in paths:
        with Image.open(path) as img:
            img.load()
            if img.size != (width, height) or img.mode != "RGB":
                raise ValueError("Unexpected image size/mode: " + str(path))
            arr = np.asarray(img).copy()
        if not np.isfinite(arr).all() or arr.std() < 0.5:
            raise ValueError("Invalid or effectively constant output: " + str(path))
        records.append({"path": str(path), "size": path.stat().st_size,
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        "mean": float(arr.mean()), "std": float(arr.std()),
                        "shape": list(arr.shape)})
        arrays.append(arr)
    return records, arrays


def validate_inverse(root, height, width):
    files = []
    for label in PASSES:
        matches = list((root / "gbuffer_frames").rglob(f"*.{label}.jpg"))
        if len(matches) != 1:
            raise ValueError(f"Expected one {label} G-buffer, found {len(matches)}")
        files.extend(matches)
    return inspect(files, height, width)[0]


def validate_forward(root, height, width):
    import numpy as np
    files = []
    for index in range(3):
        matches = list((root / f"relit_frames_{index:04d}").rglob("*.jpg"))
        if len(matches) != 1:
            raise ValueError(f"Expected one image for HDR {index}, found {len(matches)}")
        files.extend(matches)
    records, arrays = inspect(files, height, width)
    differences = [{"pair": [a, b], "mean_abs_rgb_difference": float(np.mean(
        np.abs(arrays[a].astype(np.float32) - arrays[b].astype(np.float32))))}
        for a, b in itertools.combinations(range(3), 2)]
    if any(d["mean_abs_rgb_difference"] < 0.5 for d in differences):
        raise ValueError("HDR outputs are indistinguishable; inspect lighting path")
    return {"images": records, "differences": differences,
            "visual_acceptance": "pending human image review; statistics are structural checks"}


def contact_sheet(source, inverse, forward, target):
    from PIL import Image, ImageDraw
    paths = [("Official input", source)]
    for label in PASSES:
        paths.append((label, next((inverse / "gbuffer_frames").rglob(f"*.{label}.jpg"))))
    for index, name in enumerate(("Sunny Vondelpark", "Pink Sunrise", "Street Lamp")):
        paths.append((name, next((forward / f"relit_frames_{index:04d}").rglob("*.jpg"))))
    sheet = Image.new("RGB", (3 * 384, 3 * 244), "#20242c")
    draw = ImageDraw.Draw(sheet)
    for index, (label, path) in enumerate(paths):
        img = Image.open(path).convert("RGB")
        img.thumbnail((372, 210))
        x, y = (index % 3) * 384 + 6, (index // 3) * 244 + 6
        sheet.paste(img, (x, y + 22))
        draw.text((x, y), label, fill="white")
    sheet.save(target)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--inverse-dir", required=True, type=Path)
    p.add_argument("--forward-dir", type=Path)
    p.add_argument("--input", type=Path)
    p.add_argument("--height", type=int, default=704)
    p.add_argument("--width", type=int, default=1280)
    p.add_argument("--out", type=Path)
    args = p.parse_args()
    report = {"inverse": validate_inverse(args.inverse_dir, args.height, args.width)}
    if args.forward_dir:
        report["forward"] = validate_forward(args.forward_dir, args.height, args.width)
        if args.input and args.out:
            contact_sheet(args.input, args.inverse_dir, args.forward_dir, args.out.with_suffix(".png"))
    if args.out:
        args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
