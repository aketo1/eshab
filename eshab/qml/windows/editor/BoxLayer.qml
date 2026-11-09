import QtQuick
import Eshab
import "Fmt.js" as Fmt

// Areas to hide, drawn by dragging over the picture, in its own pixels. Each
// shows how it will look: blurred, in big squares or filled with a colour.
// For a video, an area has a start and an end, and it is drawn faintly when
// the video is outside that time.
// It fills the stage; the picture's corner is at (originX, originY), and the
// chosen area's buttons sit in this layer (not inside the area), so they can
// be reached even where they stick out of it.
Item {
    id: root

    property real sourceWidth: 1
    property real sourceHeight: 1
    property real scaleFactor: 1
    property real originX: 0
    property real originY: 0
    property string mode: "blur"
    property color tint: "#1C1C1E"
    property Item pictureItem: null
    property point pictureOffset: Qt.point(0, 0)   // the picture's corner inside pictureItem
    property bool timed: false
    property real time: 0
    property real duration: 0
    property int selected: -1
    property int revision: 0        // bumped on every change, for bindings that read the list
    readonly property int count: areas.count
    readonly property real least: Math.max(2, 8 / Math.max(0.001, scaleFactor))
    property alias boxes: areas
    signal changedByHand()

    anchors.fill: parent
    onChangedByHand: revision++

    function list() {
        const out = []
        for (let i = 0; i < areas.count; i++) {
            const b = areas.get(i)
            const item = { "x": Math.round(b.px), "y": Math.round(b.py), "w": Math.round(b.pw), "h": Math.round(b.ph) }
            if (timed) {
                item.start = Math.round(b.t0 * 1000) / 1000
                item.end = Math.round(b.t1 * 1000) / 1000
            }
            out.push(item)
        }
        return out
    }

    function add(x, y, w, h) {
        x = Fmt.clamp(x, 0, sourceWidth - 1)
        y = Fmt.clamp(y, 0, sourceHeight - 1)
        w = Math.min(w, sourceWidth - x)
        h = Math.min(h, sourceHeight - y)
        areas.append({ "px": x, "py": y, "pw": w, "ph": h, "t0": timed ? time : 0, "t1": timed ? duration : 0 })
        selected = areas.count - 1
        changedByHand()
    }

    function remove(index) {
        if (index < 0 || index >= areas.count)
            return
        areas.remove(index)
        selected = -1
        changedByHand()
    }

    function clear() {
        areas.clear()
        selected = -1
        changedByHand()
    }

    function setTimes(index, start, end) {
        if (index < 0 || index >= areas.count)
            return
        areas.setProperty(index, "t0", Fmt.clamp(start, 0, duration))
        areas.setProperty(index, "t1", Fmt.clamp(end, 0, duration))
        changedByHand()
    }

    ListModel { id: areas }

    // Dragging on the picture draws a new area; a click elsewhere lets go of the chosen one.
    MouseArea {
        id: drawArea
        x: root.originX
        y: root.originY
        width: root.sourceWidth * root.scaleFactor
        height: root.sourceHeight * root.scaleFactor
        cursorShape: Qt.CrossCursor
        property point from
        property bool drawing: false
        onPressed: (mouse) => {
            from = Qt.point(mouse.x, mouse.y)
            drawing = false
            root.selected = -1
        }
        onPositionChanged: (mouse) => {
            if (!pressed)
                return
            if (!drawing && Math.abs(mouse.x - from.x) + Math.abs(mouse.y - from.y) > 6)
                drawing = true
            if (drawing) {
                const x0 = Fmt.clamp(Math.min(from.x, mouse.x), 0, width), y0 = Fmt.clamp(Math.min(from.y, mouse.y), 0, height)
                const x1 = Fmt.clamp(Math.max(from.x, mouse.x), 0, width), y1 = Fmt.clamp(Math.max(from.y, mouse.y), 0, height)
                ghost.x = x0; ghost.y = y0; ghost.width = x1 - x0; ghost.height = y1 - y0
            }
        }
        onReleased: {
            if (drawing && ghost.width / root.scaleFactor >= root.least && ghost.height / root.scaleFactor >= root.least)
                root.add(ghost.x / root.scaleFactor, ghost.y / root.scaleFactor, ghost.width / root.scaleFactor, ghost.height / root.scaleFactor)
            drawing = false
        }
        onCanceled: drawing = false

        Rectangle {
            id: ghost
            visible: drawArea.drawing
            color: Qt.rgba(1, 1, 1, 0.12)
            border.width: 2
            border.color: Theme.accent
        }
    }

    Repeater {
        model: areas
        Item {
            id: area
            readonly property bool chosen: root.selected === index
            readonly property bool showing: !root.timed || (root.time >= model.t0 - 0.001 && root.time <= model.t1 + 0.001)
            x: root.originX + model.px * root.scaleFactor
            y: root.originY + model.py * root.scaleFactor
            width: model.pw * root.scaleFactor
            height: model.ph * root.scaleFactor
            opacity: showing ? 1 : 0.35

            // How it will look.
            ShaderEffectSource {
                anchors.fill: parent
                visible: root.mode !== "solid" && root.pictureItem !== null
                sourceItem: root.pictureItem
                sourceRect: Qt.rect(area.x - root.originX + root.pictureOffset.x, area.y - root.originY + root.pictureOffset.y,
                                    Math.max(1, area.width), Math.max(1, area.height))
                textureSize: root.mode === "pixelate"
                             ? Qt.size(Math.max(1, Math.round(model.pw / 12)), Math.max(1, Math.round(model.ph / 12)))
                             : Qt.size(Math.max(1, Math.round(area.width / 9)), Math.max(1, Math.round(area.height / 9)))
                smooth: root.mode !== "pixelate"
                live: true
            }
            Rectangle {
                anchors.fill: parent
                visible: root.mode === "solid"
                color: root.tint
            }
            Rectangle {
                anchors.fill: parent
                color: "transparent"
                border.width: area.chosen ? 2 : 1
                border.color: area.chosen ? Theme.accent : Qt.rgba(1, 1, 1, 0.85)
            }

            MouseArea {
                anchors.fill: parent
                cursorShape: pressed ? Qt.ClosedHandCursor : Qt.SizeAllCursor
                property point from
                property real sx
                property real sy
                property bool moved: false
                onPressed: (mouse) => {
                    from = mapToItem(root, mouse.x, mouse.y)
                    sx = model.px
                    sy = model.py
                    moved = false
                    root.selected = index
                }
                onPositionChanged: (mouse) => {
                    if (!pressed)
                        return
                    const p = mapToItem(root, mouse.x, mouse.y)
                    const dx = (p.x - from.x) / root.scaleFactor, dy = (p.y - from.y) / root.scaleFactor
                    if (Math.abs(dx) + Math.abs(dy) > 0.5)
                        moved = true
                    model.px = Fmt.clamp(sx + dx, 0, root.sourceWidth - model.pw)
                    model.py = Fmt.clamp(sy + dy, 0, root.sourceHeight - model.ph)
                }
                onReleased: if (moved) root.changedByHand()
            }
        }
    }

    // The chosen area's own buttons: remove it, and size it from its far corner.
    Item {
        id: chrome
        readonly property bool on: root.selected >= 0 && root.selected < areas.count && root.revision >= 0
        readonly property var b: on ? areas.get(root.selected) : null
        visible: on && b !== null
        x: b ? root.originX + b.px * root.scaleFactor : 0
        y: b ? root.originY + b.py * root.scaleFactor : 0
        width: b ? b.pw * root.scaleFactor : 0
        height: b ? b.ph * root.scaleFactor : 0
    }
    Rectangle {
        visible: chrome.visible
        width: 16
        height: 16
        radius: 8
        x: chrome.x + chrome.width - width / 2
        y: chrome.y + chrome.height - height / 2
        color: "white"
        border.width: 1
        border.color: Qt.rgba(0, 0, 0, 0.35)
        MouseArea {
            anchors.fill: parent
            cursorShape: Qt.SizeFDiagCursor
            property point from
            property real sw
            property real sh
            onPressed: (mouse) => {
                from = mapToItem(root, mouse.x, mouse.y)
                sw = chrome.b.pw
                sh = chrome.b.ph
            }
            onPositionChanged: (mouse) => {
                if (!pressed || !chrome.b)
                    return
                const p = mapToItem(root, mouse.x, mouse.y)
                areas.setProperty(root.selected, "pw", Fmt.clamp(sw + (p.x - from.x) / root.scaleFactor, root.least, root.sourceWidth - chrome.b.px))
                areas.setProperty(root.selected, "ph", Fmt.clamp(sh + (p.y - from.y) / root.scaleFactor, root.least, root.sourceHeight - chrome.b.py))
            }
            onReleased: root.changedByHand()
        }
    }
    Rectangle {
        visible: chrome.visible
        width: 26
        height: 26
        radius: 13
        x: chrome.x + chrome.width - width / 2
        y: chrome.y - height / 2
        color: "#E5484D"
        border.width: 2
        border.color: "white"
        Text {
            anchors.centerIn: parent
            text: ""
            font.family: Theme.iconFont
            font.pixelSize: 10
            color: "white"
        }
        MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: root.remove(root.selected)
        }
    }
}
