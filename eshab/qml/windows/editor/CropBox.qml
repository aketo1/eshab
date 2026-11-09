import QtQuick
import Eshab
import "Fmt.js" as Fmt

// What a crop keeps: a box over the dimmed picture, moved by dragging inside it
// and sized by its corners and edges, in the picture's own pixels. With a
// ratio (above 0) only the corners size it, and the shape is kept.
// It fills the stage; the picture's corner is at (originX, originY).
Item {
    id: root

    property real sourceWidth: 1
    property real sourceHeight: 1
    property real scaleFactor: 1
    property real originX: 0
    property real originY: 0
    property real ratio: 0
    property var box: ({ "x": 0, "y": 0, "w": sourceWidth, "h": sourceHeight })
    property bool dragging: false
    readonly property real minSize: Math.max(2, 10 / Math.max(0.001, scaleFactor))
    readonly property real ix: originX
    readonly property real iy: originY
    readonly property real iw: sourceWidth * scaleFactor
    readonly property real ih: sourceHeight * scaleFactor
    readonly property real vx: originX + box.x * scaleFactor
    readonly property real vy: originY + box.y * scaleFactor
    readonly property real vw: box.w * scaleFactor
    readonly property real vh: box.h * scaleFactor
    readonly property color shade: Qt.rgba(0, 0, 0, 0.55)

    anchors.fill: parent

    function reset() {
        box = { "x": 0, "y": 0, "w": sourceWidth, "h": sourceHeight }
        if (ratio > 0)
            fitRatio()
    }

    // The largest box of the ratio, centred where the box is now.
    function fitRatio() {
        if (ratio <= 0 || sourceWidth <= 0 || sourceHeight <= 0)
            return
        let w = Math.min(sourceWidth, sourceHeight * ratio)
        let h = w / ratio
        const cx = box.x + box.w / 2, cy = box.y + box.h / 2
        box = { "x": Fmt.clamp(cx - w / 2, 0, sourceWidth - w), "y": Fmt.clamp(cy - h / 2, 0, sourceHeight - h), "w": w, "h": h }
    }

    function rounded() {
        const x = Math.round(box.x), y = Math.round(box.y)
        return { "x": x, "y": y, "w": Math.min(Math.round(box.w), sourceWidth - x), "h": Math.min(Math.round(box.h), sourceHeight - y) }
    }

    onRatioChanged: fitRatio()
    onSourceWidthChanged: reset()
    onSourceHeightChanged: reset()

    // The picture outside the box, dimmed.
    Rectangle { x: root.ix; y: root.iy; width: root.iw; height: Math.max(0, root.vy - root.iy); color: root.shade }
    Rectangle { x: root.ix; y: root.vy + root.vh; width: root.iw; height: Math.max(0, root.iy + root.ih - root.vy - root.vh); color: root.shade }
    Rectangle { x: root.ix; y: root.vy; width: Math.max(0, root.vx - root.ix); height: root.vh; color: root.shade }
    Rectangle { x: root.vx + root.vw; y: root.vy; width: Math.max(0, root.ix + root.iw - root.vx - root.vw); height: root.vh; color: root.shade }

    Rectangle {
        id: outline
        x: root.vx
        y: root.vy
        width: root.vw
        height: root.vh
        color: "transparent"
        border.width: 2
        border.color: "white"

        // Thirds while it moves, to help place what matters.
        Repeater {
            model: 2
            Rectangle {
                visible: root.dragging
                x: (index + 1) * outline.width / 3
                width: 1
                height: outline.height
                color: Qt.rgba(1, 1, 1, 0.55)
            }
        }
        Repeater {
            model: 2
            Rectangle {
                visible: root.dragging
                y: (index + 1) * outline.height / 3
                height: 1
                width: outline.width
                color: Qt.rgba(1, 1, 1, 0.55)
            }
        }
    }

    // Moving the whole box.
    MouseArea {
        x: root.vx + 10
        y: root.vy + 10
        width: Math.max(0, root.vw - 20)
        height: Math.max(0, root.vh - 20)
        cursorShape: pressed ? Qt.ClosedHandCursor : Qt.OpenHandCursor
        property point from
        property var start
        onPressed: (mouse) => {
            from = mapToItem(root, mouse.x, mouse.y)
            start = Object.assign({}, root.box)
            root.dragging = true
        }
        onPositionChanged: (mouse) => {
            if (!pressed)
                return
            const p = mapToItem(root, mouse.x, mouse.y)
            const dx = (p.x - from.x) / root.scaleFactor, dy = (p.y - from.y) / root.scaleFactor
            root.box = { "x": Fmt.clamp(start.x + dx, 0, root.sourceWidth - start.w),
                         "y": Fmt.clamp(start.y + dy, 0, root.sourceHeight - start.h), "w": start.w, "h": start.h }
        }
        onReleased: root.dragging = false
        onCanceled: root.dragging = false
    }

    // Handles: corners (and edges when the shape is free).
    Repeater {
        model: [
            { "hx": 0, "hy": 0 }, { "hx": 1, "hy": 0 }, { "hx": 0, "hy": 1 }, { "hx": 1, "hy": 1 },
            { "hx": 0.5, "hy": 0 }, { "hx": 0.5, "hy": 1 }, { "hx": 0, "hy": 0.5 }, { "hx": 1, "hy": 0.5 }
        ]
        Item {
            id: handle
            readonly property real hx: modelData.hx
            readonly property real hy: modelData.hy
            readonly property bool corner: hx !== 0.5 && hy !== 0.5
            visible: corner || root.ratio <= 0
            width: 30
            height: 30
            x: root.vx + hx * root.vw - width / 2
            y: root.vy + hy * root.vh - height / 2

            Rectangle {
                anchors.centerIn: parent
                width: handle.corner ? 16 : (handle.hy === 0.5 ? 6 : 22)
                height: handle.corner ? 16 : (handle.hx === 0.5 ? 6 : 22)
                radius: handle.corner ? 8 : 3
                color: "white"
                border.width: 1
                border.color: Qt.rgba(0, 0, 0, 0.35)
            }
            MouseArea {
                anchors.fill: parent
                cursorShape: handle.corner ? ((handle.hx === handle.hy) ? Qt.SizeFDiagCursor : Qt.SizeBDiagCursor)
                                           : (handle.hx === 0.5 ? Qt.SizeVerCursor : Qt.SizeHorCursor)
                property point from
                property var start
                onPressed: (mouse) => {
                    from = mapToItem(root, mouse.x, mouse.y)
                    start = Object.assign({}, root.box)
                    root.dragging = true
                }
                onReleased: root.dragging = false
                onCanceled: root.dragging = false
                onPositionChanged: (mouse) => {
                    if (!pressed)
                        return
                    const p = mapToItem(root, mouse.x, mouse.y)
                    const dx = (p.x - from.x) / root.scaleFactor, dy = (p.y - from.y) / root.scaleFactor
                    const sw = root.sourceWidth, sh = root.sourceHeight, least = root.minSize
                    const s = start
                    if (root.ratio > 0 && handle.corner) {
                        const r = root.ratio
                        const ax = handle.hx === 0 ? s.x + s.w : s.x
                        const ay = handle.hy === 0 ? s.y + s.h : s.y
                        let w = handle.hx === 0 ? ax - (s.x + dx) : (s.x + s.w + dx) - ax
                        let h = handle.hy === 0 ? ay - (s.y + dy) : (s.y + s.h + dy) - ay
                        w = Math.max(w, least)
                        h = Math.max(h, least)
                        if (w / h > r) h = w / r
                        else w = h * r
                        const maxW = handle.hx === 0 ? ax : sw - ax
                        const maxH = handle.hy === 0 ? ay : sh - ay
                        if (w > maxW) { w = maxW; h = w / r }
                        if (h > maxH) { h = maxH; w = h * r }
                        root.box = { "x": handle.hx === 0 ? ax - w : ax, "y": handle.hy === 0 ? ay - h : ay, "w": w, "h": h }
                        return
                    }
                    let left = s.x, top = s.y, right = s.x + s.w, bottom = s.y + s.h
                    if (handle.hx === 0) left = Fmt.clamp(s.x + dx, 0, right - least)
                    if (handle.hx === 1) right = Fmt.clamp(s.x + s.w + dx, left + least, sw)
                    if (handle.hy === 0) top = Fmt.clamp(s.y + dy, 0, bottom - least)
                    if (handle.hy === 1) bottom = Fmt.clamp(s.y + s.h + dy, top + least, sh)
                    root.box = { "x": left, "y": top, "w": right - left, "h": bottom - top }
                }
            }
        }
    }

    // The size the crop will have.
    Rectangle {
        id: sizeTag
        readonly property bool below: root.vy + root.vh + height + 14 < root.height
        x: Fmt.clamp(root.vx + root.vw / 2 - width / 2, 4, Math.max(4, root.width - width - 4))
        y: below ? root.vy + root.vh + 14 : root.vy + root.vh - height - 14
        width: sizeText.implicitWidth + 18
        height: 26
        radius: 13
        color: Qt.rgba(0, 0, 0, 0.62)
        Text {
            id: sizeText
            anchors.centerIn: parent
            readonly property var r: root.rounded()
            text: r.w + " × " + r.h
            color: "white"
            font.family: Theme.fontFamily
            font.pixelSize: 12
        }
    }
}
