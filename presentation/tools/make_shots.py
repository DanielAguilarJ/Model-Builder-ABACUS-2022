# -*- coding: utf-8 -*-
"""Frame the captured screenshots and the Abaqus renders for the slides.

Adds rounded corners, a hairline border and a soft drop shadow on a transparent
canvas, the way an application window is presented in a Keynote deck. The pixel
content itself is never retouched.
"""
from __future__ import annotations

import glob
import os

from PIL import Image, ImageDraw, ImageFilter

REPO = "/projects/sandbox/Model-Builder-ABACUS-2022"
LANG = os.environ.get("MB_LANG", "es")
SCREENS = ("/projects/sandbox/assets/screens" if LANG == "es"
           else "/projects/sandbox/assets/screens_%s" % LANG)
OUT = ("/projects/sandbox/assets/framed" if LANG == "es"
       else "/projects/sandbox/assets/framed_%s" % LANG)
os.makedirs(OUT, exist_ok=True)

RADIUS = 18
BORDER = (0, 0, 0, 26)
SHADOW_BLUR = 26
SHADOW_OFFSET = 16
SHADOW_ALPHA = 62
MARGIN = 60


def rounded_mask(size, radius):
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size[0] - 1, size[1] - 1],
                                           radius=radius, fill=255)
    return mask


def frame(image, radius=RADIUS, border=True):
    image = image.convert("RGBA")
    mask = rounded_mask(image.size, radius)
    rounded = Image.new("RGBA", image.size, (0, 0, 0, 0))
    rounded.paste(image, (0, 0), mask)
    if border:
        ImageDraw.Draw(rounded).rounded_rectangle(
            [0, 0, image.size[0] - 1, image.size[1] - 1], radius=radius,
            outline=BORDER, width=2)

    canvas = Image.new("RGBA",
                       (image.size[0] + MARGIN * 2, image.size[1] + MARGIN * 2),
                       (0, 0, 0, 0))
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        [MARGIN, MARGIN + SHADOW_OFFSET, MARGIN + image.size[0],
         MARGIN + image.size[1] + SHADOW_OFFSET],
        radius=radius, fill=(15, 18, 26, SHADOW_ALPHA))
    shadow = shadow.filter(ImageFilter.GaussianBlur(SHADOW_BLUR))
    canvas = Image.alpha_composite(canvas, shadow)
    canvas.paste(rounded, (MARGIN, MARGIN), rounded)
    return canvas


def trim_app_background(image, bg=(0xF1, 0xF5, 0xF9), border=18, keep=10,
                        margin=26, minimum=1030):
    """Cut the empty application background under a short tab.

    The last rows of the original window (its bottom frame edge) are appended
    back so the screenshot still looks like a closed window instead of a cut,
    and `minimum` keeps every capture in a narrow aspect-ratio band so the
    slides stay visually uniform.
    """
    rgb_image = image.convert("RGB")
    width, height = rgb_image.size
    pixels = rgb_image.load()
    last = 0
    for y in range(height - keep - 1, -1, -1):
        hits = 0
        for x in range(border, width - border, 3):
            pixel = pixels[x, y]
            if (abs(pixel[0] - bg[0]) > 6 or abs(pixel[1] - bg[1]) > 6 or
                    abs(pixel[2] - bg[2]) > 6):
                hits += 1
                if hits >= 3:
                    break
        if hits >= 3:
            last = y
            break
    cut = min(max(last + margin, minimum), height - keep)
    if height - cut < 60:
        return image
    top_part = image.crop((0, 0, width, cut))
    bottom_part = image.crop((0, height - keep, width, height))
    result = Image.new(image.mode, (width, cut + keep))
    result.paste(top_part, (0, 0))
    result.paste(bottom_part, (0, cut))
    return result


def trim_white(image, tolerance=248):
    """Crop the flat white margin Abaqus leaves around a viewport render."""
    grey = image.convert("L")
    mask = grey.point(lambda value: 0 if value >= tolerance else 255)
    box = mask.getbbox()
    if not box:
        return image
    pad = 12
    left = max(box[0] - pad, 0)
    upper = max(box[1] - pad, 0)
    right = min(box[2] + pad, image.size[0])
    lower = min(box[3] + pad, image.size[1])
    return image.crop((left, upper, right, lower))


def main():
    written = []
    for path in sorted(glob.glob(os.path.join(SCREENS, "gui_*.png"))):
        raw = Image.open(path)
        if raw.size[0] > 1500:
            # The modal dialog is grabbed from the root window; crop it back
            # to the application window so every capture is framed alike.
            raw = raw.crop((0, 0, 1500, min(1150, raw.size[1])))
        shot = trim_app_background(raw)
        framed = frame(shot)
        target = os.path.join(OUT, os.path.basename(path))
        framed.save(target)
        written.append((target, framed.size))

    renders = {
        "model_assembly_hex.png": "_v3test/V3_FULL_preview.png",
        "model_assembly_dense.png": "preview/KEY_FORM_B_preview.png",
        "model_notch_detail.png": "_v3test/V3_FULL_notch_mesh.png",
        "model_form_a.png": "preview/KEY_FORM_A_preview.png",
        "model_front.png": "_v3test/V3_FULL_preview_Front.png",
        "model_d50.png": "preview/FORM_A_D50_preview.png",
    }
    # A cropped detail of the front section: the refined element band around
    # the keyway is genuinely visible here, so the slide can point at it.
    section = Image.open(os.path.join(REPO, "preview/preview_front.png"))
    section = section.crop((432, 186, 1176, 800))
    frame(section, radius=14).save(os.path.join(OUT, "model_notch_section.png"))
    print("  %-34s cropped from preview/preview_front.png" %
          "model_notch_section.png")

    for name, relative in renders.items():
        source = os.path.join(REPO, relative)
        if not os.path.isfile(source):
            print("  missing render: %s" % relative)
            continue
        trimmed = trim_white(Image.open(source))
        framed = frame(trimmed, radius=14)
        target = os.path.join(OUT, name)
        framed.save(target)
        written.append((target, framed.size))

    for target, size in written:
        print("  %-34s %dx%d" % (os.path.basename(target), size[0], size[1]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
