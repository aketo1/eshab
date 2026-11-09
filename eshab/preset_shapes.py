"""The preset shapes whose outlines take more than a line or two: arrows that bend, callouts
with leader lines, brackets that fill one way and stroke another. Each follows the shape's
definition in ECMA-376, so its handles (the ``adj`` values) and its proportions work."""
from __future__ import annotations

import math

from .preset_outlines import OUTLINES


def _pin(low: float, value: float, high: float) -> float:
    return max(low, min(high, value))


def _poly(*points) -> str:
    return "M" + "L".join(f"{x:.3f} {y:.3f}" for x, y in points) + "Z"


def _circle(cx: float, cy: float, rx: float, ry: float) -> str:
    return (f"M{cx - rx:.3f} {cy:.3f}A{rx:.3f} {ry:.3f} 0 1 1 {cx + rx:.3f} {cy:.3f}"
            f"A{rx:.3f} {ry:.3f} 0 1 1 {cx - rx:.3f} {cy:.3f}Z")


def _on_ellipse(cx: float, cy: float, rx: float, ry: float, degrees: float) -> tuple:
    """The point an arc starts or ends on: DrawingML's angles are as seen, not as parameters."""
    t = math.radians(degrees)
    t = math.atan2(rx * math.sin(t), ry * math.cos(t))
    return cx + rx * math.cos(t), cy + ry * math.sin(t)


def _filled_then_stroked(path: str) -> list:
    """A curve that fills as a closed shape but only strokes along itself."""
    return [(path + "Z", "nostroke"), (path, "nofill")]


def _brackets(name: str, w: float, h: float, adj: dict, ss: float):
    if name == "leftBracket":
        y = ss * _pin(0, adj.get("adj", 8333.0), 50000.0 * h / ss) / 100000.0
        return _filled_then_stroked(f"M{w:.3f} {h:.3f}A{w:.3f} {y:.3f} 0 0 1 0 {h - y:.3f}L0 {y:.3f}A{w:.3f} {y:.3f} 0 0 1 {w:.3f} 0")
    if name == "rightBracket":
        y = ss * _pin(0, adj.get("adj", 8333.0), 50000.0 * h / ss) / 100000.0
        return _filled_then_stroked(f"M0 0A{w:.3f} {y:.3f} 0 0 1 {w:.3f} {y:.3f}L{w:.3f} {h - y:.3f}A{w:.3f} {y:.3f} 0 0 1 0 {h:.3f}")
    if name in ("leftBrace", "rightBrace"):
        a2 = _pin(0, adj.get("adj2", 50000.0), 100000)
        a1 = _pin(0, adj.get("adj1", 8333.0), min(100000 - a2, a2) / 2 * h / ss)
        y1, y3, half = ss * a1 / 100000.0, h * a2 / 100000.0, w / 2
        if name == "leftBrace":
            return _filled_then_stroked(
                f"M{w:.3f} {h:.3f}A{half:.3f} {y1:.3f} 0 0 1 {half:.3f} {h - y1:.3f}L{half:.3f} {y3 + y1:.3f}"
                f"A{half:.3f} {y1:.3f} 0 0 0 0 {y3:.3f}A{half:.3f} {y1:.3f} 0 0 0 {half:.3f} {y3 - y1:.3f}"
                f"L{half:.3f} {y1:.3f}A{half:.3f} {y1:.3f} 0 0 1 {w:.3f} 0")
        return _filled_then_stroked(
            f"M0 0A{half:.3f} {y1:.3f} 0 0 1 {half:.3f} {y1:.3f}L{half:.3f} {y3 - y1:.3f}"
            f"A{half:.3f} {y1:.3f} 0 0 0 {w:.3f} {y3:.3f}A{half:.3f} {y1:.3f} 0 0 0 {half:.3f} {y3 + y1:.3f}"
            f"L{half:.3f} {h - y1:.3f}A{half:.3f} {y1:.3f} 0 0 1 0 {h:.3f}")
    if name == "bracketPair":
        r = ss * _pin(0, adj.get("adj", 16667.0), 50000) / 100000.0
        left = f"M{r:.3f} {h:.3f}A{r:.3f} {r:.3f} 0 0 1 0 {h - r:.3f}L0 {r:.3f}A{r:.3f} {r:.3f} 0 0 1 {r:.3f} 0"
        right = f"M{w - r:.3f} 0A{r:.3f} {r:.3f} 0 0 1 {w:.3f} {r:.3f}L{w:.3f} {h - r:.3f}A{r:.3f} {r:.3f} 0 0 1 {w - r:.3f} {h:.3f}"
        whole = (f"M{r:.3f} 0L{w - r:.3f} 0A{r:.3f} {r:.3f} 0 0 1 {w:.3f} {r:.3f}L{w:.3f} {h - r:.3f}"
                 f"A{r:.3f} {r:.3f} 0 0 1 {w - r:.3f} {h:.3f}L{r:.3f} {h:.3f}A{r:.3f} {r:.3f} 0 0 1 0 {h - r:.3f}"
                 f"L0 {r:.3f}A{r:.3f} {r:.3f} 0 0 1 {r:.3f} 0Z")
        return [(whole, "nostroke"), (left + right, "nofill")]
    if name == "bracePair":
        r = ss * _pin(0, adj.get("adj", 8333.0), 25000) / 100000.0
        vc = h / 2
        arc = f"A{r:.3f} {r:.3f} 0 0"
        left = (f"M{r * 2:.3f} {h:.3f}{arc} 1 {r:.3f} {h - r:.3f}L{r:.3f} {vc + r:.3f}{arc} 0 0 {vc:.3f}"
                f"{arc} 0 {r:.3f} {vc - r:.3f}L{r:.3f} {r:.3f}{arc} 1 {r * 2:.3f} 0")
        right = (f"M{w - r * 2:.3f} 0{arc} 1 {w - r:.3f} {r:.3f}L{w - r:.3f} {vc - r:.3f}{arc} 0 {w:.3f} {vc:.3f}"
                 f"{arc} 0 {w - r:.3f} {vc + r:.3f}L{w - r:.3f} {h - r:.3f}{arc} 1 {w - r * 2:.3f} {h:.3f}")
        whole = (f"M{r * 2:.3f} {h:.3f}{arc} 1 {r:.3f} {h - r:.3f}L{r:.3f} {vc + r:.3f}{arc} 0 0 {vc:.3f}"
                 f"{arc} 0 {r:.3f} {vc - r:.3f}L{r:.3f} {r:.3f}{arc} 1 {r * 2:.3f} 0L{w - r * 2:.3f} 0"
                 f"{arc} 1 {w - r:.3f} {r:.3f}L{w - r:.3f} {vc - r:.3f}{arc} 0 {w:.3f} {vc:.3f}"
                 f"{arc} 0 {w - r:.3f} {vc + r:.3f}L{w - r:.3f} {h - r:.3f}{arc} 1 {w - r * 2:.3f} {h:.3f}Z")
        return [(whole, "nostroke"), (left + right, "nofill")]
    return None


