import QtQuick
import QtQuick.Effects

// Glass for a frameless window: the blurred wallpaper slides under the
// window as it moves, then a neutral tint and a rim. Nothing here animates,
// so it is rendered once and reused.
Item {
    id: root

    property var window: null
    property url source: eshab.backdrop
    property real radius: 22
    property real tint: Theme.dark ? 0.58 : 0.50

    Item {
        id: content
        anchors.fill: parent
        visible: false
        layer.enabled: true

        Rectangle { anchors.fill: parent; color: Theme.dark ? "#1E1E22" : "#F2F2F4" }
        Image {
            visible: root.source.toString() !== ""
            source: root.source
            asynchronous: false
            smooth: true
            fillMode: Image.Stretch
            x: root.window ? Screen.virtualX - root.window.x - root.mapToItem(null, 0, 0).x : 0
            y: root.window ? Screen.virtualY - root.window.y - root.mapToItem(null, 0, 0).y : 0
            width: Screen.width
            height: Screen.height
        }
        Rectangle {
            anchors.fill: parent
            color: Theme.dark ? Qt.rgba(0.09, 0.09, 0.11, root.tint) : Qt.rgba(0.98, 0.98, 0.99, root.tint)
        }
    }

    Rectangle {
        id: mask
        anchors.fill: parent
        radius: root.radius
        visible: false
        layer.enabled: true
    }

    MultiEffect {
        anchors.fill: parent
        source: content
        maskEnabled: true
        maskSource: mask
        saturation: 0.25
    }

    Rectangle {
        anchors.fill: parent
        radius: root.radius
        color: "transparent"
        border.width: 1
        border.color: Theme.glassRim
    }
}
