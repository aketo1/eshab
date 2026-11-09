import QtQuick
import QtMultimedia
import Eshab
import "Fmt.js" as Fmt

// A sound file: its waveform, to listen to and to choose from.
//   trim  - keep the part between two handles (it plays just that part)
//   bleep - mark the parts to cover; they bleep as it plays
//   other tools show it to listen to, with its details when they edit them.
Item {
    id: root

    property var host
    readonly property string mode: host.spec.mode
    readonly property real duration: editor.mediaDuration > 0 ? editor.mediaDuration : player.duration / 1000
    property real start: 0
    property real end: 0
    property var ranges: []
    readonly property real now: player.position / 1000
    readonly property bool ready: duration > 0 && (mode === "trim" ? end - start >= 0.05 : mode === "bleep" ? ranges.length > 0 : true)
    readonly property bool inRange: {
        for (const r of ranges)
            if (now >= r[0] && now < r[1]) return true
        return false
    }

    function stateObject() {
        if (mode === "trim")
            return { "start": Math.round(start * 1000) / 1000, "end": Math.round(end * 1000) / 1000 }
        if (mode === "bleep")
            return { "ranges": ranges.map((r) => [Math.round(r[0] * 1000) / 1000, Math.round(r[1] * 1000) / 1000]) }
        return {}
    }

    function toggle() {
        if (player.playbackState === MediaPlayer.PlayingState) {
            player.pause()
            return
        }
        if (mode === "trim" && (now < start || now >= end - 0.05))
            player.position = start * 1000
        player.play()
    }

    function seek(t) {
        player.position = Math.round(t * 1000)
    }

    function undo() {
        if (mode === "bleep" && ranges.length)
            ranges = ranges.slice(0, ranges.length - 1)
    }

    onDurationChanged: if (end <= 0 || end > duration) end = duration

    MediaPlayer {
        id: player
        source: editor.mediaUrl
        audioOutput: AudioOutput {
            id: speaker
            muted: root.mode === "bleep" && root.inRange
        }
        onPositionChanged: {
            if (root.mode === "trim" && playbackState === MediaPlayer.PlayingState && position / 1000 >= root.end) {
                pause()
                position = root.start * 1000
            }
        }
    }
    SoundEffect {
        id: bleep
        source: editor.beepUrl
        loops: SoundEffect.Infinite
        volume: 0.35
    }
    Binding {
        target: bleep
        property: "muted"
        value: !(root.mode === "bleep" && root.inRange && player.playbackState === MediaPlayer.PlayingState)
    }
    Connections {
        target: player
        function onPlaybackStateChanged() {
            if (root.mode !== "bleep")
                return
            if (player.playbackState === MediaPlayer.PlayingState) bleep.play()
            else bleep.stop()
        }
    }

    Column {
        anchors.fill: parent
        anchors.margins: 22
        spacing: 14

        Rectangle {
            id: wavePanel
            width: parent.width
            height: root.mode === "metadata" ? Math.max(120, parent.height * 0.42) : Math.max(140, parent.height - controls.height - 14)
            radius: 14
            color: Theme.dark ? Qt.rgba(1, 1, 1, 0.035) : Qt.rgba(0, 0, 0, 0.025)

            Timeline {
                id: line
                anchors.fill: parent
                anchors.margins: 10
                duration: root.duration
                position: root.now
                mode: root.mode === "trim" ? "trim" : root.mode === "bleep" ? "ranges" : "plain"
                start: root.start
                end: root.end
                ranges: root.ranges
                onSeek: (t) => root.seek(t)
                onTrimmed: (a, b) => {
                    root.start = a
                    root.end = b
                    if (root.now < a || root.now > b)
                        root.seek(a)
                }
                onRangeAdded: (a, b) => {
                    // Overlapping parts join into one.
                    let merged = [a, b]
                    const kept = []
                    for (const r of root.ranges) {
                        if (r[1] < merged[0] || r[0] > merged[1]) kept.push(r)
                        else merged = [Math.min(r[0], merged[0]), Math.max(r[1], merged[1])]
                    }
                    kept.push(merged)
                    kept.sort((x, y) => x[0] - y[0])
                    root.ranges = kept
                }
                onRangeRemoved: (i) => root.ranges = root.ranges.filter((r, j) => j !== i)

                Waveform {
                    anchors.fill: parent
                    peaks: editor.peaksList
                    played: root.duration > 0 ? root.now / root.duration : 0
                }
            }
            Text {
                anchors.centerIn: parent
                visible: editor.peaksList.length === 0
                text: root.host.word("ed.no_preview")
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: 13
            }
        }

        Item {
            id: controls
            width: parent.width
            height: 44

            Row {
                anchors.left: parent.left
                anchors.verticalCenter: parent.verticalCenter
                spacing: 10
                IconButton {
                    icon: player.playbackState === MediaPlayer.PlayingState ? "" : ""
                    tip: player.playbackState === MediaPlayer.PlayingState ? root.host.word("ed.pause") : root.host.word("ed.play")
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
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    visible: root.mode === "trim"
                    text: root.host.word("ed.start") + " " + Fmt.time(root.start, true) + "   " + root.host.word("ed.end") + " " + Fmt.time(root.end, true)
                          + "   ·   " + Fmt.fill(root.host.word("ed.keeps"), { "t": Fmt.time(root.end - root.start, true) })
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: 12
                }
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    visible: root.mode === "bleep"
                    text: Fmt.fill(root.host.word("ed.boxes"), { "n": root.ranges.length })
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: 12
                }
                IconButton {
                    visible: root.mode === "bleep"
                    icon: ""
                    mirrorIcon: eshab.rtl
                    tip: root.host.word("ed.undo")
                    enabled: root.ranges.length > 0
                    onClicked: root.undo()
                }
                IconButton {
                    visible: root.mode === "bleep"
                    icon: ""
                    danger: true
                    tip: root.host.word("ed.clear")
                    enabled: root.ranges.length > 0
                    onClicked: root.ranges = []
                }
                IconButton {
                    visible: root.mode === "trim"
                    icon: ""
                    tip: root.host.word("ed.reset")
                    onClicked: { root.start = 0; root.end = root.duration }
                }
            }
        }

        InfoList {
            visible: root.mode === "metadata"
            width: parent.width
            height: root.mode === "metadata" ? Math.max(0, root.height - 44 - wavePanel.height - controls.height - 28) : 0
            rows: editor.infoRows
        }
    }

    Shortcut {
        sequence: "Space"
        onActivated: root.toggle()
    }
}