def _bent_arrows(name: str, w: float, h: float, adj: dict, ss: float):
    hc, vc = w / 2, h / 2
    if name == "bentArrow":
        a2 = _pin(0, adj.get("adj2", 25000.0), 50000)
        a1 = _pin(0, adj.get("adj1", 25000.0), a2 * 2)
        a3 = _pin(0, adj.get("adj3", 25000.0), 50000)
        th, aw2, ah = ss * a1 / 100000.0, ss * a2 / 100000.0, ss * a3 / 100000.0
        dh2 = aw2 - th / 2
        room = min(w - ah, h - dh2)
        bd = ss * _pin(0, adj.get("adj4", 43750.0), 100000.0 * room / ss) / 100000.0
        inner = max(bd - th, 0.0)
        x4, y3 = w - ah, dh2 + th
        return [(f"M0 {h:.3f}L0 {dh2 + bd:.3f}A{bd:.3f} {bd:.3f} 0 0 1 {bd:.3f} {dh2:.3f}L{x4:.3f} {dh2:.3f}L{x4:.3f} 0"
                 f"L{w:.3f} {aw2:.3f}L{x4:.3f} {aw2 * 2:.3f}L{x4:.3f} {y3:.3f}L{th + inner:.3f} {y3:.3f}"
                 f"A{inner:.3f} {inner:.3f} 0 0 0 {th:.3f} {y3 + inner:.3f}L{th:.3f} {h:.3f}Z", None)]
    if name == "bentUpArrow":
        a1, a2, a3 = (_pin(0, adj.get(k, 25000.0), 50000) for k in ("adj1", "adj2", "adj3"))
        y1, x1, x3 = ss * a3 / 100000.0, w - ss * a2 / 50000.0, w - ss * a2 / 100000.0
        half = ss * a1 / 200000.0
        y2 = h - ss * a1 / 100000.0
        return [(_poly((0, y2), (x3 - half, y2), (x3 - half, y1), (x1, y1), (x3, 0), (w, y1), (x3 + half, y1), (x3 + half, h), (0, h)), None)]
    if name == "leftUpArrow":
        a2 = _pin(0, adj.get("adj2", 25000.0), 50000)
        a1 = _pin(0, adj.get("adj1", 25000.0), a2 * 2)
        a3 = _pin(0, adj.get("adj3", 25000.0), 100000 - a2 * 2)
        x1 = ss * a3 / 100000.0
        wide, half = ss * a2 / 100000.0, ss * a1 / 200000.0
        x4, y4 = w - wide, h - wide
        return [(_poly((0, y4), (x1, h - wide * 2), (x1, y4 - half), (x4 - half, y4 - half), (x4 - half, x1), (w - wide * 2, x1),
                       (x4, 0), (w, x1), (x4 + half, x1), (x4 + half, y4 + half), (x1, y4 + half), (x1, h)), None)]
    if name == "leftRightUpArrow":
        a2 = _pin(0, adj.get("adj2", 25000.0), 50000)
        a1 = _pin(0, adj.get("adj1", 25000.0), a2 * 2)
        a3 = _pin(0, adj.get("adj3", 25000.0), (100000 - a2 * 2) / 2)
        x1 = ss * a3 / 100000.0
        wide, half = ss * a2 / 100000.0, ss * a1 / 200000.0
        y4 = h - wide
        return [(_poly((0, y4), (x1, h - wide * 2), (x1, y4 - half), (hc - half, y4 - half), (hc - half, x1), (hc - wide, x1), (hc, 0),
                       (hc + wide, x1), (hc + half, x1), (hc + half, y4 - half), (w - x1, y4 - half), (w - x1, h - wide * 2), (w, y4),
                       (w - x1, h), (w - x1, y4 + half), (x1, y4 + half), (x1, h)), None)]
    if name == "quadArrow":
        a2 = _pin(0, adj.get("adj2", 22500.0), 50000)
        a1 = _pin(0, adj.get("adj1", 22500.0), a2 * 2)
        a3 = _pin(0, adj.get("adj3", 22500.0), (100000 - a2 * 2) / 2)
        x1 = ss * a3 / 100000.0
        wide, half = ss * a2 / 100000.0, ss * a1 / 200000.0
        return [(_poly((0, vc), (x1, vc - wide), (x1, vc - half), (hc - half, vc - half), (hc - half, x1), (hc - wide, x1), (hc, 0),
                       (hc + wide, x1), (hc + half, x1), (hc + half, vc - half), (w - x1, vc - half), (w - x1, vc - wide), (w, vc),
                       (w - x1, vc + wide), (w - x1, vc + half), (hc + half, vc + half), (hc + half, h - x1), (hc + wide, h - x1), (hc, h),
                       (hc - wide, h - x1), (hc - half, h - x1), (hc - half, vc + half), (x1, vc + half), (x1, vc + wide)), None)]
    if name == "stripedRightArrow":
        a1 = _pin(0, adj.get("adj1", 50000.0), 100000)
        a2 = _pin(0, adj.get("adj2", 50000.0), 84375.0 * w / ss)
        dx = w - ss * a2 / 100000.0
        half = h * a1 / 200000.0
        top, low = vc - half, vc + half
        return [(_poly((0, top), (ss / 32, top), (ss / 32, low), (0, low)) + _poly((ss / 16, top), (ss / 8, top), (ss / 8, low), (ss / 16, low))
                 + _poly((ss * 5 / 32, top), (dx, top), (dx, 0), (w, vc), (dx, h), (dx, low), (ss * 5 / 32, low)), None)]
    if name == "uturnArrow":
        a2 = _pin(0, adj.get("adj2", 25000.0), 25000)
        a1 = _pin(0, adj.get("adj1", 25000.0), a2 * 2)
        a3 = _pin(0, adj.get("adj3", 25000.0), (100000 - a1 * ss / h) * h / ss)
        a5 = _pin((a3 + a1) * ss / h, adj.get("adj5", 75000.0), 100000)
        th, aw2, ah = ss * a1 / 100000.0, ss * a2 / 100000.0, ss * a3 / 100000.0
        dh2 = aw2 - th / 2
        y5 = h * a5 / 100000.0
        y4 = y5 - ah
        x9 = w - dh2
        bd = ss * _pin(0, adj.get("adj4", 43750.0), min(x9 / 2, y4) * 100000.0 / ss) / 100000.0
        inner = max(bd - th, 0.0)
        x8 = w - aw2
        x6 = x8 - aw2
        x7 = x6 + dh2
        return [(f"M0 {h:.3f}L0 {bd:.3f}A{bd:.3f} {bd:.3f} 0 0 1 {bd:.3f} 0L{x9 - bd:.3f} 0A{bd:.3f} {bd:.3f} 0 0 1 {x9:.3f} {bd:.3f}"
                 f"L{x9:.3f} {y4:.3f}L{w:.3f} {y4:.3f}L{x8:.3f} {y5:.3f}L{x6:.3f} {y4:.3f}L{x7:.3f} {y4:.3f}L{x7:.3f} {th + inner:.3f}"
                 f"A{inner:.3f} {inner:.3f} 0 0 0 {x7 - inner:.3f} {th:.3f}L{th + inner:.3f} {th:.3f}"
                 f"A{inner:.3f} {inner:.3f} 0 0 0 {th:.3f} {th + inner:.3f}L{th:.3f} {h:.3f}Z", None)]
    return None


