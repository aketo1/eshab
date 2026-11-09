"""Geometry of the fan wheel: where the cards sit and which one you point at.

All three wheels are a fan of cards on an arc around the dragged file. The
arc opens towards the free side of the screen (up unless the pointer is near
the top edge) and selection is directional: once the pointer leaves the orb,
the card in that direction is chosen, whatever the distance. Pointing at
the closed side of the fan, or staying in the orb, means "cancel".

Pure Python, no Qt, so it is tested directly.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

SIDE = 560.0          # the wheel window is a square this wide, centred on the pointer
ORB_RADIUS = 34.0
DEAD_ZONE = ORB_RADIUS + 12.0
CARD = 58.0
GAP = 10.0
END_GRACE_DEG = 40.0  # pointing a little past either end still picks the end card
MAX_CARDS = 10


@dataclass(frozen=True)
class Card:
    angle: float      # degrees, screen convention (y down): -90 is up
    x: float          # centre, window coordinates
    y: float


@dataclass(frozen=True)
class Layout:
    centre: tuple[float, float]
    radius: float
    step: float
    bisector: float               # direction the fan opens towards
    cards: tuple[Card, ...] = field(default_factory=tuple)

    @property
    def opens_down(self) -> bool:
        return math.sin(math.radians(self.bisector)) > 0


def _radius_for(count: int) -> float:
    return 128.0 if count <= 6 else 150.0


def _step_for(radius: float) -> float:
    return math.degrees(2.0 * math.asin((CARD + GAP) / (2.0 * radius)))


def bisector_for(free: tuple[float, float, float, float], radius: float) -> float:
    """Direction the fan opens towards, given free space (left, top, right,
    bottom) around the pointer in logical pixels."""
    left, top, right, bottom = free
    reach = radius + CARD * 0.75
    angle = -90.0 if top >= reach or top >= bottom else 90.0
    tilt = 40.0 if angle < 0 else -40.0
    if left < reach * 0.8 <= right:
        angle += tilt          # lean away from the left edge
    elif right < reach * 0.8 <= left:
        angle -= tilt          # lean away from the right edge
    return angle


def layout(count: int, free: tuple[float, float, float, float] = (1e4, 1e4, 1e4, 1e4)) -> Layout:
    count = max(0, min(int(count), MAX_CARDS))
    centre = (SIDE / 2.0, SIDE / 2.0)
    radius = _radius_for(count)
    step = _step_for(radius)
    bisector = bisector_for(free, radius)
    start = bisector - step * (count - 1) / 2.0
    cards = []
    for index in range(count):
        # Arabic reads right to left: the first card sits at the right end.
        angle = start + step * (count - 1 - index)
        rad = math.radians(angle)
        cards.append(Card(angle, centre[0] + math.cos(rad) * radius, centre[1] + math.sin(rad) * radius))
    return Layout(centre, radius, step, bisector, tuple(cards))


def _delta(a: float, b: float) -> float:
    return (a - b + 180.0) % 360.0 - 180.0


def pick(fan: Layout, x: float, y: float) -> int:
    """Index of the card the pointer at (x, y) points at, or -1 to cancel."""
    if not fan.cards:
        return -1
    dx, dy = x - fan.centre[0], y - fan.centre[1]
    if math.hypot(dx, dy) < DEAD_ZONE:
        return -1
    angle = math.degrees(math.atan2(dy, dx))
    best = min(range(len(fan.cards)), key=lambda i: abs(_delta(angle, fan.cards[i].angle)))
    distance = abs(_delta(angle, fan.cards[best].angle))
    if distance <= fan.step / 2.0:
        return best
    ends = {0, len(fan.cards) - 1}
    if best in ends and distance <= fan.step / 2.0 + END_GRACE_DEG:
        return best
    return -1


def step_selection(fan: Layout, current: int, delta: int) -> int:
    """Keyboard and mouse-wheel stepping, wrapping around the fan."""
    count = len(fan.cards)
    if count == 0:
        return -1
    if current < 0:
        return 0 if delta > 0 else count - 1
    return (current + delta) % count
