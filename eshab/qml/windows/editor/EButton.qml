import QtQuick
import Eshab

// A pill button on the glass: primary (the material's colour), secondary, quiet or danger.
Item {
    id: root

    property string text: ""
    property string kind: "secondary"
    property bool compact: false
    signal clicked()

    implicitWidth: Math.max(compact ? 36 : 92, label.implicitWidth + (compact ? 22 : 34))
    implicitHeight: compact ? 30 : 38
    opacity: enabled ? 1 : 0.4
    activeFocusOnTab: true
    Accessible.role: Accessible.Button
    Accessible.name: text
    Keys.onReturnPressed: if (enabled) root.clicked()
    Keys.onSpacePressed: if (enabled) root.clicked()

    Rectangle {
        anchors.fill: parent
        radius: height / 2
        scale: area.pressed ? 0.97 : 1
        color: root.kind === "primary" ? Theme.accent
             : root.kind === "danger" ? "#E5484D"
             : root.kind === "quiet" ? (area.containsMouse ? (Theme.dark ? Qt.rgba(1, 1, 1, 0.08) : Qt.rgba(0, 0, 0, 0.05)) : "transparent")
             : (Theme.dark ? Qt.rgba(1, 1, 1, area.pressed ? 0.17 : (area.containsMouse ? 0.13 : 0.08))
                           : Qt.rgba(0, 0, 0, area.pressed ? 0.12 : (area.containsMouse ? 0.08 : 0.05)))
        border.width: root.kind === "quiet" ? 0 : 1
        border.color: root.kind === "primary" ? Qt.darker(Theme.accent, 1.12) : root.kind === "danger" ? "#C93C41" : Theme.glassRim
        Behavior on scale { NumberAnimation { duration: Theme.fast } }
        Behavior on color { ColorAnimation { duration: Theme.fast } }

        Rectangle {
            anchors.fill: parent
            radius: parent.radius
            color: "white"
            opacity: (root.kind === "primary" || root.kind === "danger") && area.containsMouse ? 0.12 : 0
        }
        Rectangle {
            anchors.fill: parent
            anchors.margins: -3
            radius: height / 2
            color: "transparent"
            border.width: 2
            border.color: Theme.accent
            visible: root.activeFocus
        }
    }
    Text {
        id: label
        anchors.centerIn: parent
        text: root.text
        color: root.kind === "primary" ? Theme.onAccent : root.kind === "danger" ? "white" : Theme.text
        font.family: Theme.fontFamily
        font.pixelSize: root.compact ? 13 : 14
        font.weight: root.kind === "primary" ? Font.DemiBold : Font.Normal
    }
    MouseArea {
        id: area
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: root.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
        onClicked: if (root.enabled) root.clicked()
    }
}
