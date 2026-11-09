"""The fan wheel's geometry: layout, edges and directional picking."""

import math

import pytest

from eshab import fan


def _toward(layout, index, distance):
    card = layout.cards[index]
    cx, cy = layout.centre
    rad = math.radians(card.angle)
    return cx + math.cos(rad) * distance, cy + math.sin(rad) * distance


@pytest.mark.parametrize("count", [1, 3, 5, 7, 10])
def test_cards_never_overlap(count):
    layout = fan.layout(count)
    for a, b in zip(layout.cards, layout.cards[1:]):
        assert math.hypot(a.x - b.x, a.y - b.y) >= fan.CARD + fan.GAP - 0.01


def test_fan_opens_up_and_the_first_card_is_on_the_right():
    layout = fan.layout(5)
    assert all(card.y < layout.centre[1] for card in layout.cards)
    assert layout.cards[0].x > layout.cards[-1].x


def test_near_the_top_edge_the_fan_opens_down():
    layout = fan.layout(5, free=(800, 60, 800, 700))
    assert layout.opens_down
    assert all(card.y > layout.centre[1] for card in layout.cards)


def test_near_a_side_edge_the_fan_leans_away():
    left_tight = fan.layout(5, free=(60, 800, 800, 800))
    right_tight = fan.layout(5, free=(800, 800, 60, 800))
    assert left_tight.bisector > -90 > right_tight.bisector


@pytest.mark.parametrize("count", [2, 6, 10])
def test_pointing_picks_that_card_at_any_distance(count):
    layout = fan.layout(count)
    for index in range(count):
        for distance in (fan.DEAD_ZONE + 2, 90, 400):
            assert fan.pick(layout, *_toward(layout, index, distance)) == index


def test_the_orb_and_the_closed_side_cancel():
    layout = fan.layout(4)
    cx, cy = layout.centre
    assert fan.pick(layout, cx + 10, cy - 10) == -1          # inside the orb
    assert fan.pick(layout, cx, cy + 200) == -1               # straight down, fan opens up


def test_a_little_past_either_end_still_picks_the_end_card():
    layout = fan.layout(3)
    cx, cy = layout.centre
    first = layout.cards[0]
    rad = math.radians(first.angle + layout.step / 2 + 20)
    assert fan.pick(layout, cx + math.cos(rad) * 150, cy + math.sin(rad) * 150) == 0


def test_stepping_wraps_around():
    layout = fan.layout(4)
    assert fan.step_selection(layout, -1, 1) == 0
    assert fan.step_selection(layout, -1, -1) == 3
    assert fan.step_selection(layout, 3, 1) == 0
