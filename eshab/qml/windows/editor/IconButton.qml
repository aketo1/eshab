import QtQuick
import Eshab

// A round button with one of Windows' own icons; with words it becomes a pill.
// The tip appears under it after a moment of hovering.
Item {
    id: root

    property string icon: ""
    property string text: ""
    property string tip: text
    property bool active: false
    property bool danger: false
    property bool mirrorIcon: false
    property bool tipAbove: false
    signal clicked()

    implicitHeight: 34
    implicitWidth: text !== "" ? row.implicitWidth + 26 : 34
    opacity: enabled ? 1 : 0.35
    activeFocusOnTab: true
    Accessible.role: Accessible.Button
    Accessible.name: tip
    Keys.onReturnPressed: if (enabled) root.clicked()
    Keys.onSpacePressed: if (enabled) root.clicked()

    readonly property color ink: active ? Theme.onAccent : (danger && area.containsMouse ? "#E5484D" : Theme.text)

    Rectangle {
        anchors.fill: parent
        radius: height / 2
        color: root.active ? Theme.accent
             : (Theme.dark ? Qt.rgba(1, 1, 1, area.pressed ? 0.18 : (area.containsMouse ? 0.11 : 0))
                           : Qt.rgba(0, 0, 0, area.pressed ? 0.12 : (area.containsMouse ? 0.07 : 0)))
        Behavior on color { ColorAnimation { duration: Theme.fast } }
    }
    Rectangle {
        anchors.fill: parent
        anchors.margins: -2
        radius: height / 2
        color: "transparent"
        border.width: 2
        border.color: Theme.accent
        visible: root.activeFocus
    }
    Row {
        id: row
        anchors.centerIn: parent
        spacing: 7
        Text {
            id: glyph
            anchors.verticalCenter: parent.verticalCenter
            text: root.icon
            visible: root.icon !== ""
            font.family: Theme.iconFont
            font.pixelSize: 15
            color: root.ink
            transform: Scale { origin.x: glyph.width / 2; xScale: root.mirrorIcon ? -1 : 1 }
        }
        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: root.text
            visible: root.text !== ""
            font.family: Theme.fontFamily
            font.pixelSize: 13
            color: root.ink
        }
    }
    MouseArea {
        id: area
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: root.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
        onClicked: if (root.enabled) root.clicked()
    }

    Timer {
        id: wait
        interval: 650
        running: area.containsMouse && root.text === "" && root.tip !== ""
    }
    Rectangle {
        id: tipBox
        visible: area.containsMouse && !wait.running && root.text === "" && root.tip !== ""
        z: 1000
        anchors.horizontalCenter: parent.horizontalCenter
        y: root.tipAbove ? -height - 6 : root.height + 6
        width: tipText.implicitWidth + 16
        height: tipText.implicitHeight + 8
        radius: 7
        color: Theme.dark ? "#2B2B30" : "#FFFFFF"
        border.width: 1
        border.color: Theme.dark ? Qt.rgba(1, 1, 1, 0.12) : Qt.rgba(0, 0, 0, 0.12)
        Text {
            id: tipText
            anchors.centerIn: parent
            text: root.tip
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: 12
        }
    }
}
