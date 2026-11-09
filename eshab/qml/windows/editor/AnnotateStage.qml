import QtQuick
import Eshab
import "Fmt.js" as Fmt

// Draw on a photo: arrows, pen strokes, boxes, circles, highlights and words.
// Marks are kept in the photo's own pixels and drawn here exactly as
// eshab/annotate.py draws them on the saved copy.
Item {
    id: root

    property var host
    property var marks: []
    property var redone: []
    property var drawing: null
    // The text mark the panel edits: the one just placed, or one clicked.
    property int chosen: -1
    property var seen: ({})
    readonly property bool ready: marks.length > 0
    readonly property string kind: String(host.options.mark || "arrow")
    readonly property string ink: String(host.options.color || "#F87800")
    // Thickness and text size follow the photo's size, so a mark looks the
    // same on a small screenshot and on a large photo.
    readonly property real unit: Math.max(1, Math.max(frame.sourceWidth, frame.sourceHeight) / 1200)
    readonly property real thickness: Number(host.options.width || 6) * unit
    readonly property real textSize: Number(host.options.text_size || 48) * unit

    function stateObject() {
        return { "marks": marks }
    }

    function add(op) {
        marks = marks.concat([op])
        redone = []
        chosen = op.type === "text" ? marks.length - 1 : -1
    }

    // A text mark's box, from where it was placed: Arabic grows leftward from
    // its right edge, other words rightward from their left edge.
    function laidOut(mark) {
        measure.font.pixelSize = Math.max(6, Math.floor(mark.size))
        measure.text = mark.text
        const wide = measure.advanceWidth + mark.size * 0.4 + 8
        const tall = mark.size * 1.6 + 4
        const rtl = Fmt.hasArabic(mark.text)
        const anchor = mark.anchor !== undefined ? mark.anchor : (rtl ? mark.x2 : mark.x1)
        let x1 = Fmt.clamp(rtl ? anchor - wide : anchor, 0, Math.max(0, frame.sourceWidth - 1))
        const next = Object.assign({}, mark)
        next.anchor = anchor
        next.x1 = x1
        next.x2 = Math.min(frame.sourceWidth, x1 + wide)
        next.y2 = Math.min(frame.sourceHeight, mark.y1 + tall * 4)
        return next
    }

    function replace(index, mark) {
        const next = marks.slice()
        next[index] = mark
        marks = next
    }

    function choose(index) {
        chosen = index
        const mark = marks[index]
        // The panel shows what the mark has, so editing it starts from there.
        root.host.setOption("text", mark.text)
        root.host.setOption("color", mark.color)
        root.host.setOption("text_size", Math.round(mark.size / unit))
    }

    function textAt(x, y) {
        for (let i = marks.length - 1; i >= 0; i--) {
            const m = marks[i]
            if (m.type === "text" && x >= m.x1 && x <= m.x2 && y >= m.y1 && y <= m.y1 + m.size * 1.6)
                return i
        }
        return -1
    }

    function deleteSelected() {
        if (chosen < 0 || chosen >= marks.length)
            return
        marks = marks.filter((m, i) => i !== chosen)
        chosen = -1
    }

    function undo() {
        if (typing.visible) { typing.cancel(); return }
        if (!marks.length)
            return
        redone = redone.concat([marks[marks.length - 1]])
        marks = marks.slice(0, marks.length - 1)
        if (chosen >= marks.length) chosen = -1
    }

    function redo() {
        if (!redone.length)
            return
        marks = marks.concat([redone[redone.length - 1]])
        redone = redone.slice(0, redone.length - 1)
    }

    function dismiss() {
        if (typing.visible) {
            typing.cancel()
            return true
        }
        return false
    }

    onMarksChanged: paper.requestPaint()
    onDrawingChanged: paper.requestPaint()

    // The panel edits the chosen text mark as you type, size it or colour it.
    Connections {
        target: root.host
        function onOptionsChanged() {
            const o = root.host.options
            const before = root.seen
            root.seen = Object.assign({}, o)
            if (root.chosen < 0 || root.chosen >= root.marks.length)
                return
            const mark = root.marks[root.chosen]
            if (mark.type !== "text")
                return
            const next = Object.assign({}, mark)
            let changed = false
            const words = String(o.text || "").trim()
            if (o.text !== before.text && words !== "" && words !== mark.text) { next.text = words; changed = true }
            if (o.text_size !== before.text_size) { next.size = Number(o.text_size || 48) * root.unit; changed = true }
            if (o.color !== before.color && o.color !== mark.color) { next.color = String(o.color); changed = true }
            if (changed)
                root.replace(root.chosen, root.laidOut(next))
        }
    }
    Component.onCompleted: seen = Object.assign({}, host.options)

    PictureFrame {
        id: frame
        anchors.fill: parent
        anchors.bottomMargin: 46
        inset: 28
        source: editor.sourceUrl
        sourceWidth: Math.max(1, editor.imageWidth)
        sourceHeight: Math.max(1, editor.imageHeight)

        Item {
            id: surface
            x: frame.originX
            y: frame.originY
            width: frame.viewWidth
            height: frame.viewHeight

            Canvas {
                id: paper
                anchors.fill: parent
                renderTarget: Canvas.Image
                onWidthChanged: requestPaint()
                onHeightChanged: requestPaint()

                function drawOp(ctx, op, s) {
                    const w = Math.max(1, Number(op.width || 3) * s)
                    ctx.lineCap = "round"
                    ctx.lineJoin = "round"
                    ctx.strokeStyle = op.color
                    ctx.fillStyle = op.color
                    ctx.lineWidth = w
                    if (op.type === "arrow") {
                        const x1 = op.x1 * s, y1 = op.y1 * s, x2 = op.x2 * s, y2 = op.y2 * s
                        const angle = Math.atan2(y2 - y1, x2 - x1)
                        const head = Math.max(10 * s, w * 4.2)
                        ctx.beginPath()
                        ctx.moveTo(x1, y1)
                        ctx.lineTo(x2 - head * 0.8 * Math.cos(angle), y2 - head * 0.8 * Math.sin(angle))
                        ctx.stroke()
                        ctx.beginPath()
                        ctx.moveTo(x2, y2)
                        ctx.lineTo(x2 - head * Math.cos(angle - 0.42), y2 - head * Math.sin(angle - 0.42))
                        ctx.lineTo(x2 - head * Math.cos(angle + 0.42), y2 - head * Math.sin(angle + 0.42))
                        ctx.closePath()
                        ctx.fill()
                    } else if (op.type === "pen") {
                        const points = op.points || []
                        if (!points.length)
                            return
                        ctx.beginPath()
                        ctx.moveTo(points[0][0] * s, points[0][1] * s)
                        if (points.length === 1)
                            ctx.lineTo(points[0][0] * s + 0.01, points[0][1] * s)
                        for (let i = 1; i < points.length; i++)
                            ctx.lineTo(points[i][0] * s, points[i][1] * s)
                        ctx.stroke()
                    } else if (op.type === "rect" || op.type === "ellipse" || op.type === "highlight") {
                        const x = Math.min(op.x1, op.x2) * s, y = Math.min(op.y1, op.y2) * s
                        const bw = Math.abs(op.x2 - op.x1) * s, bh = Math.abs(op.y2 - op.y1) * s
                        if (op.type === "highlight") {
                            ctx.globalAlpha = 96 / 255
                            ctx.fillRect(x, y, bw, bh)
                            ctx.globalAlpha = 1
                        } else if (op.type === "rect") {
                            ctx.strokeRect(x, y, bw, bh)
                        } else {
                            ctx.beginPath()
                            ctx.ellipse(x, y, bw, bh)
                            ctx.stroke()
                        }
                    }
                }

                onPaint: {
                    const ctx = getContext("2d")
                    ctx.reset()
                    const s = frame.scaleFactor
                    for (const op of root.marks)
                        if (op.type !== "text")
                            drawOp(ctx, op, s)
                    if (root.drawing)
                        drawOp(ctx, root.drawing, s)
                }
            }

            // Words are laid out by Qt here and in the saved copy alike.
            Repeater {
                model: root.marks
                Text {
                    visible: modelData.type === "text"
                    x: (modelData.x1 || 0) * frame.scaleFactor
                    y: (modelData.y1 || 0) * frame.scaleFactor
                    width: Math.max(1, ((modelData.x2 || 0) - (modelData.x1 || 0)) * frame.scaleFactor)
                    text: modelData.type === "text" ? modelData.text : ""
                    color: modelData.color || "#F87800"
                    wrapMode: Text.WordWrap
                    horizontalAlignment: Fmt.hasArabic(text) ? Text.AlignRight : Text.AlignLeft
                    font.family: "Segoe UI"
                    font.bold: true
                    font.pixelSize: Math.max(6, Math.floor(Number(modelData.size || 32) * frame.scaleFactor))
                }
            }

            Rectangle {
                readonly property var m: root.chosen >= 0 && root.chosen < root.marks.length ? root.marks[root.chosen] : null
                visible: m !== null && m.type === "text"
                x: m ? m.x1 * frame.scaleFactor - 4 : 0
                y: m ? m.y1 * frame.scaleFactor - 3 : 0
                width: m ? (m.x2 - m.x1) * frame.scaleFactor + 8 : 0
                height: m ? m.size * 1.45 * frame.scaleFactor + 6 : 0
                color: "transparent"
                radius: 4
                border.width: 1.5
                border.color: Theme.accent
            }

            TextMetrics {
                id: measure
                font.family: "Segoe UI"
                font.bold: true
                font.pixelSize: Math.max(6, Math.floor(root.textSize))
            }

            MouseArea {
                anchors.fill: parent
                enabled: !typing.visible
                cursorShape: root.kind === "text" ? Qt.IBeamCursor : Qt.CrossCursor
                property point from
                onPressed: (mouse) => {
                    const s = frame.scaleFactor
                    const x = mouse.x / s, y = mouse.y / s
                    from = Qt.point(x, y)
                    if (root.kind === "text") {
                        const hit = root.textAt(x, y)
                        if (hit >= 0) {
                            root.choose(hit)
                            return
                        }
                        const words = String(root.host.options.text || "").trim()
                        if (words !== "" && root.chosen < 0) {
                            root.add(root.laidOut({ "type": "text", "text": words, "x1": x, "y1": y, "x2": x,
                                                    "anchor": x, "size": root.textSize, "color": root.ink }))
                            return
                        }
                        root.chosen = -1
                        typing.open(x, y)
                        return
                    }
                    root.chosen = -1
                    if (root.kind === "pen")
                        root.drawing = { "type": "pen", "points": [[x, y]], "color": root.ink, "width": root.thickness }
                    else
                        root.drawing = { "type": root.kind, "x1": x, "y1": y, "x2": x, "y2": y, "color": root.ink, "width": root.thickness }
                }
                onPositionChanged: (mouse) => {
                    if (!pressed || !root.drawing)
                        return
                    const s = frame.scaleFactor
                    const x = Fmt.clamp(mouse.x / s, 0, frame.sourceWidth), y = Fmt.clamp(mouse.y / s, 0, frame.sourceHeight)
                    const next = Object.assign({}, root.drawing)
                    if (next.type === "pen") {
                        const last = next.points[next.points.length - 1]
                        if (Math.abs(last[0] - x) * s + Math.abs(last[1] - y) * s < 1.5)
                            return
                        next.points = next.points.concat([[x, y]])
                    } else {
                        next.x2 = x
                        next.y2 = y
                    }
                    root.drawing = next
                }
                onReleased: {
                    const op = root.drawing
                    root.drawing = null
                    if (!op)
                        return
                    const s = frame.scaleFactor
                    const big = op.type === "pen" ? op.points.length > 0
                              : op.type === "arrow" ? Math.hypot(op.x2 - op.x1, op.y2 - op.y1) * s > 6
                              : Math.abs(op.x2 - op.x1) * s > 4 && Math.abs(op.y2 - op.y1) * s > 4
                    if (big)
                        root.add(op)
                }
                onCanceled: root.drawing = null
            }

            // Typing words straight onto the photo.
            Rectangle {
                id: typing
                visible: false
                property real sx: 0
                property real sy: 0
                x: sx * frame.scaleFactor - 4
                y: sy * frame.scaleFactor - 4
                width: Math.max(80, field.contentWidth + 16)
                height: field.contentHeight + 8
                color: Qt.rgba(0, 0, 0, 0.25)
                radius: 6
                border.width: 1
                border.color: "white"

                function open(x, y) {
                    sx = x
                    sy = y
                    field.text = ""
                    visible = true
                    field.forceActiveFocus()
                    field.selectAll()
                }
                function cancel() {
                    visible = false
                    field.text = ""
                }
                function commit() {
                    const words = field.text.trim()
                    visible = false
                    if (!words)
                        return
                    root.add(root.laidOut({ "type": "text", "text": words, "x1": sx, "y1": sy, "x2": sx, "anchor": sx,
                                            "size": root.textSize, "color": root.ink }))
                    field.text = ""
                    // The panel now shows these words: editing them there changes them here.
                    root.host.setOption("text", words)
                }

                TextInput {
                    id: field
                    x: 4
                    y: 4
                    color: root.ink
                    font.family: "Segoe UI"
                    font.bold: true
                    font.pixelSize: Math.max(8, Math.floor(root.textSize * frame.scaleFactor))
                    selectByMouse: true
                    onAccepted: typing.commit()
                    Keys.onEscapePressed: typing.cancel()
                    onActiveFocusChanged: if (!activeFocus && typing.visible) typing.commit()
                }
            }
        }
    }

    Row {
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 8
        spacing: 6
        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: Fmt.fill(root.host.word("ed.marks"), { "n": root.marks.length })
            color: Theme.textSecondary
            font.family: Theme.fontFamily
            font.pixelSize: 12
        }
        IconButton {
            icon: ""
            mirrorIcon: eshab.rtl
            tip: root.host.word("ed.undo")
            enabled: root.marks.length > 0
            onClicked: root.undo()
        }
        IconButton {
            icon: ""
            mirrorIcon: eshab.rtl
            tip: root.host.word("ed.redo")
            enabled: root.redone.length > 0
            onClicked: root.redo()
        }
        IconButton {
            icon: ""
            tip: root.host.word("ed.clear")
            danger: true
            enabled: root.marks.length > 0
            onClicked: { root.marks = []; root.redone = [] }
        }
    }
}
