import QtQuick
import Eshab

// The squares behind a picture's clear parts.
Image {
    source: Theme.dark ? "image://editor/checker-dark/1" : "image://editor/checker-light/1"
    fillMode: Image.Tile
    smooth: false
    horizontalAlignment: Image.AlignLeft
    verticalAlignment: Image.AlignTop
}
