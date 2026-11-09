import QtQuick
import QtQuick.Effects
import Eshab

// «عن اسحب»: the mark, the name, and the three materials to choose from.
Window {
    id: win

    width: 440
    height: 540
    color: "transparent"
    flags: Qt.Window | Qt.FramelessWindowHint
    title: eshab.tr("tray.about")

    LayoutMirroring.enabled: eshab.rtl
    LayoutMirroring.childrenInherit: true

    Rectangle {
        id: shadowShape
        anchors.fill: card
        radius: card.radius
        color: "black"
        visible: false
        layer.enabled: true
    }
    MultiEffect {
        anchors.fill: shadowShape
        source: shadowShape
        blurEnabled: true
        blurMax: 32
        blur: 1.0
        opacity: Theme.dark ? 0.55 : 0.22
        anchors.topMargin: 6
        anchors.bottomMargin: -6
    }

    Backdrop {
        id: card
        anchors.fill: parent
        anchors.margins: 18
        window: win
        radius: 24

        DragHandler {
            target: null
            onActiveChanged: if (active) win.startSystemMove()
        }

        // Mirrored for Arabic: the caption button sits on the left, like
        // every right-to-left Windows title bar.
        WindowButton {
            anchors.top: parent.top
            anchors.right: parent.right
            anchors.margins: 8
            kind: "close"
            label: eshab.tr("window.close")
            onClicked: win.close()
        }

        Column {
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.top: parent.top
            anchors.topMargin: 46
            spacing: 6

            Logo {
                anchors.horizontalCenter: parent.horizontalCenter
                size: 150
            }
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: "اسحب"
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: 34
                font.weight: Font.Bold
            }
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                width: 320
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                text: eshab.tr("about.tagline")
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: 15
            }
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: eshab.version
                color: Theme.textSecondary
                opacity: 0.8
                font.family: Theme.fontFamily
                font.pixelSize: 12
            }
            Item { width: 1; height: 22 }
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: eshab.tr("about.material")
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: 13
            }
            Row {
                anchors.horizontalCenter: parent.horizontalCenter
                spacing: 10
                Repeater {
                    model: ["honey", "clear", "ink"]
                    MaterialJar {
                        material: modelData
                        label: eshab.tr("material." + modelData)
                        selected: Theme.material === modelData
                        onPicked: eshab.setMaterial(modelData)
                    }
                }
            }
        }
    }

    Shortcut { sequence: "Esc"; onActivated: win.close() }
}
