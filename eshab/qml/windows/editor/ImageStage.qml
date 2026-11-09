import QtQuick
import Eshab
import "Fmt.js" as Fmt

// The photo as the tool will leave it. A live tool redraws it as its options
// change; on an edited or compressed photo a line splits it into the original
// and the result, dragged anywhere across the picture to compare. A collage
// shows its photos in a strip to put them in order, and the details tools
// list what the file says about itself.
Item {
    id: root

    property var host
    readonly property bool ready: picture.ready || editor.itemList.length > 0
    readonly property bool collage: editor.toolKey === "img.collage"
    readonly property bool details: host.spec.mode === "metadata"
    readonly property bool comparable: (editor.toolKey === "img.edit" || editor.toolKey === "img.compress")
                                         && editor.previewUrl !== "" && editor.sourceUrl !== ""
    property real split: 0.5          // where the line stands across the picture, 0..1

    function stateObject() {
        return collage ? { "order": strip.order() } : {}
    }

    Item {
        id: view
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: root.collage ? strip.top : (root.details ? info.top : parent.bottom)
        anchors.bottomMargin: root.collage || root.details ? 8 : 0

        Checker {
            x: picture.x + (picture.width - picture.paintedWidth) / 2
            y: picture.y + (picture.height - picture.paintedHeight) / 2
            width: picture.paintedWidth
            height: picture.paintedHeight
            visible: picture.ready
        }
        SmoothImage {
            id: picture
            anchors.fill: parent
            anchors.margins: 22
            source: editor.previewUrl !== "" ? editor.previewUrl : editor.sourceUrl
        }

        // Before | after: the original shows on one side of the line.
        Item {
            id: painted
            x: picture.x + (picture.width - picture.paintedWidth) / 2
            y: picture.y + (picture.height - picture.paintedHeight) / 2
            width: picture.paintedWidth
            height: picture.paintedHeight
            visible: root.comparable && picture.ready
            LayoutMirroring.enabled: false
            LayoutMirroring.childrenInherit: true

            Item {
                width: parent.width * root.split
                height: parent.height
                clip: true
                SmoothImage {
                    width: painted.width
                    height: painted.height
                    fillMode: Image.Stretch
                    source: editor.sourceUrl
                }
            }
            Rectangle {
                x: parent.width * root.split - 1
                width: 2
                height: parent.height
                color: "white"
                opacity: 0.92
            }
            Rectangle {
                x: parent.width * root.split - width / 2
                y: parent.height / 2 - height / 2
                width: 34
                height: 34
                radius: 17
                color: "white"
                scale: drag.pressed ? 1.12 : 1
                Behavior on scale { NumberAnimation { duration: 120 } }
                Text {
                    anchors.centerIn: parent
                    text: "  "
                    font.family: Theme.iconFont
                    font.pixelSize: 9
                    color: "#1C1C1E"
                }
            }
            Repeater {
                model: [["ed.before", 0], ["ed.after", 1]]
                Rectangle {
                    required property var modelData
                    x: modelData[1] === 0 ? 10 : painted.width - width - 10
                    y: 10
                    width: tag.implicitWidth + 18
                    height: 24
                    radius: 12
                    color: Qt.rgba(0, 0, 0, 0.55)
                    Text {
                        id: tag
                        anchors.centerIn: parent
                        text: root.host.word(modelData[0])
                        color: "white"
                        font.family: Theme.fontFamily
                        font.pixelSize: 12
                    }
                }
            }
            MouseArea {
                id: drag
                anchors.fill: parent
                cursorShape: Qt.SizeHorCursor
                onPressed: (mouse) => root.split = Math.max(0, Math.min(1, mouse.x / width))
                onPositionChanged: (mouse) => { if (pressed) root.split = Math.max(0, Math.min(1, mouse.x / width)) }
            }
        }
        Rectangle {
            visible: root.comparable && picture.ready
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 2
            width: holdText.implicitWidth + 22
            height: 24
            radius: 12
            color: Qt.rgba(0, 0, 0, 0.55)
            Text {
                id: holdText
                anchors.centerIn: parent
                text: root.host.word("ed.compare")
                color: "white"
                font.family: Theme.fontFamily
                font.pixelSize: 12
            }
        }
        Text {
            anchors.centerIn: parent
            visible: !picture.ready && editor.sourceUrl === "" && editor.previewUrl === "" && !root.collage
            text: root.host.word("ed.no_preview")
            color: Theme.textSecondary
            font.family: Theme.fontFamily
            font.pixelSize: 14
        }
    }

    InfoList {
        id: info
        visible: root.details
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.margins: 10
        height: root.details ? Math.min(parent.height * 0.38, contentHeight + 4) : 0
        rows: editor.infoRows
    }

    OrderStrip {
        id: strip
        visible: root.collage
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.margins: 10
        height: root.collage ? 118 : 0
        onReordered: (order) => {
            editor.setOrder(JSON.stringify(order))
            root.host.refreshPreview()
        }
    }
}
