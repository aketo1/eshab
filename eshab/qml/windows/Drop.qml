import QtQuick
import Eshab

// The drop that flies from where a file was let go to the top of the screen,
// where the activity island forms around it. Half a second, then gone.
Window {
    id: win

    required property var island

    width: 44
    height: 44
    color: "transparent"
    title: "Eshab"
    flags: Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus
           | Qt.NoDropShadowWindowHint | Qt.WindowTransparentForInput

    property real t: 0
    readonly property point from: island.flightFrom
    readonly property point to: island.flightTo
    readonly property int serial: island.flightSerial
    // A gentle sideways bulge makes the path a curve, not a ruler line.
    readonly property real bulge: Math.max(-90, Math.min(90, (from.x - to.x) * 0.18))

    function ease(v) { return v < 0.5 ? 4 * v * v * v : 1 - Math.pow(-2 * v + 2, 3) / 2 }

    x: from.x + (to.x - from.x) * ease(t) + Math.sin(Math.PI * t) * bulge - width / 2
    y: from.y + (to.y - from.y) * ease(t) - height / 2
    visible: t > 0.001 && t < 0.999

    onSerialChanged: if (serial > 0) flight.restart()
    NumberAnimation {
        id: flight
        target: win
        property: "t"
        from: 0
        to: 1
        duration: 480
    }

    Rectangle {
        anchors.centerIn: parent
        width: 20 * (1 - 0.3 * win.t)
        height: width
        radius: width / 2
        color: Theme.accent
        border.width: 1.5
        border.color: Qt.rgba(1, 1, 1, 0.75)
        Rectangle {
            x: parent.width * 0.22; y: parent.height * 0.18
            width: parent.width * 0.32; height: width; radius: width / 2
            color: Qt.rgba(1, 1, 1, 0.65)
        }
    }
}
