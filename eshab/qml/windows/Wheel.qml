import QtQuick
import QtQuick.Effects
import Eshab

// The wheel: a fan of glass cards dealt around the dragged file. Python
// (eshab/fanwheel.py) owns the state and the geometry; this file draws it.
Window {
    id: win

    required property var wheel

    width: 560
    height: 560
    color: "transparent"
    title: "Eshab"
    flags: Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.NoDropShadowWindowHint
           | (wheel.keyboard ? 0 : Qt.WindowDoesNotAcceptFocus)

    readonly property real cx: width / 2
    readonly property real cy: height / 2
    readonly property bool shown: wheel.phase === "open"
    readonly property bool leaving: wheel.phase === "leaving" || wheel.phase === "switching"
    readonly property real pad: 12
    readonly property real card: 58

    function hex(c) {
        const h = v => ("0" + Math.round(v * 255).toString(16)).slice(-2)
        return (h(c.r) + h(c.g) + h(c.b)).toUpperCase()
    }

    Image {
        id: frostImage
        anchors.fill: parent
        source: win.wheel.frost
        visible: false
        cache: false
        smooth: true
        asynchronous: false
    }

    // The liquid neck from the orb to the chosen card; it follows on a spring.
    ShaderEffect {
        id: bridge
        anchors.fill: parent
        readonly property var target: win.wheel.selected >= 0 && win.wheel.selected < win.wheel.cards.length
                                      ? win.wheel.cards[win.wheel.selected] : null
        property real bx: target ? target.x : win.cx
        property real by: target ? target.y : win.cy
        Behavior on bx { SpringAnimation { spring: 6; damping: 0.42; epsilon: 0.25 } }
        Behavior on by { SpringAnimation { spring: 6; damping: 0.42; epsilon: 0.25 } }
        opacity: win.shown && target ? 1 : 0
        visible: opacity > 0.01
        Behavior on opacity { NumberAnimation { duration: 140 } }
        property vector4d ends: Qt.vector4d(win.cx, win.cy, bx, by)
        property vector4d radii: Qt.vector4d(15, 11, 0.62, width)
        property vector4d tone: Qt.vector4d(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.82)
        property vector4d extra: Qt.vector4d(height, 0, 0, 0)
        fragmentShader: Qt.resolvedUrl("../Eshab/shaders/bridge.frag.qsb")
    }

    // The cards, dealt from the orb and flipped face up.
    Repeater {
        model: win.wheel.cards
        delegate: Item {
            id: cardItem
            required property var modelData
            required property int index
            readonly property bool chosen: index === win.wheel.selected
            property bool dealt: false

            width: win.card
            height: win.card
            x: (dealt && !win.leaving ? modelData.x : win.cx) - width / 2
            y: (dealt && !win.leaving ? modelData.y : win.cy) - height / 2
            z: chosen ? 2 : 1
            opacity: dealt && !(win.leaving && !chosen) ? 1 : 0
            scale: chosen ? (win.leaving ? 1.3 : 1.16) : (dealt ? 1 : 0.4)

            Behavior on x { SpringAnimation { spring: 4.6; damping: 0.34; epsilon: 0.2 } }
            Behavior on y { SpringAnimation { spring: 4.6; damping: 0.34; epsilon: 0.2 } }
            Behavior on opacity { NumberAnimation { duration: win.leaving ? 150 : 200 } }
            Behavior on scale { SpringAnimation { spring: 5; damping: 0.3; epsilon: 0.005 } }

            transform: Rotation {
                origin.x: cardItem.width / 2
                origin.y: cardItem.height / 2
                axis { x: 0; y: 1; z: 0 }
                angle: cardItem.dealt ? 0 : 85
                Behavior on angle { NumberAnimation { duration: 320; easing.type: Easing.OutCubic } }
            }

            Timer {
                running: win.shown && !cardItem.dealt
                interval: 16 + cardItem.index * 24
                onTriggered: cardItem.dealt = true
            }

            Glass {
                x: -win.pad
                y: -win.pad
                width: parent.width + 2 * win.pad
                height: parent.height + 2 * win.pad
                pad: win.pad
                radius: 18
                frost: frostImage
                fx: cardItem.x - win.pad
                fy: cardItem.y - win.pad
                accentStrength: cardItem.chosen ? 0.9 : 0
                Behavior on accentStrength { NumberAnimation { duration: 120 } }
            }

            readonly property color ink: chosen ? Theme.onAccent : Theme.text
            // Formats show their name; tools and actions show their icon.
            Text {
                visible: cardItem.modelData.kind === "conversion"
                anchors.centerIn: parent
                anchors.verticalCenterOffset: 6
                text: cardItem.modelData.text
                color: cardItem.ink
                font.family: Theme.fontFamily
                font.pixelSize: text.length > 4 ? 12 : 14
                font.weight: Font.Bold
            }
            Image {
                readonly property bool big: cardItem.modelData.kind !== "conversion"
                anchors.centerIn: parent
                anchors.verticalCenterOffset: big ? 0 : -11
                width: big ? 26 : 15
                height: width
                sourceSize: Qt.size(width * 2, height * 2)
                opacity: big ? 1 : 0.75
                source: cardItem.modelData.glyph
                        ? "image://eshab/glyph/" + cardItem.modelData.glyph + "/" + win.hex(cardItem.ink) : ""
            }
        }
    }

    // The orb: the dragged file, and where to let go to cancel.
    Glass {
        id: orb
        width: 68 + 2 * win.pad
        height: width
        x: win.cx - width / 2
        y: win.cy - height / 2
        pad: win.pad
        radius: 34
        frost: frostImage
        scale: win.shown ? 1 : 0.6
        opacity: win.wheel.phase === "hidden" ? 0 : 1
        Behavior on scale { SpringAnimation { spring: 5; damping: 0.32; epsilon: 0.005 } }
    }
    Item {
        id: preview
        width: 46
        height: 46
        x: win.cx - width / 2
        y: win.cy - height / 2
        scale: orb.scale
        visible: win.wheel.preview !== ""
        layer.enabled: true
        layer.effect: MultiEffect { maskEnabled: true; maskSource: previewMask }
        Image {
            anchors.fill: parent
            source: win.wheel.preview
            sourceSize: Qt.size(96, 96)
            fillMode: Image.PreserveAspectCrop
            asynchronous: true
        }
    }
    Rectangle {
        id: previewMask
        width: preview.width
        height: preview.height
        radius: width / 2
        visible: false
        layer.enabled: true
    }
    Rectangle {
        visible: win.wheel.fileCount > 1
        width: 22
        height: 22
        radius: 11
        x: win.cx + 18
        y: win.cy - 36
        color: Theme.accent
        Text {
            anchors.centerIn: parent
            text: win.wheel.fileCount
            color: Theme.onAccent
            font.family: Theme.fontFamily
            font.pixelSize: 11
            font.weight: Font.Bold
        }
    }

    // What letting go does now, and which keys open which wheel: one glass
    // capsule, so the words stay readable over icons and file names.
    Item {
        id: legend
        readonly property bool hasKeys: keys.count > 0
        width: Math.ceil(Math.max(label.implicitWidth, keyRow.implicitWidth)) + 36
        height: hasKeys ? 50 : 30
        x: Math.round(win.cx - width / 2)
        y: win.wheel.opensDown ? win.cy - 46 - height : win.cy + 46
        opacity: win.shown ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 160 } }
        Behavior on width { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }

        Glass {
            x: -win.pad
            y: -win.pad
            width: parent.width + 2 * win.pad
            height: parent.height + 2 * win.pad
            pad: win.pad
            radius: legend.hasKeys ? 16 : 15
            frost: frostImage
            fx: legend.x - win.pad
            fy: legend.y - win.pad
            shadowStrength: 0.18
        }
        Column {
            anchors.centerIn: parent
            spacing: 3
            Text {
                id: label
                anchors.horizontalCenter: parent.horizontalCenter
                text: win.wheel.label
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: 13
                font.weight: Font.DemiBold
            }
            Row {
                id: keyRow
                anchors.horizontalCenter: parent.horizontalCenter
                spacing: 10
                visible: legend.hasKeys
                Repeater {
                    id: keys
                    model: win.wheel.modes
                    Text {
                        required property var modelData
                        text: modelData.keys
                        color: modelData.active ? Theme.accent : Theme.textSecondary
                        font.family: Theme.fontFamily
                        font.pixelSize: 11
                        font.weight: modelData.active ? Font.Bold : Font.Normal
                    }
                }
            }
        }
    }

    DropArea {
        anchors.fill: parent
        onEntered: drag => {
            win.wheel.enter(drag.urls)
            win.wheel.pointer(drag.x, drag.y)
            drag.accept(Qt.CopyAction)
        }
        onPositionChanged: drag => {
            win.wheel.pointer(drag.x, drag.y)
            if (win.wheel.selected >= 0)
                drag.accept(Qt.CopyAction)
            else
                drag.accepted = false     // the "no" cursor: letting go here cancels
        }
        onExited: win.wheel.leave()
        onDropped: drop => {
            if (win.wheel.drop())
                drop.accept(Qt.CopyAction)   // copy only: the original is never moved
            else
                drop.accepted = false
        }
    }

    // Pinned or keyboard wheel: hover, click, arrows, Enter, Esc.
    MouseArea {
        anchors.fill: parent
        enabled: win.wheel.pinned
        hoverEnabled: true
        onPositionChanged: mouse => win.wheel.pointer(mouse.x, mouse.y)
        onClicked: mouse => win.wheel.click(mouse.x, mouse.y)
        onWheel: event => win.wheel.step(event.angleDelta.y < 0 ? 1 : -1)
    }
    Item {
        focus: win.wheel.keyboard
        Keys.onPressed: event => {
            if (event.key === Qt.Key_Escape) win.wheel.escape()
            else if (event.key === Qt.Key_Left || event.key === Qt.Key_Up) win.wheel.step(-1)
            else if (event.key === Qt.Key_Right || event.key === Qt.Key_Down) win.wheel.step(1)
            else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) win.wheel.confirm()
            else return
            event.accepted = true
        }
    }
}