def _arrow_callouts(name: str, w: float, h: float, adj: dict, ss: float):
    hc, vc = w / 2, h / 2
    if name in ("rightArrowCallout", "leftArrowCallout"):
        a2 = _pin(0, adj.get("adj2", 25000.0), 50000.0 * h / ss)
        a1 = _pin(0, adj.get("adj1", 25000.0), a2 * 2)
        a3 = _pin(0, adj.get("adj3", 25000.0), 100000.0 * w / ss)
        a4 = _pin(0, adj.get("adj4", 64977.0), 100000 - a3 * ss / w)
        wide, half, head, box = ss * a2 / 100000.0, ss * a1 / 200000.0, ss * a3 / 100000.0, w * a4 / 100000.0
        points = [(0, 0), (box, 0), (box, vc - half), (w - head, vc - half), (w - head, vc - wide), (w, vc),
                  (w - head, vc + wide), (w - head, vc + half), (box, vc + half), (box, h), (0, h)]
        if name == "leftArrowCallout":
            points = [(w - x, y) for x, y in points]
        return [(_poly(*points), None)]
    if name in ("downArrowCallout", "upArrowCallout"):
        a2 = _pin(0, adj.get("adj2", 25000.0), 50000.0 * w / ss)
        a1 = _pin(0, adj.get("adj1", 25000.0), a2 * 2)
        a3 = _pin(0, adj.get("adj3", 25000.0), 100000.0 * h / ss)
        a4 = _pin(0, adj.get("adj4", 64977.0), 100000 - a3 * ss / h)
        wide, half, head, box = ss * a2 / 100000.0, ss * a1 / 200000.0, ss * a3 / 100000.0, h * a4 / 100000.0
        points = [(0, 0), (w, 0), (w, box), (hc + half, box), (hc + half, h - head), (hc + wide, h - head), (hc, h),
                  (hc - wide, h - head), (hc - half, h - head), (hc - half, box), (0, box)]
        if name == "upArrowCallout":
            points = [(x, h - y) for x, y in points]
        return [(_poly(*points), None)]
    if name == "leftRightArrowCallout":
        a2 = _pin(0, adj.get("adj2", 25000.0), 50000.0 * h / ss)
        a1 = _pin(0, adj.get("adj1", 25000.0), a2 * 2)
        a3 = _pin(0, adj.get("adj3", 25000.0), 50000.0 * w / ss)
        a4 = _pin(0, adj.get("adj4", 48123.0), 100000 - a3 * 2 * ss / w)
        wide, half, head, box = ss * a2 / 100000.0, ss * a1 / 200000.0, ss * a3 / 100000.0, w * a4 / 200000.0
        return [(_poly((0, vc), (head, vc - wide), (head, vc - half), (hc - box, vc - half), (hc - box, 0), (hc + box, 0), (hc + box, vc - half),
                       (w - head, vc - half), (w - head, vc - wide), (w, vc), (w - head, vc + wide), (w - head, vc + half), (hc + box, vc + half),
                       (hc + box, h), (hc - box, h), (hc - box, vc + half), (head, vc + half), (head, vc + wide)), None)]
    if name == "upDownArrowCallout":
        a2 = _pin(0, adj.get("adj2", 25000.0), 50000.0 * w / ss)
        a1 = _pin(0, adj.get("adj1", 25000.0), a2 * 2)
        a3 = _pin(0, adj.get("adj3", 25000.0), 50000.0 * h / ss)
        a4 = _pin(0, adj.get("adj4", 48123.0), 100000 - a3 * 2 * ss / h)
        wide, half, head, box = ss * a2 / 100000.0, ss * a1 / 200000.0, ss * a3 / 100000.0, h * a4 / 200000.0
        return [(_poly((hc, 0), (hc + wide, head), (hc + half, head), (hc + half, vc - box), (w, vc - box), (w, vc + box), (hc + half, vc + box),
                       (hc + half, h - head), (hc + wide, h - head), (hc, h), (hc - wide, h - head), (hc - half, h - head), (hc - half, vc + box),
                       (0, vc + box), (0, vc - box), (hc - half, vc - box), (hc - half, head), (hc - wide, head)), None)]
    if name == "quadArrowCallout":
        a2 = _pin(0, adj.get("adj2", 18515.0), 50000)
        a1 = _pin(0, adj.get("adj1", 18515.0), a2 * 2)
        a3 = _pin(0, adj.get("adj3", 18515.0), 50000 - a2)
        a4 = _pin(a1, adj.get("adj4", 48123.0), 100000 - a3 * 2)
        wide, half, head = ss * a2 / 100000.0, ss * a1 / 200000.0, ss * a3 / 100000.0
        boxw, boxh = w * a4 / 200000.0, h * a4 / 200000.0
        return [(_poly((0, vc), (head, vc - wide), (head, vc - half), (hc - boxw, vc - half), (hc - boxw, vc - boxh), (hc - half, vc - boxh),
                       (hc - half, head), (hc - wide, head), (hc, 0), (hc + wide, head), (hc + half, head), (hc + half, vc - boxh),
                       (hc + boxw, vc - boxh), (hc + boxw, vc - half), (w - head, vc - half), (w - head, vc - wide), (w, vc), (w - head, vc + wide),
                       (w - head, vc + half), (hc + boxw, vc + half), (hc + boxw, vc + boxh), (hc + half, vc + boxh), (hc + half, h - head),
                       (hc + wide, h - head), (hc, h), (hc - wide, h - head), (hc - half, h - head), (hc - half, vc + boxh), (hc - boxw, vc + boxh),
                       (hc - boxw, vc + half), (head, vc + half), (head, vc + wide)), None)]
    return None


