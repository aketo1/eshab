import QtQuick
import Eshab

// A sound's outline as bars. Drawn once per size; the played part is the
// same drawing in the accent colour, clipped at the playhead, so playing
// costs nothing but moving a clip.
Item {
    id: root

    property var peaks: []
    property real played: 0          // 0..1
    property color ink: Theme.dark ? Qt.rgba(1, 1, 1, 0.38) : Qt.rgba(0, 0, 0, 0.3)
    property color playedInk: Theme.accent

    // (An inline component cannot see this file's ids, so the peaks are handed in.)
    component Bars: Canvas {
        property color color
        property var peaks: []
        renderTarget: Canvas.Image
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        onColorChanged: requestPaint()
        onPeaksChanged: requestPaint()
        onPaint: {
            const ctx = getContext("2d")
            ctx.reset()
            const n = peaks.length
            if (!n || width < 2)
                return
            ctx.fillStyle = color
            const step = 3
            const middle = height / 2
            for (let x = 0; x < width; x += step) {
                const a = Math.floor(x / width * n)
                const b = Math.max(a + 1, Math.floor((x + step) / width * n))
                let top = 0
                for (let i = a; i < b && i < n; i++)
                    if (peaks[i] > top) top = peaks[i]
                const half = Math.max(1, top * (middle - 4))
                ctx.fillRect(x, middle - half, step - 1, half * 2)
            }
        }
    }

    Bars {
        anchors.fill: parent
        color: root.ink
        peaks: root.peaks
    }
    Item {
        width: Math.round(root.width * Math.max(0, Math.min(1, root.played)))
        height: root.height
        clip: true
        Bars {
            width: root.width
            height: root.height
            color: root.playedInk
            peaks: root.peaks
        }
    }
}
