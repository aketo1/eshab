import QtQuick

// One material to choose from: a glass jar with the mark inside it.
Item {
    id: root

    property string material: "honey"
    property string label: ""
    property bool selected: false
    signal picked()

    width: 92
    height: 112
    Accessible.role: Accessible.RadioButton
    Accessible.name: label
    Accessible.checked: selected

    Rectangle {
        id: jar
        width: 76
        height: 76
        radius: 38
        anchors.horizontalCenter: parent.horizontalCenter
        color: Theme.dark ? Qt.rgba(1, 1, 1, 0.06) : Qt.rgba(1, 1, 1, 0.55)
        border.width: root.selected ? 2 : 1
        border.color: root.selected ? Theme.materials[root.material].accent : Theme.glassRim
        scale: area.pressed ? 0.94 : (root.selected ? 1.06 : (area.containsMouse ? 1.03 : 1))
        Behavior on scale { SpringAnimation { spring: 4; damping: 0.28; epsilon: 0.001 } }
        Behavior on border.color { ColorAnimation { duration: Theme.base } }

        Logo {
            anchors.centerIn: parent
            size: 54
            material: root.material
            alive: root.selected
        }
    }

    Text {
        anchors.top: jar.bottom
        anchors.topMargin: 10
        anchors.horizontalCenter: parent.horizontalCenter
        text: root.label
        color: root.selected ? Theme.text : Theme.textSecondary
        font.family: Theme.fontFamily
        font.pixelSize: 13
        font.weight: root.selected ? Font.DemiBold : Font.Normal
    }

    MouseArea {
        id: area
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: root.picked()
    }
}
