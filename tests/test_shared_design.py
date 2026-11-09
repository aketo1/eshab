"""Every tool page uses the same chrome and keeps its primary action reachable."""
from pathlib import Path
import os
import subprocess

from PIL import Image
import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QScrollArea

from eshab import theme
from eshab.brand import BrandMark
from eshab.liquid_ui import WindowControl, WindowHeader
from eshab.media import CREATE_NO_WINDOW, ffmpeg_path
from eshab.settings_window import SettingsWindow


def capture(window, name):
    folder = os.environ.get("ESHAB_UI_QA_DIR")
    if folder:
        destination = Path(folder)
        destination.mkdir(parents=True, exist_ok=True)
        window.grab().save(str(destination / f"{name}.png"))


def configure_qa():
    if os.environ.get("ESHAB_UI_QA_DIR"):
        from eshab import i18n, settings
        i18n.set_language("ar")
        settings.set("appearanceTheme", "dark")


@pytest.fixture(scope="module")
def samples(tmp_path_factory):
    root = tmp_path_factory.mktemp("shared_design")
    image = root / "photo.png"
    Image.new("RGB", (640, 400), "steelblue").save(image)
    audio = root / "tone.wav"
    video = root / "clip.mp4"
    exe = ffmpeg_path()
    if not exe:
        pytest.skip("FFmpeg is required for media tool pages")
    for output, args in ((audio, ["-f", "lavfi", "-i", "sine=frequency=440:duration=1"]),
                         (video, ["-f", "lavfi", "-i", "color=c=blue:s=320x240:d=1", "-c:v", "mpeg4"])):
        subprocess.run([exe, "-hide_banner", "-loglevel", "error", *args, "-y", str(output)],
                        check=True, capture_output=True, timeout=30, creationflags=CREATE_NO_WINDOW)
    return image, audio, video


@pytest.mark.parametrize("name", ["compress_image", "compress_audio", "compress_video", "collage", "crop_image", "redact_image",
                                 "background", "adjust_image", "annotate", "metadata", "images_pdf", "channels", "visualizer",
                                 "trim_audio", "bleep", "trim_video", "crop_video", "speed", "snapshots", "split", "redact_video", "join"])
def test_each_tool_has_shared_header_and_visible_save(qapp, samples, name):
    from eshab.editors import images, audio, video
    from eshab.editors.pdf import ImagesPdfDialog
    image_path, audio_path, video_path = samples
    builders = {
        "compress_image": lambda: images.CompressDialog([image_path], "image"),
        "compress_audio": lambda: images.CompressDialog([audio_path], "audio"),
        "compress_video": lambda: images.CompressDialog([video_path], "video"),
        "collage": lambda: images.CollageDialog([image_path, image_path]),
        "crop_image": lambda: images.CropImageDialog(image_path),
        "redact_image": lambda: images.RedactPhotoDialog(image_path),
        "background": lambda: images.BackgroundDialog(image_path),
        "adjust_image": lambda: images.EditPhotoDialog(image_path),
        "annotate": lambda: images.AnnotateDialog(image_path),
        "metadata": lambda: images.MetadataDialog(image_path),
        "images_pdf": lambda: ImagesPdfDialog([image_path]),
        "channels": lambda: audio.ChannelsDialog(audio_path),
        "visualizer": lambda: audio.VisualizerDialog(audio_path),
        "trim_audio": lambda: audio.TrimAudioDialog(audio_path),
        "bleep": lambda: audio.BleepDialog(audio_path),
        "trim_video": lambda: video.TrimVideoDialog(video_path),
        "crop_video": lambda: video.CropVideoDialog(video_path),
        "speed": lambda: video.SpeedDialog(video_path),
        "snapshots": lambda: video.SnapshotsDialog(video_path),
        "split": lambda: video.SplitVideoDialog(video_path),
        "redact_video": lambda: video.RedactVideoDialog(video_path),
        "join": lambda: video.JoinDialog([video_path, video_path]),
    }
    configure_qa()
    theme.apply_app_theme()
    dialog = builders[name]()
    dialog.show()
    qapp.processEvents()
    assert dialog.windowFlags() & Qt.WindowType.FramelessWindowHint
    assert isinstance(dialog._window_header, WindowHeader)
    assert len(dialog._window_header.findChildren(WindowControl)) == 3
    assert len(dialog._window_header.findChildren(BrandMark)) == 1
    button = dialog._ok_button
    position = button.mapTo(dialog, button.rect().center())
    assert button.isVisible() and dialog.rect().contains(position), (name, position, dialog.size())
    assert not dialog.grab().isNull()
    capture(dialog, name)
    dialog.close()


def test_every_settings_page_scrolls_inside_shared_window(qapp):
    configure_qa()
    theme.apply_app_theme()
    window = SettingsWindow()
    window.resize(550, 520)
    window.show()
    qapp.processEvents()
    assert isinstance(window._window_header, WindowHeader)
    for index in range(window.tabs.count()):
        window.tabs.setCurrentIndex(index)
        qapp.processEvents()
        page = window.tabs.currentWidget()
        assert isinstance(page, QScrollArea)
        assert page.viewport().height() > 80
        assert not window.grab().isNull()
        capture(window, f"settings-{index}")
    window.close()