_CALLOUT_LINES = {
    "1": (18750.0, -8333.0, 112500.0, -38333.0),
    "2": (18750.0, -8333.0, 18750.0, -16667.0, 112500.0, -46667.0),
    "3": (18750.0, -8333.0, 18750.0, -16667.0, 100000.0, -16667.0, 112963.0, -8333.0),
}


def _line_callouts(name: str, w: float, h: float, adj: dict):
    if not name[-1:] in _CALLOUT_LINES or not name[:-1] in ("callout", "accentCallout", "borderCallout", "accentBorderCallout"):
        return None
    values = _CALLOUT_LINES[name[-1]]
    points = []
    for index in range(0, len(values), 2):
        y = h * adj.get(f"adj{index + 1}", values[index]) / 100000.0
        x = w * adj.get(f"adj{index + 2}", values[index + 1]) / 100000.0
        points.append((x, y))
    box = _poly((0, 0), (w, 0), (w, h), (0, h))
    leader = "M" + "L".join(f"{x:.3f} {y:.3f}" for x, y in points)
    bar = f"M{points[0][0]:.3f} 0L{points[0][0]:.3f} {h:.3f}"
    kind = name[:-1]
    pieces = [(box, None if "Border" in kind or kind == "borderCallout" else "nostroke")]
    if kind.startswith("accent"):
        pieces.append((bar, "nofill"))
    pieces.append((leader, "nofill"))
    return pieces


