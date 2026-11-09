import QtQuick
import Eshab

// The island as it looks at the top of the screen, filling as a job runs.
Rectangle {
    id: root

    property real progress: 0

    width: 300
    height: 150
    radius: 18
    color: Theme.dark ? Qt.rgba(1, 1, 1, 0.04) : Qt.rgba(0, 0, 0, 0.03)
    border.width: 1
    border.color: Theme.glassRim
    clip: true

    SequentialAnimation on progress {
        running: root.visible
        loops: Animation.Infinite
        NumberAnimation { from: 0; to: 1; duration: 2800; easing.type: Easing.InOutSine }
        PauseAnimation { duration: 900 }
    }

    // the top edge of a screen
    Rectangle {
        width: parent.width
        height: 6
        color: Theme.dark ? Qt.rgba(1, 1, 1, 0.08) : Qt.rgba(0, 0, 0, 0.06)
    }
    Rectangle {
        anchors.horizontalCenter: parent.horizontalCenter
        y: 16
        width: 236
        height: 38
        radius: 19
        color: Theme.dark ? "#26262B" : "#FFFFFF"
        border.width: 1
        border.color: Theme.glassRim
        Row {
            anchors.verticalCenter: parent.verticalCenter
            anchors.left: parent.left
            anchors.leftMargin: 12
            spacing: 9
            Logo {
                anchors.verticalCenter: parent.verticalCenter
                size: 24
                alive: false
                progress: root.progress < 0.999 ? root.progress : -1
                done: root.progress >= 0.999
            }
            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: root.progress < 0.999 ? "PDF" : eshab.tr("toast.done")
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: 13
                font.weight: Font.DemiBold
            }
        }
        Text {
            anchors.right: parent.right
            anchors.rightMargin: 14
            anchors.verticalCenter: parent.verticalCenter
            text: Math.round(root.progress * 100) + "%"
            color: Theme.textSecondary
            font.family: Theme.fontFamily
            font.pixelSize: 12
        }
    }
    // a window under it, still clickable
    Rectangle {
        x: 24
        y: 72
        width: parent.width - 48
        height: 64
        radius: 10
        color: Theme.dark ? Qt.rgba(1, 1, 1, 0.05) : Qt.rgba(1, 1, 1, 0.7)
        border.width: 1
        border.color: Theme.glassRim
    }
}
