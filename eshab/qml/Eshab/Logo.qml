import QtQuick

// The «الملف ينسحب» mark. At rest the page's corner is a drop sitting in a
// round notch; now and then the drop is pulled out on a liquid neck that
// snaps, and it springs back. The same shape is the loader (the page fills
// with the material) and the success state (a check replaces the lines).
Item {
    id: root

    property real size: 64
    property string material: Theme.material
    property bool flat: false          // single colour: title bars, tiny sizes
    property color ink: Theme.text
    property bool lines: true
    property bool alive: true          // idle pull-and-snap
    property real progress: -1         // >= 0 shows the loader
    property bool done: false          // success check

    implicitWidth: size
    implicitHeight: size

    // Animated state, in units of the 100 x 100 box.
    property real pull: 0
    property real hoverPull: 0
    property real neckA: 0
    property real neckB: 0
    property real bob: 0
    property real wave: 0
    property real check: 0

    readonly property var tone: Theme.materials[material] || Theme.materials["honey"]
    readonly property real reach: 16 * (pull + hoverPull) + bob
    readonly property bool loading: progress >= 0 && !done
    // Animations stop with the window: nothing ticks while Eshab sits in the tray.
    readonly property bool shown: visible && Window.window !== null && Window.window.visible

    function rgb(value) {
        const c = Qt.color(value)
        return Qt.vector4d(c.r, c.g, c.b, 1)
    }

    ShaderEffect {
        anchors.fill: parent
        fragmentShader: "shaders/mark.frag.qsb"
        property vector4d page: Qt.vector4d(55, 56, 26, 32)
        property vector4d notch: Qt.vector4d(29, 24, 20, 9)
        property vector4d drop: Qt.vector4d(27.5 - 0.634 * root.reach, 22.5 - 0.773 * root.reach,
                                            12 - 1.6 * Math.max(0, root.pull), 3)
        property vector4d neck: Qt.vector4d(root.neckA, root.neckB, 100 / Math.max(1, width),
                                            root.lines ? 1 : 0)
        property vector4d lightTone: root.flat ? root.rgb(root.ink) : root.rgb(root.tone.light)
        property vector4d deepTone: root.rgb(root.tone.deep)
        property vector4d matter: Qt.vector4d(root.tone.alpha, root.tone.rim,
                                              root.loading ? Math.min(1, root.progress) : -1, root.wave)
        property vector4d extra: Qt.vector4d(root.check, root.flat ? 1 : 0, 0, 0)
    }

    HoverHandler { id: hover }
    Behavior on hoverPull { SpringAnimation { spring: 3.2; damping: 0.22; epsilon: 0.002 } }
    Binding { target: root; property: "hoverPull"; value: hover.hovered && !root.loading ? 0.22 : 0 }

    // Idle: rest, sink into the notch, pull out on a neck, snap, spring back.
    // A timer starts each pull, so between pulls nothing animates and the
    // window renders no frames at all.
    Timer {
        interval: 4600
        repeat: true
        running: root.alive && root.shown && !root.loading && !root.done
        onRunningChanged: if (!running) pullOnce.complete()
        onTriggered: pullOnce.restart()
    }
    SequentialAnimation {
        id: pullOnce
        NumberAnimation { target: root; property: "pull"; to: -0.42; duration: 360; easing.type: Easing.InOutSine }
        ParallelAnimation {
            NumberAnimation { target: root; property: "pull"; to: 1.0; duration: 760; easing.type: Easing.InOutCubic }
            SequentialAnimation {
                ParallelAnimation {
                    NumberAnimation { target: root; property: "neckA"; to: 7.5; duration: 220; easing.type: Easing.OutQuad }
                    NumberAnimation { target: root; property: "neckB"; to: 5.0; duration: 220; easing.type: Easing.OutQuad }
                }
                ParallelAnimation {
                    NumberAnimation { target: root; property: "neckA"; to: 1.8; duration: 540; easing.type: Easing.InQuad }
                    NumberAnimation { target: root; property: "neckB"; to: 0.9; duration: 540; easing.type: Easing.InQuad }
                }
            }
        }
        ParallelAnimation {
            NumberAnimation { target: root; property: "neckA"; to: 0; duration: 80 }
            NumberAnimation { target: root; property: "neckB"; to: 0; duration: 80 }
        }
        NumberAnimation { target: root; property: "pull"; to: 0; duration: 700; easing.type: Easing.OutBack; easing.overshoot: 2.4 }
    }

    // Loading: the liquid level waves and the drop bobs above the notch.
    NumberAnimation on wave {
        running: root.loading && root.shown
        from: 0; to: Math.PI * 2; duration: 1300; loops: Animation.Infinite
    }
    SequentialAnimation on bob {
        running: root.loading && root.shown
        loops: Animation.Infinite
        NumberAnimation { to: 3.0; duration: 520; easing.type: Easing.InOutSine }
        NumberAnimation { to: 0; duration: 520; easing.type: Easing.InOutSine }
    }
    onLoadingChanged: if (!loading) bob = 0

    // Done: the check draws itself, then the lines come back when done clears.
    NumberAnimation {
        id: checkIn
        target: root; property: "check"; from: 0; to: 1; duration: 560; easing.type: Easing.OutCubic
    }
    onDoneChanged: {
        if (done) { checkIn.restart() }
        else { checkIn.stop(); check = 0 }
    }
}