def _waves(name: str, w: float, h: float, adj: dict):
    limit, default = (12500, 6250.0) if name == "doubleWave" else (20000, 12500.0)
    a1 = _pin(0, adj.get("adj1", default), limit)
    a2 = _pin(-10000, adj.get("adj2", 0.0), 10000)
    y1 = h * a1 / 100000.0
    swing = y1 * 10 / 3
    y2, y3, y4 = y1 - swing, y1 + swing, h - y1
    y5, y6 = y4 - swing, y4 + swing
    of2 = w * a2 / 50000.0
    dx2 = 0.0 if a2 > 0 else of2
    far = of2 if a2 > 0 else 0.0
    x2, last, first, x_end = -dx2, w - far, far, w + dx2
    if name == "wave":
        step = (dx2 + last) / 3
        x3 = x2 + step
        x4 = (x3 + last) / 2
        x7 = first + step
        x8 = (x7 + x_end) / 2
        return [(f"M{x2:.3f} {y1:.3f}C{x3:.3f} {y2:.3f} {x4:.3f} {y3:.3f} {last:.3f} {y1:.3f}L{x_end:.3f} {y4:.3f}"
                 f"C{x8:.3f} {y6:.3f} {x7:.3f} {y5:.3f} {first:.3f} {y4:.3f}Z", None)]
    step = (dx2 + last) / 6
    x3, x4 = x2 + step, x2 + step * 2
    x5 = (x2 + last) / 2
    x6 = (x5 + last) / 2
    x7 = (x6 + last) / 2
    x10, x11 = first + step, first + step * 2
    x12 = (first + x_end) / 2
    x13 = (x12 + x_end) / 2
    x14 = (x13 + x_end) / 2
    return [(f"M{x2:.3f} {y1:.3f}C{x3:.3f} {y2:.3f} {x4:.3f} {y3:.3f} {x5:.3f} {y1:.3f}C{x6:.3f} {y2:.3f} {x7:.3f} {y3:.3f} {last:.3f} {y1:.3f}"
             f"L{x_end:.3f} {y4:.3f}C{x14:.3f} {y6:.3f} {x13:.3f} {y5:.3f} {x12:.3f} {y4:.3f}C{x11:.3f} {y6:.3f} {x10:.3f} {y5:.3f} {first:.3f} {y4:.3f}Z", None)]


def _math(name: str, w: float, h: float, adj: dict, ss: float):
    hc, vc = w / 2, h / 2
    if name == "mathPlus":
        a1 = _pin(0, adj.get("adj1", 23520.0), 73490)
        dx1, dy1, dx2 = w * 73490 / 200000.0, h * 73490 / 200000.0, ss * a1 / 200000.0
        return [(_poly((hc - dx1, vc - dx2), (hc - dx2, vc - dx2), (hc - dx2, vc - dy1), (hc + dx2, vc - dy1), (hc + dx2, vc - dx2),
                       (hc + dx1, vc - dx2), (hc + dx1, vc + dx2), (hc + dx2, vc + dx2), (hc + dx2, vc + dy1), (hc - dx2, vc + dy1),
                       (hc - dx2, vc + dx2), (hc - dx1, vc + dx2)), None)]
    if name == "mathMultiply":
        th = ss * _pin(0, adj.get("adj1", 23520.0), 51965) / 100000.0
        angle = math.atan2(h, w)
        sa, ca, ta = math.sin(angle), math.cos(angle), math.tan(angle)
        length = math.hypot(w, h)
        margin = length - length * 51965 / 100000.0
        xm, ym = ca * margin / 2, sa * margin / 2
        dxa, dya = sa * th / 2, ca * th / 2
        xa, ya, xb, yb = xm - dxa, ym + dya, xm + dxa, ym - dya
        yc = (hc - xb) * ta + yb
        xd, xe = w - xb, w - xa
        xfe = (vc - ya) / ta
        return [(_poly((xa, ya), (xb, yb), (hc, yc), (xd, yb), (xe, ya), (xe - xfe, vc), (xe, h - ya), (xd, h - yb), (hc, h - yc),
                       (xb, h - yb), (xa, h - ya), (xa + xfe, vc)), None)]
    if name == "mathDivide":
        a1 = _pin(1000, adj.get("adj1", 23520.0), 73490)
        a3 = _pin(1000, adj.get("adj3", 11760.0), 36745 - a1 / 2)
        a2 = _pin(0, adj.get("adj2", 5880.0), 100000 - 2 * a3 - a1)
        half, gap, r = h * a1 / 200000.0, h * a2 / 100000.0, h * a3 / 100000.0
        dx1 = w * 73490 / 200000.0
        y3, y4 = vc - half, vc + half
        centre = y3 - gap - r
        return [(_circle(hc, centre, r, r) + _circle(hc, h - centre, r, r)
                 + _poly((hc - dx1, y3), (hc + dx1, y3), (hc + dx1, y4), (hc - dx1, y4)), None)]
    return None


