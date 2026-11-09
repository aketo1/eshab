"""The shelf inside the activity island (eshab/activity.py): files parked from
the wheel stay in a small capsule at the top until they are dragged out or
cleared; the island leaves only when there is neither a job nor a parked file."""
import json
from pathlib import Path

from PySide6.QtCore import QObject, QPoint, QRect

from eshab import activity


def _island():
    island = activity.ActivityIsland.__new__(activity.ActivityIsland)
    QObject.__init__(island)
    island._cards, island._shelf, island._dragging = [], [], False
    island._state = "hidden"
    island._hover_since = island._away_since = None
    island._screen = QRect(0, 0, 1920, 1080)
    island._flight = {"from": QPoint(), "to": QPoint(), "serial": 0}
    island._apply_window = lambda: None            # no window in these tests
    island._fly = lambda anchor: island.landed()
    island._may_show = lambda: True
    return island


def _files(tmp_path, count):
    made = []
    for index in range(count):
        path = tmp_path / f"file{index}.txt"
        path.write_text("x", encoding="utf-8")
        made.append(path)
    return made


def test_parked_files_open_a_small_capsule(qapp, tmp_path):
    island = _island()
    files = _files(tmp_path, 3)
    assert island.shelve(files + [files[0], tmp_path / "missing.txt"]) == 3
    assert island.state == "compact"
    assert island.islandWidth == activity.SHELF_COMPACT_W
    assert [f["name"] for f in island.shelf] == ["file0.txt", "file1.txt", "file2.txt"]
    assert all(f["url"].startswith("image://eshab/thumb/") for f in island.shelf)
    assert island.busy()


def test_a_job_takes_the_capsule_and_the_shelf_waits_inside(qapp, tmp_path):
    island = _island()
    island.shelve(_files(tmp_path, 2))
    island.start("job", "Compress", "a.pdf", QPoint(10, 10))
    assert island.islandWidth == activity.COMPACT_W
    island._set_state("expanded")
    one_row = activity.SHELF_HEAD_H + activity.TILE_H + activity.TILE_GAP
    assert island.shelfHeight == one_row
    assert island.islandHeight == activity.EXPANDED_PAD * 2 + activity.ROW_H + 8 + one_row


def test_many_parked_files_scroll_inside_two_rows(qapp, tmp_path):
    island = _island()
    island.shelve(_files(tmp_path, 11))
    assert island.shelfHeight == activity.SHELF_HEAD_H + 2 * (activity.TILE_H + activity.TILE_GAP)


def test_the_island_leaves_when_the_shelf_is_emptied(qapp, tmp_path):
    island = _island()
    files = _files(tmp_path, 2)
    island.shelve(files)
    island.unshelve(str(files[0]))
    assert [f["name"] for f in island.shelf] == ["file1.txt"]
    island.clearShelf()
    assert island.shelf == [] and island.state == "hidden" and not island.busy()
    assert all(path.exists() for path in files)       # only the shelf forgets them


def test_a_file_gone_from_its_folder_leaves_the_shelf(qapp, tmp_path):
    island = _island()
    files = _files(tmp_path, 2)
    island.shelve(files)
    files[0].unlink()
    island.dragOut(json.dumps([str(files[0])]))          # nothing left to drag: no drag starts
    assert [f["name"] for f in island.shelf] == ["file1.txt"]


def test_the_shelf_keeps_at_most_its_limit(qapp, tmp_path):
    island = _island()
    island.shelve(_files(tmp_path, activity.MAX_SHELF + 5))
    assert len(island.shelf) == activity.MAX_SHELF
