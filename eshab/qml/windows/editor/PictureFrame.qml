import QtQuick
import Eshab

// A picture fitted into the stage. What is drawn over it fills the whole
// stage, with the picture's corner at (originX, originY) and scaleFactor
// turning the picture's own pixels into the screen's, so handles at the
// picture's edges are inside their parents and always reachable. A photo is
// the same way round in Arabic, so nothing here is mirrored.
Item {
    id: root

    property string source: ""
    property real sourceWidth: 1
    property real sourceHeight: 1
    property real inset: 22
    property bool checker: true
    property real maxScale: 4
    readonly property real scaleFactor: Math.max(0.001, Math.min(maxScale,
        Math.min((width - 2 * inset) / Math.max(1, sourceWidth), (height - 2 * inset) / Math.max(1, sourceHeight))))
    readonly property real viewWidth: sourceWidth * scaleFactor
    readonly property real viewHeight: sourceHeight * scaleFactor
    readonly property real originX: frameItem.x
    readonly property real originY: frameItem.y
    property alias picture: pic
    default property alias overlay: layer.data

    LayoutMirroring.enabled: false
    LayoutMirroring.childrenInherit: true

    Item {
        id: frameItem
        x: Math.round((root.width - root.viewWidth) / 2)
        y: Math.round((root.height - root.viewHeight) / 2)
        width: root.viewWidth
        height: root.viewHeight

        Rectangle {
            anchors.fill: parent
            anchors.margins: -1
            color: "transparent"
            border.width: 1
            border.color: Theme.dark ? Qt.rgba(0, 0, 0, 0.5) : Qt.rgba(0, 0, 0, 0.12)
        }
        Checker {
            anchors.fill: parent
            visible: root.checker
        }
        SmoothImage {
            id: pic
            anchors.fill: parent
            source: root.source
            fillMode: Image.Stretch
        }
    }
    Item {
        id: layer
        anchors.fill: parent
    }
}
