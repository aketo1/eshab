import QtQuick
import Eshab

// A few colours to tap, and any colour by its code.
Column {
    id: root

    property var colors: []
    property string value: "#000000"
    signal picked(string value)

    spacing: 8

    Flow {
        width: parent.width
        spacing: 8
        Repeater {
            model: root.colors
            Rectangle {
                readonly property bool chosen: root.value.toUpperCase() === modelData.toUpperCase()
                width: 28
                height: 28
                radius: 14
                color: modelData
                border.width: chosen ? 3 : 1
                border.color: chosen ? Theme.accent : Theme.glassRim
                scale: area.containsMouse ? 1.1 : 1
                Behavior on scale { NumberAnimation { duration: Theme.fast } }
                Accessible.role: Accessible.RadioButton
                Accessible.name: modelData
                MouseArea {
                    id: area
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.picked(modelData)
                }
            }
        }
    }
    Row {
        spacing: 8
        Rectangle {
            width: 28
            height: 28
            radius: 8
            color: /^#[0-9a-fA-F]{6}$/.test(code.text) ? code.text : root.value
            border.width: 1
            border.color: Theme.glassRim
        }
        ETextField {
            id: code
            width: 120
            height: 30
            text: root.value.toUpperCase()
            onEdited: (words) => {
                let clean = words.trim()
                if (!clean.startsWith("#")) clean = "#" + clean
                if (/^#[0-9a-fA-F]{6}$/.test(clean)) root.picked(clean.toUpperCase())
            }
            Connections {
                target: root
                function onValueChanged() { if (!code.activeFocus) code.text = root.value.toUpperCase() }
            }
        }
    }
}
