import QtQuick
import QtQuick.Effects
import Eshab
import "editor"
import "guide"

// The guide: shown the first time Eshab runs and whenever it is asked for from
// the tray. Four pages: hello (and the material), a try-out of the wheel right
// inside the window, the island and the shelf, and ready.
Window {
    id: win

    property int page: 0
    readonly property int pages: 4
    readonly property string conversionKey: eshab.maskLabel(eshab.setting("conversionWheelDragModifierMask") || "")
    readonly property string toolsKey: eshab.maskLabel(eshab.setting("toolsWheelDragModifierMask") || "")
    readonly property string actionsKey: eshab.maskLabel(eshab.setting("actionsWheelDragModifierMask") || "")

    width: 860
    height: 600
    minimumWidth: 720
    minimumHeight: 540
    color: "transparent"
    flags: Qt.Window | Qt.FramelessWindowHint
    title: eshab.tr("guide.title")

    LayoutMirroring.enabled: eshab.rtl
    LayoutMirroring.childrenInherit: true

    function fill(template, values) {
        let out = String(template)
        for (const key in values)
            out = out.split("{" + key + "}").join(String(values[key]))
        return out
    }
    function go(to) { page = Math.max(0, Math.min(pages - 1, to)) }

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
        opacity: Theme.dark ? 0.5 : 0.2
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
        WindowButton {
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.margins: 10
            z: 5
            kind: "close"
            label: eshab.tr("settings.close")
            onClicked: win.close()
        }

        // -- the pages ---------------------------------------------------------------------
        Item {
            id: pagesArea
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.bottom: footer.top
            anchors.topMargin: 40
            anchors.leftMargin: 40
            anchors.rightMargin: 40

            // 1 · hello
            Page {
                index: 0
                shown: win.page
                Column {
                    anchors.centerIn: parent
                    width: parent.width
                    spacing: 10
                    Logo {
                        anchors.horizontalCenter: parent.horizontalCenter
                        size: 150
                    }
                    Title { text: eshab.tr("guide.hello") }
                    Body { text: eshab.tr("about.tagline") }
                    Item { width: 1; height: 10 }
                    Body { text: eshab.tr("guide.pick"); color: Theme.textSecondary; font.pixelSize: 13 }
                    Row {
                        anchors.horizontalCenter: parent.horizontalCenter
                        spacing: 12
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

            // 2 · try it
            Page {
                index: 1
                shown: win.page
                Column {
                    id: tryColumn
                    anchors.fill: parent
                    spacing: 8
                    Title { text: eshab.tr("guide.try.title") }
                    Body { text: win.fill(eshab.tr("guide.try.body"), { "key": win.conversionKey }) }
                    Body {
                        text: win.fill(eshab.tr("guide.try.more"), { "tools": win.toolsKey, "actions": win.actionsKey })
                        color: Theme.textSecondary
                        font.pixelSize: 13
                    }
                    Item { width: 1; height: 4 }
                    TryOut {
                        objectName: "tryout"
                        width: parent.width
                        height: tryColumn.height - y
                    }
                }
            }

            // 3 · the island and the shelf
            Page {
                index: 2
                shown: win.page
                Row {
                    anchors.centerIn: parent
                    spacing: 36
                    Column {
                        width: (pagesArea.width - 36) / 2
                        spacing: 14
                        IslandSample { anchors.horizontalCenter: parent.horizontalCenter }
                        Title { text: eshab.tr("guide.island.title"); font.pixelSize: 19 }
                        Body { text: eshab.tr("guide.island.body"); font.pixelSize: 13 }
                    }
                    Column {
                        width: (pagesArea.width - 36) / 2
                        spacing: 14
                        ShelfSample { anchors.horizontalCenter: parent.horizontalCenter }
                        Title { text: eshab.tr("guide.shelf.title"); font.pixelSize: 19 }
                        Body { text: eshab.tr("guide.shelf.body"); font.pixelSize: 13 }
                    }
                }
            }

            // 4 · ready
            Page {
                index: 3
                shown: win.page
                Column {
                    anchors.centerIn: parent
                    width: Math.min(parent.width, 480)
                    spacing: 12
                    Logo {
                        anchors.horizontalCenter: parent.horizontalCenter
                        size: 120
                        done: win.page === 3
                        lines: true
                    }
                    Title { text: eshab.tr("guide.ready.title") }
                    Body { text: eshab.tr("guide.ready.body") }
                    Item { width: 1; height: 8 }
                    ESwitch {
                        width: parent.width
                        text: eshab.tr("settings.general.startup")
                        checked: eshab.startup
                        onToggled: (on) => eshab.setStartup(on)
                    }
                    EButton {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: eshab.tr("tray.settings")
                        onClicked: eshab.openSettings()
                    }
                }
            }
        }

        // -- dots and buttons ------------------------------------------------------------------
        Item {
            id: footer
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            anchors.leftMargin: 28
            anchors.rightMargin: 24
            height: 76

            EButton {
                anchors.left: parent.left
                anchors.verticalCenter: parent.verticalCenter
                kind: "quiet"
                text: win.page === 0 ? eshab.tr("guide.skip") : eshab.tr("guide.back")
                onClicked: win.page === 0 ? win.close() : win.go(win.page - 1)
            }
            Row {
                anchors.centerIn: parent
                spacing: 8
                Repeater {
                    model: win.pages
                    Rectangle {
                        width: index === win.page ? 22 : 8
                        height: 8
                        radius: 4
                        color: index === win.page ? Theme.accent : (Theme.dark ? Qt.rgba(1, 1, 1, 0.25) : Qt.rgba(0, 0, 0, 0.18))
                        Behavior on width { NumberAnimation { duration: Theme.base; easing.type: Easing.OutCubic } }
                        MouseArea {
                            anchors.fill: parent
                            anchors.margins: -6
                            cursorShape: Qt.PointingHandCursor
                            onClicked: win.go(index)
                        }
                    }
                }
            }
            EButton {
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                kind: "primary"
                text: win.page === win.pages - 1 ? eshab.tr("guide.start") : eshab.tr("guide.next")
                onClicked: win.page === win.pages - 1 ? win.close() : win.go(win.page + 1)
            }
        }
    }

    // A page fades and slides in from the side it comes from. (An inline
    // component cannot see this file's ids, so the page shown is handed in.)
    component Page: Item {
        id: pageItem
        property int index: 0
        property int shown: 0
        readonly property bool current: shown === index
        readonly property real side: (index < shown ? -1 : 1) * (eshab.rtl ? -1 : 1)
        anchors.fill: parent
        opacity: current ? 1 : 0
        visible: opacity > 0.01
        transform: Translate { x: pageItem.current ? 0 : pageItem.side * 40; Behavior on x { NumberAnimation { duration: Theme.slow; easing.type: Easing.OutCubic } } }
        Behavior on opacity { NumberAnimation { duration: Theme.base } }
    }
    component Title: Text {
        width: parent ? parent.width : 400
        horizontalAlignment: Text.AlignHCenter
        wrapMode: Text.WordWrap
        color: Theme.text
        font.family: Theme.fontFamily
        font.pixelSize: 24
        font.weight: Font.Bold
    }
    component Body: Text {
        width: parent ? parent.width : 400
        horizontalAlignment: Text.AlignHCenter
        wrapMode: Text.WordWrap
        color: Theme.text
        font.family: Theme.fontFamily
        font.pixelSize: 15
        lineHeight: 1.15
    }

    Shortcut { sequence: "Esc"; onActivated: win.close() }
    Shortcut { sequence: "Right"; onActivated: win.go(win.page + (eshab.rtl ? -1 : 1)) }
    Shortcut { sequence: "Left"; onActivated: win.go(win.page + (eshab.rtl ? 1 : -1)) }
}
