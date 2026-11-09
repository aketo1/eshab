import QtQuick
import Eshab

// A slider on the glass. A centred one fills from its middle (for -100…100 adjustments).
// In Arabic it runs from right to left, like the rest of the window.
Item {
    id: root

    property real from: 0
    property real to: 100
    property real stepSize: 1
    property real value: 0
    property real resetTo: from
    property bool centered: false
    readonly property bool mirrored: LayoutMirroring.enabled
    readonly property real ratio: Math.max(0, Math.min(1, (value - from) / Math.max(1e-9, to - from)))
    readonly property real zeroRatio: Math.max(0, Math.min(1, (0 - from) / Math.max(1e-9, to - from)))
    signal moved(real value)

    implicitHeight: 28
    implicitWidth: 220
    activeFocusOnTab: true
    Accessible.role: Accessible.Slider
    Keys.onLeftPressed: step(mirrored ? 1 : -1)
    Keys.onRightPressed: step(mirrored ? -1 : 1)
    Keys.onUpPressed: step(1)
    Keys.onDownPressed: step(-1)

    function step(direction) { set(value + direction * stepSize) }
    function set(v) {
        v = Math.max(from, Math.min(to, Math.round(v / stepSize) * stepSize))
        if (v !== value) root.moved(v)
    }
    function px(r) { return (mirrored ? 1 - r : r) * track.width }

    Rectangle {
        id: track
        anchors.verticalCenter: parent.verticalCenter
        x: 10
        width: parent.width - 20
        height: 4
        radius: 2
        color: Theme.dark ? Qt.rgba(1, 1, 1, 0.16) : Qt.rgba(0, 0, 0, 0.12)

        Rectangle {
            height: parent.height
            radius: 2
            color: Theme.accent
            x: root.centered ? Math.min(root.px(root.zeroRatio), root.px(root.ratio)) : (root.mirrored ? root.px(root.ratio) : 0)
            width: root.centered ? Math.abs(root.px(root.ratio) - root.px(root.zeroRatio))
                                 : (root.mirrored ? track.width - root.px(root.ratio) : root.px(root.ratio))
        }
        Rectangle {
            visible: root.centered
            width: 2
            height: 10
            radius: 1
            anchors.verticalCenter: parent.verticalCenter
            x: root.px(root.zeroRatio) - 1
            color: Theme.textSecondary
            opacity: 0.6
        }
    }
    Rectangle {
        id: knob
        width: 20
        height: 20
        radius: 10
        anchors.verticalCenter: parent.verticalCenter
        x: track.x + root.px(root.ratio) - width / 2
        color: "white"
        border.width: 1
        border.color: Theme.dark ? Qt.rgba(0, 0, 0, 0.4) : Qt.rgba(0, 0, 0, 0.18)
        scale: area.pressed ? 1.15 : (area.containsMouse ? 1.06 : 1)
        Behavior on scale { NumberAnimation { duration: Theme.fast } }

        Rectangle {
            anchors.centerIn: parent
            width: 8
            height: 8
            radius: 4
            color: Theme.accent
        }
        Rectangle {
            anchors.fill: parent
            anchors.margins: -4
            radius: width / 2
            color: "transparent"
            border.width: 2
            border.color: Theme.accent
            visible: root.activeFocus
        }
    }
    MouseArea {
        id: area
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        function at(mx) {
            let r = (mx - track.x) / Math.max(1, track.width)
            if (root.mirrored) r = 1 - r
            root.set(root.from + Math.max(0, Math.min(1, r)) * (root.to - root.from))
        }
        onPressed: (mouse) => { root.forceActiveFocus(); at(mouse.x) }
        onPositionChanged: (mouse) => { if (pressed) at(mouse.x) }
        onDoubleClicked: root.moved(root.resetTo)
    }
}