def _cut_corners(name: str, w: float, h: float, adj: dict, ss: float):
    if name == "snip2DiagRect":
        one, two = (ss * _pin(0, adj.get(k, d), 50000) / 100000.0 for k, d in (("adj1", 0.0), ("adj2", 16667.0)))
        return [(_poly((one, 0), (w - two, 0), (w, two), (w, h - one), (w - one, h), (two, h), (0, h - two), (0, one)), None)]
    if name == "snipRoundRect":
        one, two = (ss * _pin(0, adj.get(k, 16667.0), 50000) / 100000.0 for k in ("adj1", "adj2"))
        return [(f"M{one:.3f} 0L{w - two:.3f} 0L{w:.3f} {two:.3f}L{w:.3f} {h:.3f}L0 {h:.3f}L0 {one:.3f}A{one:.3f} {one:.3f} 0 0 1 {one:.3f} 0Z", None)]
    if name == "round2DiagRect":
        one, two = (ss * _pin(0, adj.get(k, d), 50000) / 100000.0 for k, d in (("adj1", 16667.0), ("adj2", 0.0)))
        return [(f"M{one:.3f} 0L{w - two:.3f} 0A{two:.3f} {two:.3f} 0 0 1 {w:.3f} {two:.3f}L{w:.3f} {h - one:.3f}"
                 f"A{one:.3f} {one:.3f} 0 0 1 {w - one:.3f} {h:.3f}L{two:.3f} {h:.3f}A{two:.3f} {two:.3f} 0 0 1 0 {h - two:.3f}"
                 f"L0 {one:.3f}A{one:.3f} {one:.3f} 0 0 1 {one:.3f} 0Z", None)]
    if name == "round2SameRect":
        one, two = (ss * _pin(0, adj.get(k, d), 50000) / 100000.0 for k, d in (("adj1", 16667.0), ("adj2", 0.0)))
        return [(f"M{one:.3f} 0L{w - one:.3f} 0A{one:.3f} {one:.3f} 0 0 1 {w:.3f} {one:.3f}L{w:.3f} {h - two:.3f}"
                 f"A{two:.3f} {two:.3f} 0 0 1 {w - two:.3f} {h:.3f}L{two:.3f} {h:.3f}A{two:.3f} {two:.3f} 0 0 1 0 {h - two:.3f}"
                 f"L0 {one:.3f}A{one:.3f} {one:.3f} 0 0 1 {one:.3f} 0Z", None)]
    if name == "nonIsoscelesTrapezoid":
        one = ss * _pin(0, adj.get("adj1", 25000.0), 100000.0 * w / ss / 2) / 100000.0
        two = ss * _pin(0, adj.get("adj2", 25000.0), 100000.0 * w / ss / 2) / 100000.0
        return [(_poly((0, h), (one, 0), (w - two, 0), (w, h)), None)]
    if name == "pieWedge":
        return [(f"M0 {h:.3f}A{w:.3f} {h:.3f} 0 0 1 {w:.3f} 0L{w:.3f} {h:.3f}Z", None)]
    return None


def _no_smoking(w: float, h: float, adj: dict, ss: float):
    hc, vc = w / 2, h / 2
    dr = ss * _pin(0, adj.get("adj", 18750.0), 50000) / 100000.0
    iw, ih = max(hc - dr, 0.01), max(vc - dr, 0.01)
    across = math.atan2(h, w)
    ct, st = ih * math.cos(across), iw * math.sin(across)
    n = iw * ih / max(math.hypot(ct, st), 0.01)
    half_angle = math.degrees(math.atan2(dr / 2, n))
    middle = math.degrees(across)
    d = _circle(hc, vc, hc, vc)
    for start in (middle - half_angle, middle - half_angle - 180.0):
        one = _on_ellipse(hc, vc, iw, ih, start)
        two = _on_ellipse(hc, vc, iw, ih, start - 180.0 + 2 * half_angle)
        d += f"M{one[0]:.3f} {one[1]:.3f}A{iw:.3f} {ih:.3f} 0 0 0 {two[0]:.3f} {two[1]:.3f}Z"
    return [(d, "evenodd")]


