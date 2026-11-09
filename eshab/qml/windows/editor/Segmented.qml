import QtQuick
import Eshab

// One choice among a few, as chips. Given a width they wrap onto more lines;
// without one they sit in a single row.
Item {
    id: root

    property var options: []
    property var value
    property real spacing: 6
    signal picked(var value)

    implicitWidth: {
        let total = 0
        for (let i = 0; i < chips.count; i++) {
            const chip = chips.itemAt(i)
            if (chip) total += chip.width + (i > 0 ? spacing : 0)
        }
        return total
    }
    implicitHeight: flow.height

    Flow {
        id: flow
        width: root.width > 0 ? root.width : root.implicitWidth
        spacing: root.spacing

        Repeater {
            id: chips
            model: root.options

            Rectangle {
                id: chip
                readonly property bool chosen: root.value === modelData.value

                height: 32
                width: Math.max(44, words.implicitWidth + 26)
                radius: 16
                color: chosen ? Theme.accent
                     : (Theme.dark ? Qt.rgba(1, 1, 1, area.containsMouse ? 0.13 : 0.07)
                                   : Qt.rgba(0, 0, 0, area.containsMouse ? 0.08 : 0.045))
                border.width: 1
                border.color: chosen ? Qt.darker(Theme.accent, 1.12) : Theme.glassRim
                activeFocusOnTab: true
                Accessible.role: Accessible.RadioButton
                Accessible.name: modelData.label
                Accessible.checked: chosen
                Keys.onSpacePressed: root.picked(modelData.value)
                Keys.onReturnPressed: root.picked(modelData.value)
                Behavior on color { ColorAnimation { duration: Theme.fast } }

                Text {
                    id: words
                    anchors.centerIn: parent
                    text: modelData.label
                    color: chip.chosen ? Theme.onAccent : Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: 13
                    font.weight: chip.chosen ? Font.DemiBold : Font.Normal
                }
                Rectangle {
                    anchors.fill: parent
                    anchors.margins: -3
                    radius: height / 2
                    color: "transparent"
                    border.width: 2
                    border.color: Theme.accent
                    visible: chip.activeFocus
                }
                MouseArea {
                    id: area
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.picked(modelData.value)
                }
            }
        }
    }
}
