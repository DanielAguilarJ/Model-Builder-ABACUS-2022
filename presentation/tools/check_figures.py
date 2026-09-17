# -*- coding: utf-8 -*-
"""Fail if any rendered figure has content running off the bottom edge.

Diagram cards intentionally span the full width, so touching the right edge is
by design; content touching the bottom row means a layout overflowed.
"""
from __future__ import annotations

import glob
import os
import sys

from PIL import Image


def check(folder):
    clipped = []
    for path in sorted(glob.glob(os.path.join(folder, "*.png"))):
        image = Image.open(path).convert("RGBA")
        width, height = image.size
        box = image.getchannel("A").getbbox()
        if not box:
            continue
        bottom_margin = height - box[3]
        state = "CLIPPED" if bottom_margin <= 0 else "ok"
        if bottom_margin <= 0:
            clipped.append(os.path.basename(path))
        print("  %-8s %-26s bottom margin %4d px" %
              (state, os.path.basename(path), bottom_margin))
    return clipped


def main():
    failures = []
    for folder, label in ((sys.argv[1] if len(sys.argv) > 1 else "diagrams",
                           "figures"),):
        print("=== %s: %s ===" % (label, folder))
        failures.extend(check(folder))
    if failures:
        print("\n%d figure(s) clipped: %s" % (len(failures), ", ".join(failures)))
        return 1
    print("\nno figure is clipped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
