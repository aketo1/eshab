"""Reading designed QR codes: rounded finder squares, dots or blobs instead of
plain squares. OpenCV finds such a code but cannot decode it, so it is drawn
again as a plain code: the three finder squares fix the grid, every module is
read at its centre, the parts every code shares (finders, timing, alignment)
are drawn exactly, and OpenCV decodes the clean copy.
"""
from __future__ import annotations

import numpy as np

#: Centres of the alignment patterns, by version (version 1 has none).
ALIGNMENT = {2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34], 7: [6, 22, 38], 8: [6, 24, 42],
             9: [6, 26, 46], 10: [6, 28, 50], 11: [6, 30, 54], 12: [6, 32, 58], 13: [6, 34, 62]}


def _finders(ink):
    """Nested squares (a dark ring around a light ring around a dark core): (x, y, size)."""
    import cv2

    contours, hierarchy = cv2.findContours(255 - ink, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    if hierarchy is None:
        return []
    hierarchy = hierarchy[0]
    found = []
    for index, contour in enumerate(contours):
        hole = hierarchy[index][2]
        if hole < 0 or hierarchy[hole][2] < 0:
            continue
        x, y, w, h = cv2.boundingRect(contour)
        if w < 14 or h < 14 or not 0.75 < w / h < 1.33:
            continue
        _, _, core_w, _ = cv2.boundingRect(contours[hierarchy[hole][2]])
        if not 0.25 < core_w / w < 0.6:        # the core is 3 of the finder's 7 modules
            continue
        found.append((x + w / 2, y + h / 2, (w + h) / 2))
    return found[:40]


def _corner_triples(found):
    """Three finders that make a code's corner (similar sizes, a right angle), best first."""
    triples = []
    for i, a in enumerate(found):
        for j, b in enumerate(found):
            for k, c in enumerate(found):
                if len({i, j, k}) < 3:
                    continue
                sizes = (a[2], b[2], c[2])
                if max(sizes) > 1.4 * min(sizes):
                    continue
                pa, pb, pc = np.array(a[:2]), np.array(b[:2]), np.array(c[:2])
                ab, ac = pb - pa, pc - pa
                lb, lc = float(np.hypot(*ab)), float(np.hypot(*ac))
                if lb < 2 * min(sizes) or abs(lb - lc) > 0.15 * max(lb, lc):
                    continue
                cosine = abs(float(ab @ ac)) / (lb * lc)
                if cosine > 0.15 or ab[0] * ac[1] - ab[1] * ac[0] < 0:
                    continue
                triples.append((cosine + abs(lb - lc) / max(lb, lc), pa, pb, pc, sum(sizes) / 3))
    return sorted(triples, key=lambda t: t[0])


def _canonical(grid, modules: int):
    """Draw the parts every code has exactly as the standard draws them."""
    for top, left in ((0, 0), (0, modules - 7), (modules - 7, 0)):
        for r in range(-1, 8):
            for c in range(-1, 8):
                row, col = top + r, left + c
                if 0 <= row < modules and 0 <= col < modules:
                    ring = max(abs(r - 3), abs(c - 3))
                    grid[row, col] = 1 if ring in (0, 1, 3) else 0
    for i in range(8, modules - 8):
        grid[6, i] = grid[i, 6] = 1 if i % 2 == 0 else 0
    centres = ALIGNMENT.get((modules - 17) // 4, [])
    for row in centres:
        for col in centres:
            if (row, col) in ((6, 6), (6, centres[-1]), (centres[-1], 6)):
                continue
            for r in range(-2, 3):
                for c in range(-2, 3):
                    grid[row + r, col + c] = 1 if max(abs(r), abs(c)) in (0, 2) else 0
    return grid


def _decode_grid(grid, detector) -> str:
    modules = grid.shape[0]
    scale, quiet = 10, 4
    picture = np.full(((modules + 2 * quiet) * scale,) * 2, 255, np.uint8)
    picture[quiet * scale:(quiet + modules) * scale, quiet * scale:(quiet + modules) * scale] = \
        np.kron((1 - grid) * 255, np.ones((scale, scale))).astype(np.uint8)
    text, _, _ = detector.detectAndDecode(picture)
    return text or ""


def _read(gray, detector) -> list[str]:
    import cv2

    results: list[str] = []
    variants = [cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1],
                cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 51, 10)]
    for ink in variants:
        for _, tl, tr, bl, size in _corner_triples(_finders(ink))[:6]:
            module = size / 7
            if module < 1.5:
                continue
            estimate = (float(np.hypot(*(tr - tl))) / module + 7 - 17) / 4
            versions = sorted({v for v in (round(estimate) + d for d in (0, -1, 1, -2, 2)) if 1 <= v <= 13},
                              key=lambda v: abs(v - estimate))
            for version in versions:
                modules = 17 + 4 * version
                ux, uy = (tr - tl) / (modules - 7), (bl - tl) / (modules - 7)
                grid = np.zeros((modules, modules), np.int64)
                height, width = ink.shape
                for row in range(modules):
                    for col in range(modules):
                        x, y = tl + (col - 3) * ux + (row - 3) * uy
                        xi, yi = int(round(x)), int(round(y))
                        if 0 <= xi < width and 0 <= yi < height:
                            grid[row, col] = 1 if ink[yi, xi] < 128 else 0
                text = _decode_grid(_canonical(grid, modules), detector)
                if text:
                    if text not in results:
                        results.append(text)
                    break
        if results:
            break
    return results


def read_designed(gray) -> list[str]:
    """Texts of designed QR codes in a grayscale picture (an empty list when none decode)."""
    import cv2

    detector = cv2.QRCodeDetector()
    found = _read(gray, detector)
    if not found and max(gray.shape) < 2400:
        found = _read(cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC), detector)
    return found
