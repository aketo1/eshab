import QtQuick
import QtMultimedia
import Eshab
import "Fmt.js" as Fmt

// A video to watch and to choose from.
//   trim      - keep the part between two handles
//   crop      - a box over the picture keeps what is inside it
//   boxes     - areas to hide, each from when it starts to when it ends
//   snapshots - moments to save as pictures
// Other tools show it to watch (at the new speed, for the speed tool), with
// its details when they edit them.
Item {
    id: root

    property var host
    readonly property string mode: host.spec.mode
    readonly property real duration: editor.mediaDuration > 0 ? editor.mediaDuration : player.duration / 1000
    readonly property real now: player.position / 1000
    readonly property bool playing: player.playbackState === MediaPlayer.PlayingState
    readonly property real sourceWidth: Math.max(1, editor.videoWidth > 0 ? editor.videoWidth : screen.sourceRect.width)
    readonly property real sourceHeight: Math.max(1, editor.videoHeight > 0 ? editor.videoHeight : screen.sourceRect.height)
    property real start: 0
    property real end: 0
    property var times: []
    readonly property bool ready: duration > 0 && (
        mode === "trim" ? end - start >= 0.05 :
        mode === "crop" ? crop.box.w >= 2 && crop.box.h >= 2 :
        mode === "boxes" ? boxes.count > 0 :
        mode === "snapshots" ? (times.length > 0 || Number(host.options.every || 0) > 0) : true)

    function stateObject() {
        if (mode === "trim")
            return { "start": Math.round(start * 1000) / 1000, "end": Math.round(end * 1000) / 1000 }
        if (mode === "crop")
            return { "box": crop.rounded() }
        if (mode === "boxes")
            return { "boxes": boxes.list() }
        if (mode === "snapshots")
            return { "times": times }
        return {}
    }

    function toggle() {
        if (playing) {
            player.pause()
            return
        }
        if (mode === "trim" && (now < start || now >= end - 0.05))
            player.position = start * 1000
        player.play()
    }

    function seek(t) {
        player.position = Math.round(Fmt.clamp(t, 0, duration) * 1000)
    }

    function addSnapshot() {
        const t = Math.round(now * 1000) / 1000
        if (times.indexOf(t) < 0)
            times = times.concat([t]).sort((a, b) => a - b)
    }

    function undo() {
        if (mode === "boxes") boxes.remove(boxes.count - 1)
        else if (mode === "snapshots" && times.length) times = times.slice(0, times.length - 1)
    }

    function deleteSelected() {
        if (mode === "boxes") boxes.remove(boxes.selected)
    }

    onDurationChanged: if (end <= 0 || end > duration) end = duration

    MediaPlayer {
        id: player
        source: editor.mediaUrl
        videoOutput: screen
        audioOutput: AudioOutput {}
        playbackRate: editor.toolKey === "vid.speed" ? Number(root.host.options.speed || 1) : 1
        onMediaStatusChanged: {
            // Show the first picture instead of black.
            if (mediaStatus === MediaPlayer.LoadedMedia && playbackState === MediaPlayer.StoppedState)
                pause()
        }
        onPositionChanged: {
            if (root.mode === "trim" && playbackState === MediaPlayer.PlayingState && position / 1000 >= root.end) {
                pause()
                position = root.start * 1000
            }
        }
    }

    Rectangle {
        id: picture
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: controls.top
        anchors.margins: 18
        anchors.bottomMargin: 12
        radius: 12
        color: "black"
        clip: false
        LayoutMirroring.enabled: false
        LayoutMirroring.childrenInherit: true

        VideoOutput {
            id: screen
            anchors.fill: parent
            // Room around the picture, so a box's corners can be reached at its edges.
            anchors.margins: root.mode === "crop" || root.mode === "boxes" ? 24 : 0
            fillMode: VideoOutput.PreserveAspectFit
        }
        MouseArea {
            anchors.fill: parent
            enabled: root.mode !== "crop" && root.mode !== "boxes"
            onClicked: root.toggle()
        }
        // Over the whole frame, with the picture's corner at (originX, originY),
        // so handles at the picture's edges can always be reached.
        Item {
            id: overlay
            anchors.fill: parent
            readonly property real scaleFactor: screen.contentRect.width / root.sourceWidth
            readonly property real originX: screen.x + screen.contentRect.x
            readonly property real originY: screen.y + screen.contentRect.y

            CropBox {
                id: crop
                visible: root.mode === "crop"
                enabled: visible
                sourceWidth: root.sourceWidth
                sourceHeight: root.sourceHeight
                scaleFactor: overlay.scaleFactor
                originX: overlay.originX
                originY: overlay.originY
                ratio: root.mode === "crop" ? Fmt.ratio(root.host.options.aspect, root.sourceWidth, root.sourceHeight) : 0
            }
            BoxLayer {
                id: boxes
                visible: root.mode === "boxes"
                enabled: visible
                sourceWidth: root.sourceWidth
                sourceHeight: root.sourceHeight
                scaleFactor: overlay.scaleFactor
                originX: overlay.originX
                originY: overlay.originY
                mode: String(root.host.options.mode || "blur")
                tint: String(root.host.options.color || "#1C1C1E")
                pictureItem: root.mode === "boxes" ? screen : null
                pictureOffset: Qt.point(screen.contentRect.x, screen.contentRect.y)
                timed: true
                time: root.now
                duration: root.duration
            }
        }
        // Play, big and quiet, while it is paused.
        Rectangle {
            visible: !root.playing && root.mode !== "crop" && root.mode !== "boxes"
            anchors.centerIn: parent
            width: 64
            height: 64
            radius: 32
            color: Qt.rgba(0, 0, 0, 0.45)
            border.width: 1
            border.color: Qt.rgba(1, 1, 1, 0.3)
            Text {
                anchors.centerIn: parent
                anchors.horizontalCenterOffset: 2
                text: ""
                font.family: Theme.iconFont
                font.pixelSize: 24
                color: "white"
            }
        }
    }

    Column {
        id: controls
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.margins: 18
        anchors.topMargin: 0
        spacing: 10

        Timeline {
            id: line
            width: parent.width
            height: 34
            duration: root.duration
            position: root.now
            readonly property bool boxTime: root.mode === "boxes" && boxes.selected >= 0
            mode: root.mode === "trim" || boxTime ? "trim" : "plain"
            start: boxTime && boxes.revision >= 0 ? boxes.boxes.get(boxes.selected).t0 : root.start
            end: boxTime && boxes.revision >= 0 ? boxes.boxes.get(boxes.selected).t1 : root.end
            marks: root.mode === "snapshots" ? root.times
                 : (editor.toolKey === "vid.split" ? (function () {
                       const parts = Math.max(2, Number(root.host.options.parts || 2)), out = []
                       for (let i = 1; i < parts; i++) out.push(root.duration * i / parts)
                       return out
                   })() : [])
            ranges: {
                if (root.mode !== "boxes" || boxTime || boxes.revision < 0)
                    return []
                const out = []
                for (let i = 0; i < boxes.count; i++) {
                    const b = boxes.boxes.get(i)
                    out.push([b.t0, b.t1])
                }
                return out
            }
            rangeColor: Theme.accent
            onSeek: (t) => root.seek(t)
            onTrimmed: (a, b) => {
                if (boxTime) {
                    boxes.setTimes(boxes.selected, a, b)
                    return
                }
                root.start = a
                root.end = b
                if (root.now < a || root.now > b)
                    root.seek(a)
            }

            Rectangle {
                anchors.fill: parent
                radius: 8
                color: Theme.dark ? Qt.rgba(1, 1, 1, 0.07) : Qt.rgba(0, 0, 0, 0.05)
                Rectangle {
                    width: root.duration > 0 ? parent.width * Fmt.clamp(root.now / root.duration, 0, 1) : 0
                    height: parent.height
                    radius: 8
                    color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.28)
                }
            }
        }

        Item {
            width: parent.width
            height: 40

            Row {
                anchors.left: parent.left
                anchors.verticalCenter: parent.verticalCenter
                spacing: 10
                IconButton {
                    icon: root.playing ? "" : ""
                    tip: root.playing ? root.host.word("ed.pause") : root.host.word("ed.play")
                    active: true
                    width: 40
                    height: 40
                    onClicked: root.toggle()
                }
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: Fmt.time(root.now, true) + "  /  " + Fmt.time(root.duration, true)
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: 13
                    font.features: { "tnum": 1 }
                }
            }

            Row {
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                spacing: 8

                // trim
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    visible: root.mode === "trim"
                    text: Fmt.fill(root.host.word("ed.keeps"), { "t": Fmt.time(root.end - root.start, true) })
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: 12
                }
                IconButton {
                    visible: root.mode === "trim"
                    icon: ""
                    tip: root.host.word("ed.reset")
                    onClicked: { root.start = 0; root.end = root.duration }
                }

                // split
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    visible: editor.toolKey === "vid.split"
                    text: Fmt.fill(root.host.word("ed.parts_at"), { "t": Fmt.time(root.duration / Math.max(2, Number(root.host.options.parts || 2)), true) })
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: 12
                }

                // areas to hide
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    visible: root.mode === "boxes"
                    text: Fmt.fill(root.host.word("ed.boxes"), { "n": boxes.count })
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: 12
                }
                IconButton {
                    visible: root.mode === "boxes" && boxes.selected >= 0
                    icon: ""
                    text: root.host.word("ed.starts_here")
                    onClicked: {
                        const b = boxes.boxes.get(boxes.selected)
                        boxes.setTimes(boxes.selected, Math.min(root.now, b.t1 - 0.1), b.t1)
                    }
                }
                IconButton {
                    visible: root.mode === "boxes" && boxes.selected >= 0
                    icon: ""
                    text: root.host.word("ed.ends_here")
                    onClicked: {
                        const b = boxes.boxes.get(boxes.selected)
                        boxes.setTimes(boxes.selected, b.t0, Math.max(root.now, b.t0 + 0.1))
                    }
                }
                IconButton {
                    visible: root.mode === "boxes"
                    icon: ""
                    danger: true
                    tip: root.host.word("ed.clear")
                    enabled: boxes.count > 0
                    onClicked: boxes.clear()
                }

                // snapshots
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    visible: root.mode === "snapshots"
                    text: Fmt.fill(root.host.word("ed.snapshots"), { "n": root.times.length })
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: 12
                }
                IconButton {
                    visible: root.mode === "snapshots"
                    icon: ""
                    text: root.host.word("ed.add_snapshot")
                    onClicked: root.addSnapshot()
                }
                IconButton {
                    visible: root.mode === "snapshots"
                    icon: ""
                    danger: true
                    tip: root.host.word("ed.clear")
                    enabled: root.times.length > 0
                    onClicked: root.times = []
                }
            }
        }

        // The moments chosen, each a chip to jump to or remove.
        Flow {
            visible: root.mode === "snapshots" && root.times.length > 0
            width: parent.width
            spacing: 6
            Repeater {
                model: root.mode === "snapshots" ? root.times : []
                Rectangle {
                    height: 28
                    width: chipText.implicitWidth + 40
                    radius: 14
                    color: Theme.dark ? Qt.rgba(1, 1, 1, 0.08) : Qt.rgba(0, 0, 0, 0.05)
                    border.width: 1
                    border.color: Theme.glassRim
                    Text {
                        id: chipText
                        anchors.left: parent.left
                        anchors.leftMargin: 12
                        anchors.verticalCenter: parent.verticalCenter
                        text: Fmt.time(modelData, true)
                        color: Theme.text
                        font.family: Theme.fontFamily
                        font.pixelSize: 12
                    }
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.seek(modelData)
                    }
                    Text {
                        anchors.right: parent.right
                        anchors.rightMargin: 9
                        anchors.verticalCenter: parent.verticalCenter
                        text: ""
                        font.family: Theme.iconFont
                        font.pixelSize: 9
                        color: Theme.textSecondary
                        MouseArea {
                            anchors.fill: parent
                            anchors.margins: -6
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.times = root.times.filter((t) => t !== modelData)
                        }
                    }
                }
            }
        }

        InfoList {
            visible: root.mode === "metadata"
            width: parent.width
            height: root.mode === "metadata" ? Math.min(root.height * 0.3, contentHeight + 4) : 0
            rows: editor.infoRows
        }
    }

    Shortcut {
        sequence: "Space"
        onActivated: root.toggle()
    }
}
