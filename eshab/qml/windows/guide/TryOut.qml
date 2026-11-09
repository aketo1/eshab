import QtQuick
import Eshab

// The wheel, tried inside the guide: drag the sample file with a key held and
// a fan of cards opens where the file is; let go over a card. The keys are the
// ones set in Settings, read the same way the real wheel reads them.
Rectangle {
    id: root

    readonly property var masks: ({
        "actions": parse(eshab.setting("actionsWheelDragModifierMask")),
        "tools": parse(eshab.setting("toolsWheelDragModifierMask")),
        "conversion": parse(eshab.setting("conversionWheelDragModifierMask"))
    })
    property string wheel: ""
    property point center: Qt.point(0, 0)
    property int pick: -1
    property bool carrying: false
    property string message: ""
    readonly property var cards: wheel === "conversion" ? ["PDF", "TXT", "HTML", "MD", "RTF"]
        : wheel === "tools" ? [eshab.tr("guide.demo.compress"), eshab.tr("guide.demo.crop"), eshab.tr("guide.demo.edit_pdf"), eshab.tr("guide.demo.metadata")]
        : wheel === "actions" ? [eshab.tr("guide.demo.copy"), eshab.tr("guide.demo.move"), eshab.tr("guide.demo.shelf"), eshab.tr("guide.demo.path")]
        : []

    radius: 18
    color: Theme.dark ? Qt.rgba(1, 1, 1, 0.04) : Qt.rgba(0, 0, 0, 0.03)
    border.width: 1
    border.color: Theme.glassRim
    clip: true
    LayoutMirroring.enabled: false
    LayoutMirroring.childrenInherit: true

    function parse(text) {
        const set = {}
        for (const part of String(text || "").split("+"))
            if (part.trim()) set[part.trim()] = true
        return set
    }
    function wheelFor(modifiers) {
        const now = { "ctrl": !!(modifiers & Qt.ControlModifier), "alt": !!(modifiers & Qt.AltModifier),
                      "shift": !!(modifiers & Qt.ShiftModifier), "win": !!(modifiers & Qt.MetaModifier) }
        for (const kind of ["actions", "tools", "conversion"]) {
            const mask = masks[kind]
            let any = false, all = true
            for (const key in mask) { any = true; if (!now[key]) all = false }
            if (any && all) return kind
        }
        return ""
    }
    // Cards sit on an arc above where the fan opened.
    function spot(i, n) {
        const angle = (n > 1 ? 205 + 130 * i / (n - 1) : 270) * Math.PI / 180
        return Qt.point(center.x + 128 * Math.cos(angle), center.y + 118 * Math.sin(angle))
    }
    function fill(template, values) {
        let out = String(template)
        for (const key in values)
            out = out.split("{" + key + "}").join(String(values[key]))
        return out
    }
    // Where the sample rests: low in the middle (worked out from the size now,
    // not from a binding that may not have caught up yet).
    function home() {
        return Qt.point(width / 2 - sample.width / 2, height - sample.height - 22)
    }
    function place() {
        if (carrying || back.running)
            return
        const at = home()
        sample.x = at.x
        sample.y = at.y
    }
    function goHome() {
        const at = home()
        backX.to = at.x
        backY.to = at.y
        back.restart()
    }

    onWidthChanged: Qt.callLater(place)
    onHeightChanged: Qt.callLater(place)

    // What happened, for a few seconds.
    Rectangle {
        anchors.horizontalCenter: parent.horizontalCenter
        y: 14
        width: Math.min(parent.width - 40, said.implicitWidth + 30)
        height: said.implicitHeight + 14
        radius: height / 2
        color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.18)
        border.width: 1
        border.color: Theme.accent
        opacity: root.message !== "" ? 1 : 0
        visible: opacity > 0.01
        Behavior on opacity { NumberAnimation { duration: Theme.base } }
        Text {
            id: said
            anchors.centerIn: parent
            width: Math.min(implicitWidth, root.width - 70)
            text: root.message
            wrapMode: Text.WordWrap
            horizontalAlignment: Text.AlignHCenter
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: 13
            font.weight: Font.DemiBold
        }
    }
    Timer { id: forget; interval: 4200; onTriggered: root.message = "" }

    // The fan.
    Repeater {
        model: root.cards
        Rectangle {
            readonly property point at: root.spot(index, root.cards.length)
            readonly property bool chosen: root.pick === index
            x: at.x - width / 2
            y: at.y - height / 2
            width: Math.max(64, words.implicitWidth + 24)
            height: 44
            radius: 14
            color: chosen ? Theme.accent : (Theme.dark ? "#2C2C31" : "#FFFFFF")
            border.width: 1
            border.color: chosen ? Qt.darker(Theme.accent, 1.15) : Theme.glassRim
            scale: chosen ? 1.12 : 1
            Behavior on scale { NumberAnimation { duration: Theme.fast } }
            NumberAnimation on opacity { from: 0; to: 1; duration: Theme.base }
            Text {
                id: words
                anchors.centerIn: parent
                text: modelData
                color: parent.chosen ? Theme.onAccent : Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: 13
                font.weight: Font.DemiBold
            }
        }
    }

    // The sample file.
    Rectangle {
        id: sample
        width: 104
        height: 124
        radius: 16
        color: Theme.dark ? "#2C2C31" : "#FFFFFF"
        border.width: 1
        border.color: root.carrying ? Theme.accent : Theme.glassRim
        scale: root.carrying ? 0.84 : (grabArea.containsMouse ? 1.04 : 1)
        Behavior on scale { NumberAnimation { duration: Theme.fast } }
        Component.onCompleted: Qt.callLater(root.place)

        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            y: 18
            text: ""
            font.family: Theme.iconFont
            font.pixelSize: 44
            color: "#2B579A"
        }
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 12
            width: parent.width - 12
            horizontalAlignment: Text.AlignHCenter
            elide: Text.ElideMiddle
            text: eshab.tr("guide.try.sample")
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: 12
        }
        // While carried with no key yet: which key to press.
        Rectangle {
            visible: root.carrying && root.wheel === ""
            anchors.horizontalCenter: parent.horizontalCenter
            y: -height - 8
            width: keyText.implicitWidth + 20
            height: 26
            radius: 13
            color: Theme.accent
            Text {
                id: keyText
                anchors.centerIn: parent
                text: win_conversion_key()
                color: Theme.onAccent
                font.family: Theme.fontFamily
                font.pixelSize: 12
                font.weight: Font.DemiBold
                function win_conversion_key() { return eshab.maskLabel(eshab.setting("conversionWheelDragModifierMask") || "") }
            }
        }
    }
    ParallelAnimation {
        id: back
        NumberAnimation { id: backX; target: sample; property: "x"; duration: Theme.slow; easing.type: Easing.OutBack; easing.overshoot: 1.2 }
        NumberAnimation { id: backY; target: sample; property: "y"; duration: Theme.slow; easing.type: Easing.OutBack; easing.overshoot: 1.2 }
    }

    MouseArea {
        id: grabArea
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: root.carrying ? Qt.ClosedHandCursor : Qt.ArrowCursor
        property point grab
        onPressed: (mouse) => {
            const p = mapToItem(sample, mouse.x, mouse.y)
            root.carrying = sample.contains(p)
            if (!root.carrying) {
                mouse.accepted = false
                return
            }
            back.stop()
            grab = p
        }
        onPositionChanged: (mouse) => {
            if (!root.carrying)
                return
            sample.x = mouse.x - grab.x
            sample.y = mouse.y - grab.y
            const kind = root.wheelFor(mouse.modifiers)
            if (kind !== root.wheel) {
                root.wheel = kind
                root.center = Qt.point(Math.max(140, Math.min(root.width - 140, mouse.x)), Math.max(150, mouse.y))
                root.pick = -1
            }
            if (root.wheel !== "") {
                let best = -1, nearest = 72
                for (let i = 0; i < root.cards.length; i++) {
                    const at = root.spot(i, root.cards.length)
                    const d = Math.hypot(at.x - mouse.x, at.y - mouse.y)
                    if (d < nearest) { nearest = d; best = i }
                }
                root.pick = best
            }
        }
        onReleased: {
            if (root.carrying && root.wheel !== "" && root.pick >= 0) {
                const target = root.cards[root.pick]
                const words = root.wheel === "conversion" ? eshab.tr("guide.try.done")
                            : root.wheel === "tools" ? eshab.tr("guide.try.tools_done") : eshab.tr("guide.try.action_done")
                root.message = root.fill(words, { "target": target })
                forget.restart()
            }
            root.carrying = false
            root.wheel = ""
            root.pick = -1
            root.goHome()
        }
    }
}
