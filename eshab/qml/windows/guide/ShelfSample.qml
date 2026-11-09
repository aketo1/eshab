import QtQuick
import Eshab

// The shelf in the island: a few parked files, ready to be dragged out.
Rectangle {
    id: root

    width: 300
    height: 150
    radius: 18
    color: Theme.dark ? Qt.rgba(1, 1, 1, 0.04) : Qt.rgba(0, 0, 0, 0.03)
    border.width: 1
    border.color: Theme.glassRim
    clip: true

    Rectangle {
        width: parent.width
        height: 6
        color: Theme.dark ? Qt.rgba(1, 1, 1, 0.08) : Qt.rgba(0, 0, 0, 0.06)
    }
    Rectangle {
        anchors.horizontalCenter: parent.horizontalCenter
        y: 16
        width: 250
        height: 118
        radius: 20
        color: Theme.dark ? "#26262B" : "#FFFFFF"
        border.width: 1
        border.color: Theme.glassRim

        Text {
            anchors.left: parent.left
            anchors.leftMargin: 16
            y: 10
            text: eshab.tr("action.file_shelf") + " · 3"
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: 13
            font.weight: Font.DemiBold
        }
        Row {
            anchors.horizontalCenter: parent.horizontalCenter
            y: 38
            spacing: 10
            Repeater {
                model: [["", "#2B579A"], ["", "#30A46C"], ["", "#8E4EC6"]]
                Rectangle {
                    id: tile
                    width: 64
                    height: 66
                    radius: 12
                    color: Theme.dark ? Qt.rgba(1, 1, 1, 0.06) : Qt.rgba(0, 0, 0, 0.04)
                    border.width: 1
                    border.color: Theme.glassRim
                    Text {
                        anchors.centerIn: parent
                        text: modelData[0]
                        font.family: Theme.iconFont
                        font.pixelSize: 28
                        color: modelData[1]
                    }
                    // the middle one floats up, as if being dragged out
                    SequentialAnimation on y {
                        running: index === 1 && root.visible
                        loops: Animation.Infinite
                        PauseAnimation { duration: 700 }
                        NumberAnimation { to: -8; duration: 520; easing.type: Easing.OutCubic }
                        NumberAnimation { to: 0; duration: 520; easing.type: Easing.InOutCubic }
                        PauseAnimation { duration: 900 }
                    }
                }
            }
        }
    }
}
