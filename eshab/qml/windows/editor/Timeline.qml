import QtQuick
import Eshab
import "Fmt.js" as Fmt

// Time from left to right (in Arabic too, like the waveform drawn inside it):
// the playhead, what a trim keeps, parts marked across it, and single moments.
//   plain  - click or drag to move the playhead
//   trim   - two handles; what lies between them is kept
//   ranges - drag across to mark a part, click a part to remove it
// Marks (moments) can be shown in any mode. Time runs inside a margin (pad),
// so the trim handles at either end stay within this item and can be grabbed.
Item {
    id: root

    property real duration: 0
    property real position: 0
    property string mode: "plain"
    property real start: 0
    property real end: duration
    property var ranges: []
    property var marks: []
    property color rangeColor: "#E5484D"
    property color markColor: Theme.accent
    property bool dimOutside: mode === "trim"
    readonly property real pad: 20
    readonly property real span: Math.max(1, width - 2 * pad)
    readonly property bool dragging: seekArea.pressed || startGrip.pressed || endGrip.pressed
    default property alias content: back.data
    signal seek(real seconds)
    signal trimmed(real start, real end)
    signal rangeAdded(real from, real to)
    signal rangeRemoved(int index)

    LayoutMirroring.enabled: false
    LayoutMirroring.childrenInherit: true

    function px(t) { return pad + (duration > 0 ? Fmt.clamp(t / duration, 0, 1) * span : 0) }
    function at(x) { return duration > 0 ? Fmt.clamp((x - pad) / span, 0, 1) * duration : 0 }

    Item {
        id: back
        x: root.pad
        width: root.span
        height: root.height
    }

    // Outside the trim, dimmed.
    Rectangle {
        visible: root.dimOutside
        x: root.pad; y: 0; height: root.height
        width: Math.max(0, root.px(root.start) - root.pad)
        color: Theme.dark ? Qt.rgba(0, 0, 0, 0.55) : Qt.rgba(1, 1, 1, 0.7)
    }
    Rectangle {
        visible: root.dimOutside
        x: root.px(root.end); y: 0; height: root.height
        width: Math.max(0, root.pad + root.span - root.px(root.end))
        color: Theme.dark ? Qt.rgba(0, 0, 0, 0.55) : Qt.rgba(1, 1, 1, 0.7)
    }

    // Marked parts.
    Repeater {
        model: root.ranges
        Rectangle {
            x: root.px(modelData[0])
            width: Math.max(2, root.px(modelData[1]) - root.px(modelData[0]))
            height: root.height
            color: Qt.rgba(root.rangeColor.r, root.rangeColor.g, root.rangeColor.b, partHover.hovered ? 0.5 : 0.32)
            border.width: 1
            border.color: root.rangeColor
            HoverHandler { id: partHover }
            Text {
                anchors.centerIn: parent
                visible: partHover.hovered && parent.width > 18
                text: ""
                font.family: Theme.iconFont
                font.pixelSize: 11
                color: "white"
            }
        }
    }
    // Moments.
    Repeater {
        model: root.marks
        Rectangle {
            x: root.px(modelData) - 1
            width: 2
            height: root.height
            color: root.markColor
            Rectangle {
                anchors.horizontalCenter: parent.horizontalCenter
                y: 0
                width: 8; height: 8; radius: 4
                color: root.markColor
            }
        }
    }

    // A part being marked.
    Rectangle {
        id: drafting
        visible: false
        height: root.height
        color: Qt.rgba(root.rangeColor.r, root.rangeColor.g, root.rangeColor.b, 0.25)
        border.width: 1
        border.color: root.rangeColor
    }

    MouseArea {
        id: seekArea
        anchors.fill: parent
        cursorShape: root.mode === "ranges" ? Qt.IBeamCursor : Qt.PointingHandCursor
        property real from: 0
        property bool marking: false
        onPressed: (mouse) => {
            from = Fmt.clamp(mouse.x, root.pad, root.pad + root.span)
            marking = false
            if (root.mode !== "ranges")
                root.seek(root.at(mouse.x))
        }
        onPositionChanged: (mouse) => {
            if (!pressed)
                return
            if (root.mode === "ranges") {
                const x = Fmt.clamp(mouse.x, root.pad, root.pad + root.span)
                if (!marking && Math.abs(x - from) > 4)
                    marking = true
                if (marking) {
                    drafting.visible = true
                    drafting.x = Math.min(from, x)
                    drafting.width = Math.max(from, x) - drafting.x
                }
            } else {
                root.seek(root.at(mouse.x))
            }
        }
        onReleased: (mouse) => {
            if (root.mode === "ranges") {
                if (marking) {
                    const a = root.at(drafting.x), b = root.at(drafting.x + drafting.width)
                    if (b - a >= 0.05)
                        root.rangeAdded(a, b)
                } else {
                    const t = root.at(mouse.x)
                    let hit = -1
                    for (let i = 0; i < root.ranges.length; i++)
                        if (t >= root.ranges[i][0] && t <= root.ranges[i][1]) hit = i
                    if (hit >= 0) root.rangeRemoved(hit)
                    else root.seek(t)
                }
            }
            drafting.visible = false
            marking = false
        }
        onCanceled: { drafting.visible = false; marking = false }
    }

    // The playhead.
    Rectangle {
        x: root.px(root.position) - 1
        width: 2
        height: root.height
        color: Theme.text
        opacity: 0.9
    }

    // Trim handles: the grip's coloured bar meets the kept part; the item
    // around it is wider, for an easy grab.
    Grip {
        id: startGrip
        visible: root.mode === "trim"
        x: root.px(root.start) - 20
        onDraggedTo: (gx) => root.trimmed(Math.min(root.at(gx + 20), root.end - 0.1), root.end)
    }
    Grip {
        id: endGrip
        visible: root.mode === "trim"
        x: root.px(root.end) - 6
        onDraggedTo: (gx) => root.trimmed(root.start, Math.max(root.at(gx + 6), root.start + 0.1))
    }

    // (An inline component cannot see this file's ids: its size comes from its parent.)
    component Grip: Item {
        id: grip
        readonly property alias pressed: gripArea.pressed
        signal draggedTo(real x)
        width: 26
        height: parent ? parent.height : 0
        Rectangle {
            x: 6
            width: 14
            height: parent.height
            radius: 5
            color: Theme.accent
            Column {
                anchors.centerIn: parent
                spacing: 3
                Repeater {
                    model: 3
                    Rectangle { width: 4; height: 1.5; radius: 1; color: Theme.onAccent; opacity: 0.8 }
                }
            }
        }
        MouseArea {
            id: gripArea
            anchors.fill: parent
            cursorShape: Qt.SizeHorCursor
            property real grab: 0
            onPressed: (mouse) => { grab = mouse.x }
            onPositionChanged: (mouse) => {
                if (pressed)
                    grip.draggedTo(grip.x + mouse.x - grab)
            }
        }
    }
}
