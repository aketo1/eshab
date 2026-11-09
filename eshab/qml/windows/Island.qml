import QtQuick
import QtQuick.Effects
import Eshab

// The activity island (eshab/activity.py): a liquid-glass capsule at the top
// centre that opens into the list of jobs when you rest the pointer on it.
// Files parked on the shelf live here too, as tiles to drag out.
// The window stays put; only the painted shape grows and shrinks.
Window {
    id: win

    required property var island

    width: 460
    height: 720
    color: "transparent"
    title: "Eshab"
    flags: Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus
           | Qt.NoDropShadowWindowHint | Qt.WindowTransparentForInput

    LayoutMirroring.enabled: eshab.rtl
    LayoutMirroring.childrenInherit: true

    readonly property bool open: island.state === "expanded"
    readonly property bool shown: island.state !== "hidden"
    readonly property var head: island.headline
    readonly property var parked: island.shelf
    readonly property var recentFiles: island.recent
    readonly property bool shelfOnly: island.cards.length === 0 && parked.length > 0

    function percent(value) { return Math.round(Math.max(0, Math.min(1, value)) * 100) + "%" }

    // The capsule's geometry, springing between compact and open.
    Item {
        id: shape
        x: (win.width - width) / 2
        y: 8
        width: win.island.islandWidth
        height: win.island.islandHeight
        property real radius: win.open ? 22 : height / 2
        Behavior on width { SpringAnimation { spring: 4.4; damping: 0.38; epsilon: 0.3 } }
        Behavior on height { SpringAnimation { spring: 4.4; damping: 0.38; epsilon: 0.3 } }
        Behavior on radius { NumberAnimation { duration: 200 } }
    }

    Item {
        id: surface
        anchors.fill: parent
        opacity: win.shown ? 1 : 0
        scale: win.shown ? 1 : 0.5
        transformOrigin: Item.Top
        Behavior on opacity { NumberAnimation { duration: 180 } }
        Behavior on scale { SpringAnimation { spring: 5; damping: 0.32; epsilon: 0.005 } }

        // Soft shadow under the capsule.
        Item {
            id: shadowSource
            x: shape.x - 24
            y: shape.y - 18
            width: shape.width + 48
            height: shape.height + 48
            visible: false
            layer.enabled: true
            Rectangle {
                x: 24; y: 22; width: shape.width; height: shape.height; radius: shape.radius
                color: "black"
            }
        }
        MultiEffect {
            anchors.fill: shadowSource
            source: shadowSource
            blurEnabled: true
            blurMax: 24
            blur: 1
            opacity: Theme.dark ? 0.55 : 0.25
        }

        // Glass: the blurred wallpaper under the window, tinted, cut to the capsule.
        Item {
            id: glass
            anchors.fill: parent
            visible: false
            layer.enabled: true
            Rectangle { anchors.fill: parent; color: Theme.dark ? "#1E1E22" : "#F2F2F4" }
            Image {
                source: eshab.backdrop
                x: Screen.virtualX - win.x
                y: Screen.virtualY - win.y
                width: Screen.width
                height: Screen.height
                visible: source.toString() !== ""
            }
            Rectangle {
                anchors.fill: parent
                color: Theme.dark ? Qt.rgba(0.07, 0.07, 0.09, 0.66) : Qt.rgba(0.99, 0.99, 1.0, 0.60)
            }
        }
        Item {
            id: mask
            anchors.fill: parent
            visible: false
            layer.enabled: true
            Rectangle { x: shape.x; y: shape.y; width: shape.width; height: shape.height; radius: shape.radius }
        }
        MultiEffect {
            anchors.fill: parent
            source: glass
            maskEnabled: true
            maskSource: mask
        }
        Rectangle {
            x: shape.x; y: shape.y; width: shape.width; height: shape.height; radius: shape.radius
            color: "transparent"
            border.width: 1
            border.color: Theme.glassRim
        }

        // Compact: one line about the job that matters most.
        Row {
            id: compact
            x: shape.x + 12
            width: shape.width - 24
            height: 38
            y: shape.y
            spacing: 9
            opacity: win.open || win.shelfOnly ? 0 : 1
            visible: opacity > 0.01
            Behavior on opacity { NumberAnimation { duration: 120 } }

            Item {
                width: 26
                height: 38
                Logo {
                    anchors.centerIn: parent
                    size: 26
                    alive: false
                    visible: win.head.state !== "error"
                    progress: win.head.state === "working" ? (win.head.progress >= 0 ? win.head.progress : 0.35) : -1
                    done: win.head.state === "done"
                }
                Rectangle {
                    anchors.centerIn: parent
                    visible: win.head.state === "error"
                    width: 10; height: 10; radius: 5
                    color: "#E5484D"
                }
            }
            Text {
                anchors.verticalCenter: parent.verticalCenter
                width: compact.width - 26 - tail.width - 2 * compact.spacing
                elide: Text.ElideRight
                text: win.head.state === "error" ? eshab.tr("toast.failed")
                      : win.head.state === "done" ? eshab.tr("toast.done") + (win.head.detail ? " · " + win.head.detail : " · " + win.head.title)
                      : (win.head.title || "")
                color: win.head.state === "error" ? "#E5484D" : Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: 13
                font.weight: Font.DemiBold
            }
            Text {
                id: tail
                anchors.verticalCenter: parent.verticalCenter
                text: win.head.state === "working"
                      ? (win.island.others > 0 ? "+" + win.island.others + "  " : "") + (win.head.progress >= 0 ? win.percent(win.head.progress) : "")
                      : ""
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: 12
            }
        }

        // Compact, with only parked files: a peek of them and how many.
        Row {
            id: shelfCompact
            x: shape.x + 12
            y: shape.y
            height: 38
            spacing: 8
            opacity: !win.open && win.shelfOnly ? 1 : 0
            visible: opacity > 0.01
            Behavior on opacity { NumberAnimation { duration: 120 } }

            Item {
                width: 22 + Math.min(3, win.parked.length) * 7
                height: 38
                Repeater {
                    model: Math.min(3, win.parked.length)
                    Rectangle {
                        required property int index
                        readonly property var file: win.parked[win.parked.length - 1 - index]
                        x: index * 7
                        anchors.verticalCenter: parent.verticalCenter
                        width: 22
                        height: 22
                        radius: 6
                        rotation: (index - 1) * 7
                        color: Theme.dark ? "#2C2C31" : "#FFFFFF"
                        border.width: 1
                        border.color: Theme.glassRim
                        Image {
                            anchors.fill: parent
                            anchors.margins: 2
                            source: parent.file ? parent.file.url : ""
                            sourceSize: Qt.size(48, 48)
                            fillMode: Image.PreserveAspectFit
                            asynchronous: true
                        }
                    }
                }
            }
            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: eshab.tr("action.file_shelf") + " · " + win.parked.length
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: 13
                font.weight: Font.DemiBold
            }
        }

        // Open: every job with its own controls.
        Column {
            id: list
            x: shape.x + 14
            y: shape.y + 14
            width: shape.width - 28
            opacity: win.open ? 1 : 0
            visible: opacity > 0.01
            Behavior on opacity { NumberAnimation { duration: 160 } }

            Repeater {
                model: win.island.cards
                delegate: Item {
                    id: row
                    required property var modelData
                    readonly property bool working: modelData.state === "working"
                    readonly property bool failed: modelData.state === "error"
                    readonly property bool finished: modelData.state === "done"
                    width: list.width
                    height: 58

                    Logo {
                        id: mark
                        anchors.left: parent.left
                        anchors.verticalCenter: parent.verticalCenter
                        size: 32
                        alive: false
                        visible: !row.failed
                        progress: row.working ? (row.modelData.progress >= 0 ? row.modelData.progress : 0.35) : -1
                        done: row.finished
                    }
                    Rectangle {
                        anchors.centerIn: mark
                        visible: row.failed
                        width: 12; height: 12; radius: 6
                        color: "#E5484D"
                    }
                    Column {
                        anchors.left: mark.right
                        anchors.leftMargin: 10
                        anchors.right: buttons.left
                        anchors.rightMargin: 8
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 3
                        Text {
                            width: parent.width
                            text: row.failed ? eshab.tr("toast.failed") + " · " + row.modelData.title : row.modelData.title
                            color: row.failed ? "#E5484D" : Theme.text
                            elide: Text.ElideRight
                            font.family: Theme.fontFamily
                            font.pixelSize: 13
                            font.weight: Font.DemiBold
                        }
                        Text {
                            width: parent.width
                            text: row.modelData.detail
                            color: Theme.textSecondary
                            elide: Text.ElideMiddle
                            font.family: Theme.fontFamily
                            font.pixelSize: 12
                        }
                        Rectangle {
                            visible: row.working
                            width: parent.width
                            height: 4
                            radius: 2
                            color: Theme.dark ? Qt.rgba(1, 1, 1, 0.12) : Qt.rgba(0, 0, 0, 0.08)
                            Rectangle {
                                width: parent.width * Math.max(0.04, row.modelData.progress)
                                height: parent.height
                                radius: 2
                                color: Theme.accent
                                Behavior on width { NumberAnimation { duration: 160 } }
                            }
                        }
                    }
                    Row {
                        id: buttons
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 6
                        Repeater {
                            model: row.working ? [["toast.cancel", "cancel"]]
                                 : row.finished && row.modelData.output ? [["toast.show", "reveal"], ["toast.open", "open"]]
                                 : row.failed ? [["toast.dismiss", "dismiss"]] : []
                            delegate: Rectangle {
                                required property var modelData
                                readonly property bool primary: modelData[1] === "open"
                                width: caption.implicitWidth + 20
                                height: 28
                                radius: 14
                                color: primary ? Theme.accent
                                       : (Theme.dark ? Qt.rgba(1, 1, 1, hit.containsMouse ? 0.16 : 0.10)
                                                     : Qt.rgba(0, 0, 0, hit.containsMouse ? 0.10 : 0.06))
                                Text {
                                    id: caption
                                    anchors.centerIn: parent
                                    text: eshab.tr(modelData[0])
                                    color: parent.primary ? Theme.onAccent : Theme.text
                                    font.family: Theme.fontFamily
                                    font.pixelSize: 12
                                    font.weight: Font.DemiBold
                                }
                                MouseArea {
                                    id: hit
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: win.island[modelData[1]](row.modelData.id)
                                }
                            }
                        }
                    }
                }
            }

            // The shelf: parked files, each a tile to drag anywhere.
            Item {
                width: list.width
                height: 8
                visible: win.island.cards.length > 0 && win.parked.length > 0
            }
            Item {
                id: shelfPart
                visible: win.parked.length > 0
                width: list.width
                height: win.island.shelfHeight

                Item {
                    id: shelfHead
                    width: parent.width
                    height: 34
                    Text {
                        anchors.left: parent.left
                        anchors.right: shelfButtons.left
                        anchors.rightMargin: 8
                        anchors.verticalCenter: parent.verticalCenter
                        text: eshab.tr("action.file_shelf") + " · " + win.parked.length
                        color: Theme.text
                        elide: Text.ElideRight
                        font.family: Theme.fontFamily
                        font.pixelSize: 13
                        font.weight: Font.DemiBold
                    }
                    Row {
                        id: shelfButtons
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 6
                        // Dragged, not clicked: every parked file at once.
                        Rectangle {
                            visible: win.parked.length > 1
                            width: allText.implicitWidth + 22
                            height: 28
                            radius: 14
                            color: Theme.accent
                            Text {
                                id: allText
                                anchors.centerIn: parent
                                text: eshab.tr("shelf.drag_all")
                                color: Theme.onAccent
                                font.family: Theme.fontFamily
                                font.pixelSize: 12
                                font.weight: Font.DemiBold
                            }
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.OpenHandCursor
                                property point from
                                property bool started: false
                                onPressed: (mouse) => { from = Qt.point(mouse.x, mouse.y); started = false }
                                onPositionChanged: (mouse) => {
                                    if (!pressed || started || Math.abs(mouse.x - from.x) + Math.abs(mouse.y - from.y) < 6)
                                        return
                                    started = true
                                    win.island.dragOut(JSON.stringify(win.parked.map((f) => f.path)))
                                }
                            }
                        }
                        Rectangle {
                            width: clearText.implicitWidth + 22
                            height: 28
                            radius: 14
                            color: Theme.dark ? Qt.rgba(1, 1, 1, clearHit.containsMouse ? 0.16 : 0.10)
                                              : Qt.rgba(0, 0, 0, clearHit.containsMouse ? 0.10 : 0.06)
                            Text {
                                id: clearText
                                anchors.centerIn: parent
                                text: eshab.tr("shelf.clear")
                                color: Theme.text
                                font.family: Theme.fontFamily
                                font.pixelSize: 12
                                font.weight: Font.DemiBold
                            }
                            MouseArea {
                                id: clearHit
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: win.island.clearShelf()
                            }
                        }
                    }
                }

                GridView {
                    id: tiles
                    y: shelfHead.height
                    width: parent.width
                    height: parent.height - shelfHead.height
                    cellWidth: Math.floor(width / 4)
                    cellHeight: 96
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    interactive: contentHeight > height
                    model: win.parked
                    delegate: Item {
                        id: tile
                        required property var modelData
                        width: tiles.cellWidth
                        height: tiles.cellHeight

                        Rectangle {
                            anchors.fill: parent
                            anchors.margins: 3
                            radius: 12
                            color: grab.containsMouse ? (Theme.dark ? Qt.rgba(1, 1, 1, 0.08) : Qt.rgba(0, 0, 0, 0.05)) : "transparent"
                            border.width: grab.containsMouse ? 1 : 0
                            border.color: Theme.glassRim
                        }
                        Image {
                            anchors.horizontalCenter: parent.horizontalCenter
                            y: 10
                            width: 50
                            height: 50
                            source: tile.modelData.url
                            sourceSize: Qt.size(100, 100)
                            fillMode: Image.PreserveAspectFit
                            asynchronous: true
                            smooth: true
                        }
                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            y: 66
                            width: parent.width - 12
                            horizontalAlignment: Text.AlignHCenter
                            text: tile.modelData.name
                            elide: Text.ElideMiddle
                            color: Theme.text
                            font.family: Theme.fontFamily
                            font.pixelSize: 11
                        }
                        MouseArea {
                            id: grab
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.OpenHandCursor
                            property point from
                            property bool started: false
                            onPressed: (mouse) => { from = Qt.point(mouse.x, mouse.y); started = false }
                            onPositionChanged: (mouse) => {
                                if (!pressed || started || Math.abs(mouse.x - from.x) + Math.abs(mouse.y - from.y) < 6)
                                    return
                                started = true
                                win.island.dragOut(JSON.stringify([tile.modelData.path]))
                            }
                            onDoubleClicked: win.island.revealShelved(tile.modelData.path)
                        }
                        // Remove it from the shelf (the file itself stays where it is).
                        Rectangle {
                            visible: grab.containsMouse || removeHit.containsMouse
                            anchors.top: parent.top
                            anchors.right: parent.right
                            anchors.margins: 6
                            width: 20
                            height: 20
                            radius: 10
                            color: Theme.dark ? "#3A3A40" : "#FFFFFF"
                            border.width: 1
                            border.color: Theme.glassRim
                            Text {
                                anchors.centerIn: parent
                                text: "\uE711"
                                font.family: Theme.iconFont
                                font.pixelSize: 8
                                color: Theme.text
                            }
                            MouseArea {
                                id: removeHit
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: win.island.unshelve(tile.modelData.path)
                            }
                        }
                    }
                }
            }

            // Recent files: what Eshab made lately. Click opens, drag copies it out.
            Item {
                width: list.width
                height: 8
                visible: win.recentFiles.length > 0 && (win.island.cards.length > 0 || win.parked.length > 0)
            }
            Item {
                id: recentPart
                visible: win.recentFiles.length > 0
                width: list.width
                height: win.island.recentHeight

                Item {
                    id: recentHead
                    width: parent.width
                    height: 34
                    Text {
                        anchors.left: parent.left
                        anchors.right: recentClear.left
                        anchors.rightMargin: 8
                        anchors.verticalCenter: parent.verticalCenter
                        text: eshab.tr("recent.title")
                        color: Theme.text
                        elide: Text.ElideRight
                        font.family: Theme.fontFamily
                        font.pixelSize: 13
                        font.weight: Font.DemiBold
                    }
                    Rectangle {
                        id: recentClear
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        width: recentClearText.implicitWidth + 22
                        height: 28
                        radius: 14
                        color: Theme.dark ? Qt.rgba(1, 1, 1, recentClearHit.containsMouse ? 0.16 : 0.10)
                                          : Qt.rgba(0, 0, 0, recentClearHit.containsMouse ? 0.10 : 0.06)
                        Text {
                            id: recentClearText
                            anchors.centerIn: parent
                            text: eshab.tr("recent.clear")
                            color: Theme.text
                            font.family: Theme.fontFamily
                            font.pixelSize: 12
                            font.weight: Font.DemiBold
                        }
                        MouseArea {
                            id: recentClearHit
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: win.island.clearRecent()
                        }
                    }
                }

                GridView {
                    id: recentTiles
                    y: recentHead.height
                    width: parent.width
                    height: parent.height - recentHead.height
                    cellWidth: Math.floor(width / 4)
                    cellHeight: 96
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    interactive: contentHeight > height
                    model: win.recentFiles
                    delegate: Item {
                        id: recentTile
                        required property var modelData
                        width: recentTiles.cellWidth
                        height: recentTiles.cellHeight

                        Rectangle {
                            anchors.fill: parent
                            anchors.margins: 3
                            radius: 12
                            color: recentGrab.containsMouse ? (Theme.dark ? Qt.rgba(1, 1, 1, 0.08) : Qt.rgba(0, 0, 0, 0.05)) : "transparent"
                            border.width: recentGrab.containsMouse ? 1 : 0
                            border.color: Theme.glassRim
                        }
                        Image {
                            anchors.horizontalCenter: parent.horizontalCenter
                            y: 10
                            width: 50
                            height: 50
                            source: recentTile.modelData.url
                            sourceSize: Qt.size(100, 100)
                            fillMode: Image.PreserveAspectFit
                            asynchronous: true
                            smooth: true
                        }
                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            y: 66
                            width: parent.width - 12
                            horizontalAlignment: Text.AlignHCenter
                            text: recentTile.modelData.name
                            elide: Text.ElideMiddle
                            color: Theme.text
                            font.family: Theme.fontFamily
                            font.pixelSize: 11
                        }
                        MouseArea {
                            id: recentGrab
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            property point from
                            property bool started: false
                            onPressed: (mouse) => { from = Qt.point(mouse.x, mouse.y); started = false }
                            onPositionChanged: (mouse) => {
                                if (!pressed || started || Math.abs(mouse.x - from.x) + Math.abs(mouse.y - from.y) < 6)
                                    return
                                started = true
                                win.island.dragOut(JSON.stringify([recentTile.modelData.path]))
                            }
                            onClicked: if (!started) win.island.openRecent(recentTile.modelData.path)
                        }
                        // Show it in its folder.
                        Rectangle {
                            visible: recentGrab.containsMouse || revealHit.containsMouse
                            anchors.top: parent.top
                            anchors.right: parent.right
                            anchors.margins: 6
                            width: 20
                            height: 20
                            radius: 10
                            color: Theme.dark ? "#3A3A40" : "#FFFFFF"
                            border.width: 1
                            border.color: Theme.glassRim
                            Text {
                                anchors.centerIn: parent
                                text: ""
                                font.family: Theme.iconFont
                                font.pixelSize: 9
                                color: Theme.text
                            }
                            MouseArea {
                                id: revealHit
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: win.island.revealShelved(recentTile.modelData.path)
                            }
                        }
                    }
                }
            }
        }
    }
}
