import QtQuick
import QtQml.Models
import Eshab

// The files in the order they will be used, rearranged by dragging. As a grid
// (pages of a PDF, videos to join) or as one row under a collage.
GridView {
    id: root

    property real tile: 150
    property bool strip: false
    property bool showNames: !strip
    signal reordered(var order)

    flow: strip ? GridView.FlowTopToBottom : GridView.FlowLeftToRight
    cellWidth: strip ? Math.round(height * 0.86) : tile + 16
    cellHeight: strip ? height : tile + (showNames ? 46 : 16)
    clip: true
    boundsBehavior: Flickable.StopAtBounds

    function order() {
        const out = []
        for (let i = 0; i < visual.items.count; i++)
            out.push(visual.items.get(i).model.modelData.index)
        return out
    }

    // Put the files in this order (a list of their original positions).
    function arrange(target) {
        for (let i = 0; i < target.length; i++) {
            const now = order().indexOf(target[i])
            if (now >= 0 && now !== i)
                visual.items.move(now, i)
        }
    }

    function sortBy(kind) {
        const items = editor.itemList.slice()
        if (kind === "name")
            items.sort((a, b) => String(a.name).localeCompare(String(b.name), undefined, { "numeric": true, "sensitivity": "base" }))
        else
            items.sort((a, b) => a.index - b.index)
        arrange(items.map((item) => item.index))
    }

    model: DelegateModel {
        id: visual
        model: editor.itemList
        delegate: DropArea {
            id: slot
            readonly property int visualIndex: DelegateModel.itemsIndex
            width: root.cellWidth
            height: root.cellHeight
            onEntered: (drag) => {
                if (drag.source && drag.source.visualIndex !== undefined && drag.source.visualIndex !== slot.visualIndex)
                    visual.items.move(drag.source.visualIndex, slot.visualIndex)
            }

            Item {
                id: card
                readonly property int visualIndex: slot.visualIndex
                width: slot.width - (root.strip ? 10 : 16)
                height: slot.height - (root.strip ? 10 : 16)
                anchors.horizontalCenter: slot.horizontalCenter
                anchors.verticalCenter: slot.verticalCenter
                Drag.active: grab.drag.active
                Drag.source: card
                Drag.hotSpot.x: width / 2
                Drag.hotSpot.y: height / 2
                scale: Drag.active ? 1.06 : 1
                Behavior on scale { NumberAnimation { duration: Theme.fast } }

                Rectangle {
                    id: thumb
                    width: parent.width
                    height: root.showNames ? parent.height - 30 : parent.height
                    radius: 12
                    color: Theme.dark ? Qt.rgba(1, 1, 1, 0.06) : Qt.rgba(0, 0, 0, 0.04)
                    border.width: card.Drag.active ? 2 : 1
                    border.color: card.Drag.active ? Theme.accent : Theme.glassRim

                    Image {
                        anchors.fill: parent
                        anchors.margins: 8
                        source: modelData.url
                        fillMode: Image.PreserveAspectFit
                        asynchronous: true
                        cache: false
                        smooth: true
                        mipmap: true
                    }
                    Rectangle {
                        anchors.top: parent.top
                        anchors.left: parent.left
                        anchors.margins: 6
                        width: Math.max(22, number.implicitWidth + 12)
                        height: 22
                        radius: 11
                        color: Theme.accent
                        Text {
                            id: number
                            anchors.centerIn: parent
                            text: slot.visualIndex + 1
                            color: Theme.onAccent
                            font.family: Theme.fontFamily
                            font.pixelSize: 12
                            font.weight: Font.DemiBold
                        }
                    }
                }
                Text {
                    visible: root.showNames
                    anchors.top: thumb.bottom
                    anchors.topMargin: 6
                    width: parent.width
                    horizontalAlignment: Text.AlignHCenter
                    text: modelData.name
                    elide: Text.ElideMiddle
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: 12
                }
                MouseArea {
                    id: grab
                    anchors.fill: parent
                    drag.target: card
                    cursorShape: pressed ? Qt.ClosedHandCursor : Qt.OpenHandCursor
                    onReleased: root.reordered(root.order())
                }
                states: State {
                    when: card.Drag.active
                    ParentChange { target: card; parent: root }
                    AnchorChanges {
                        target: card
                        anchors.horizontalCenter: undefined
                        anchors.verticalCenter: undefined
                    }
                }
            }
        }
    }
}