def _cloud_callout(w: float, h: float, adj: dict, ss: float):
    """The cloud, then three bubbles leading from it to the point its handle sets."""
    cloud = OUTLINES.get("cloud")
    if not cloud:
        return None
    hc, vc = w / 2, h / 2
    dx, dy = w * adj.get("adj1", -20833.0) / 100000.0, h * adj.get("adj2", 62500.0) / 100000.0
    x, y = hc + dx, vc + dy
    direction = math.atan2(dy, dx)
    turn = math.atan2(hc * math.sin(direction), vc * math.cos(direction))      # the same way, on the ellipse
    g6, g7 = hc + hc * math.cos(turn) - x, vc + vc * math.sin(turn) - y
    reach = max(math.hypot(g6, g7), 0.01)
    third = (reach - ss * 6600 / 21600) / 3
    one = third + ss * 1800 / 21600
    two = ss * 4800 / 21600 + third * 2
    small, middle, large = ss * 600 / 21600, ss * 1200 / 21600, ss * 1800 / 21600
    bubbles = (_circle(x, y, small, small)
               + _circle(one * g6 / reach + x, one * g7 / reach + y, middle, middle)
               + _circle(two * g6 / reach + x, two * g7 / reach + y, large, large))
    pieces = scaled_outline(cloud, w, h)
    return pieces[:1] + [(bubbles, None)] + pieces[1:]


def _solids(name: str, w: float, h: float, adj: dict, ss: float):
    """Shapes with lit and shaded faces: each face is filled, then one line goes over them all."""
    hc, vc = w / 2, h / 2
    if name == "can":
        y = ss * _pin(0, adj.get("adj", 25000.0), 50000.0 * h / ss) / 200000.0
        rim = f"A{hc:.3f} {y:.3f} 0 0"
        return [(f"M0 {y:.3f}{rim} 0 {w:.3f} {y:.3f}L{w:.3f} {h - y:.3f}{rim} 1 0 {h - y:.3f}Z", "nostroke"),
                (_circle(hc, y, hc, y), "lighten"),
                (f"M{w:.3f} {y:.3f}{rim} 1 0 {y:.3f}{rim} 1 {w:.3f} {y:.3f}L{w:.3f} {h - y:.3f}{rim} 1 0 {h - y:.3f}L0 {y:.3f}", "nofill")]
    if name == "cube":
        d = ss * _pin(0, adj.get("adj", 25000.0), 100000) / 100000.0
        x, y = w - d, d
        return [(_poly((0, y), (x, y), (x, h), (0, h)), "nostroke"),
                (_poly((x, y), (w, 0), (w, h - d), (x, h)), "darkenLess"),
                (_poly((0, y), (d, 0), (w, 0), (x, y)), "lightenLess"),
                (f"M0 {y:.3f}L{d:.3f} 0L{w:.3f} 0L{w:.3f} {h - d:.3f}L{x:.3f} {h:.3f}L0 {h:.3f}L0 {y:.3f}L{x:.3f} {y:.3f}L{w:.3f} 0M{x:.3f} {y:.3f}L{x:.3f} {h:.3f}", "nofill")]
    if name == "foldedCorner":
        d = ss * _pin(0, adj.get("adj", 16667.0), 50000) / 100000.0
        x1, y2 = w - d, h - d
        x2, y1 = x1 + d / 5, y2 + d / 5
        return [(_poly((0, 0), (w, 0), (w, y2), (x1, h), (0, h)), "nostroke"),
                (_poly((x1, h), (x2, y1), (w, y2)), "darkenLess"),
                (f"M{x1:.3f} {h:.3f}L{x2:.3f} {y1:.3f}L{w:.3f} {y2:.3f}L{x1:.3f} {h:.3f}L0 {h:.3f}L0 0L{w:.3f} 0L{w:.3f} {y2:.3f}", "nofill")]
    if name == "bevel":
        d = ss * _pin(0, adj.get("adj", 12500.0), 50000) / 100000.0
        x, y = w - d, h - d
        return [(_poly((d, d), (x, d), (x, y), (d, y)), "nostroke"),
                (_poly((0, 0), (w, 0), (x, d), (d, d)), "lightenLess"),
                (_poly((0, h), (d, y), (x, y), (w, h)), "darkenLess"),
                (_poly((0, 0), (d, d), (d, y), (0, h)), "lighten"),
                (_poly((w, 0), (w, h), (x, y), (x, d)), "darken"),
                (_poly((0, 0), (w, 0), (w, h), (0, h)) + _poly((d, d), (x, d), (x, y), (d, y))
                 + f"M0 0L{d:.3f} {d:.3f}M0 {h:.3f}L{d:.3f} {y:.3f}M{w:.3f} 0L{x:.3f} {d:.3f}M{w:.3f} {h:.3f}L{x:.3f} {y:.3f}", "nofill")]
    if name == "smileyFace":
        a = _pin(-4653, adj.get("adj", 4653.0), 4653)
        rx, ry = w * 1125 / 21600, h * 1125 / 21600
        eye_y = h * 7570 / 21600
        x1, x3, y3 = w * 4969 / 21699, w * 16640 / 21600, h * 16515 / 21600
        dy = h * a / 100000.0
        face = _circle(hc, vc, hc, vc)
        return [(face, "nostroke"),
                (_circle(w * 6215 / 21600 + rx, eye_y, rx, ry) + _circle(w * 13135 / 21600 + rx, eye_y, rx, ry), "darkenLess+s"),
                (f"M{x1:.3f} {y3 - dy:.3f}Q{hc:.3f} {y3 + dy * 3:.3f} {x3:.3f} {y3 - dy:.3f}", "nofill"),
                (face, "nofill")]
    return None


