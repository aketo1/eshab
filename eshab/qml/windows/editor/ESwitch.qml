import QtQuick
import Eshab

// On or off, with its label beside it; the whole row is the target.
Item {
    id: root

    property bool checked: false
    property string text: ""
    signal toggled(bool checked)

    implicitHeight: 32
    implicitWidth: 260
    activeFocusOnTab: true
    Accessible.role: Accessible.CheckBox
    Accessible.name: text
    Accessible.checked: checked
    Keys.onSpacePressed: root.toggled(!checked)
    Keys.onReturnPressed: root.toggled(!checked)

    Text {
        anchors.left: parent.left
        anchors.right: track.left
        anchors.rightMargin: 10
        anchors.verticalCenter: parent.verticalCenter
        text: root.text
        color: Theme.text
        elide: Text.ElideRight
        font.family: Theme.fontFamily
        font.pixelSize: 13
    }
    Rectangle {
        id: track
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        width: 42
        height: 24
        radius: 12
        color: root.checked ? Theme.accent : (Theme.dark ? Qt.rgba(1, 1, 1, 0.16) : Qt.rgba(0, 0, 0, 0.14))
        border.width: 1
        border.color: root.checked ? Qt.darker(Theme.accent, 1.12) : Theme.glassRim
        Behavior on color { ColorAnimation { duration: Theme.fast } }

        Rectangle {
            width: 18
            height: 18
            radius: 9
            anchors.verticalCenter: parent.verticalCenter
            x: root.checked !== root.LayoutMirroring.enabled ? parent.width - width - 3 : 3
            color: "white"
            Behavior on x { NumberAnimation { duration: Theme.base; easing.type: Easing.OutBack; easing.overshoot: 1.4 } }
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
    MouseArea {
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        onClicked: { root.forceActiveFocus(); root.toggled(!root.checked) }
    }
}