def _curved_connectors(name: str, w: float, h: float, adj: dict):
    hc, vc = w / 2, h / 2
    if name == "curvedConnector4":
        x2 = w * adj.get("adj1", 50000.0) / 100000.0
        x3 = (w + x2) / 2
        y4 = h * adj.get("adj2", 50000.0) / 100000.0
        y1 = y4 / 2
        return [(f"M0 0C{x2 / 2:.3f} 0 {x2:.3f} {y1 / 2:.3f} {x2:.3f} {y1:.3f}C{x2:.3f} {(y1 + y4) / 2:.3f} {(x2 + x3) / 2:.3f} {y4:.3f} {x3:.3f} {y4:.3f}"
                 f"C{(x3 + w) / 2:.3f} {y4:.3f} {w:.3f} {(h + y4) / 2:.3f} {w:.3f} {h:.3f}", "nofill")]
    if name == "curvedConnector5":
        x3 = w * adj.get("adj1", 50000.0) / 100000.0
        x6 = w * adj.get("adj3", 50000.0) / 100000.0
        x5 = (x3 + x6) / 2
        y4 = h * adj.get("adj2", 50000.0) / 100000.0
        y1 = y4 / 2
        y5 = (h + y4) / 2
        return [(f"M0 0C{x3 / 2:.3f} 0 {x3:.3f} {y1 / 2:.3f} {x3:.3f} {y1:.3f}C{x3:.3f} {(y1 + y4) / 2:.3f} {(x3 + x5) / 2:.3f} {y4:.3f} {x5:.3f} {y4:.3f}"
                 f"C{(x5 + x6) / 2:.3f} {y4:.3f} {x6:.3f} {(y5 + y4) / 2:.3f} {x6:.3f} {y5:.3f}C{x6:.3f} {(y5 + h) / 2:.3f} {(x6 + w) / 2:.3f} {h:.3f} {w:.3f} {h:.3f}", "nofill")]
    return None


def more_presets(name: str, w: float, h: float, adj: dict):
    """A shape from the formulas here as [(SVG path, mode)], or None if it isn't one of them."""
    ss = min(w, h)
    for family in (lambda: _brackets(name, w, h, adj, ss), lambda: _bent_arrows(name, w, h, adj, ss), lambda: _arrow_callouts(name, w, h, adj, ss),
                   lambda: _line_callouts(name, w, h, adj), lambda: _math(name, w, h, adj, ss), lambda: _cut_corners(name, w, h, adj, ss),
                   lambda: _solids(name, w, h, adj, ss), lambda: _curved_connectors(name, w, h, adj)):
        found = family()
        if found is not None:
            return found
    if name in ("wave", "doubleWave"):
        return _waves(name, w, h, adj)
    if name == "noSmoking":
        return _no_smoking(w, h, adj, ss)
    if name == "cloudCallout":
        return _cloud_callout(w, h, adj, ss)
    return None


# -- outlines taken as they are --------------------------------------------------------------

#: Shapes whose details keep their size at the corners when the shape stretches; every other
#: outline in the table is defined proportionally, so it scales exactly.
CORNERED = frozenset(("cornerTabs", "squareTabs", "plaqueTabs", "verticalScroll", "horizontalScroll"))


def _stretch(value: float, size: float, side: float, cornered: bool) -> float:
    if not cornered or size == side:
        return value * size / 1000.0
    if value < 499.0:
        return value * side / 1000.0
    if value > 501.0:
        return size - (1000.0 - value) * side / 1000.0
    return size / 2


def scaled_outline(outline, w: float, h: float, cornered: bool = False) -> list:
    """A stored outline (in thousandths of a square) at this shape's size."""
    side = min(w, h)
    pieces = []
    for mode, d in outline:
        out, number, axis = [], "", 0

        def flush():
            nonlocal number, axis
            if number:
                size = h if axis else w
                out.append(f"{_stretch(float(number), size, side, cornered):.3f}")
                number = ""
                axis ^= 1
        for char in d:
            if char in "MLCZ":
                flush()
                out.append(char)
                axis = 0
            elif char == " ":
                flush()
                out.append(" ")
            else:
                number += char
        flush()
        pieces.append(("".join(out), mode))
    return pieces
