import QtQuick
import QtQuick.Effects
import Eshab
import "editor"
import "editor/Fmt.js" as Fmt

// Every Eshab editor, built from its tool's description (eshab/editor_app.py):
// the file large on one side, the tool's options on the other, Save below.
// When the work is done the island at the top of the screen shows the result
// and this window closes.
Window {
    id: win

    readonly property var spec: JSON.parse(editor.spec)
    readonly property var words: spec.words
    readonly property string preview: spec.preview
    readonly property var fields: spec.fields
    readonly property bool loaded: !editor.loading
    property var options: ({})
    property string note: ""
    property string problem: ""
    property bool leaving: false
    property bool zoomed: false
    property rect normal: Qt.rect(0, 0, 0, 0)
    readonly property real margin: zoomed ? 0 : 18
    readonly property int shownFields: {
        let n = 0
        for (const f of fields)
            if (shows(f)) n++
        return n
    }
    readonly property Item stageItem: stage.item
    readonly property bool canSave: loaded && !editor.broken && !editor.busy && stageItem !== null && !!stageItem.ready

    width: preview === "info" ? 860 : 1180
    height: preview === "info" ? 620 : 790
    minimumWidth: 640
    minimumHeight: 480
    color: "transparent"
    flags: Qt.Window | Qt.FramelessWindowHint
    title: editor.title

    LayoutMirroring.enabled: eshab.rtl
    LayoutMirroring.childrenInherit: true

    function word(key) {
        return words[key] !== undefined ? words[key] : eshab.tr(key)
    }

    // A field shows when the options it depends on have the values it needs.
    // (A list may reach here as a Qt sequence rather than a JavaScript array,
    // so it is recognised by its length, not by Array.isArray.)
    function shows(field) {
        if (!field.when)
            return true
        for (const key in field.when) {
            const want = field.when[key], have = options[key]
            const many = want !== null && typeof want === "object" && typeof want.length === "number"
            if (many ? Array.prototype.indexOf.call(want, have) < 0 : want !== have)
                return false
        }
        return true
    }

    function setOption(key, value) {
        const next = Object.assign({}, options)
        next[key] = value
        options = next
        problem = ""
        note = ""
        refreshPreview()
    }

    function refreshPreview() {
        if (spec.live)
            live.restart()
    }

    function save() {
        if (!canSave)
            return
        problem = ""
        note = ""
        const state = stageItem.stateObject ? stageItem.stateObject() : {}
        editor.run(JSON.stringify(options), JSON.stringify(state))
        if (spec.mode === "qr")
            note = word("ed.copied_all")
    }

    function leave() {
        if (editor.busy) {
            leaving = true
            editor.cancel()
            return
        }
        win.close()
    }

    function toggleZoom() {
        if (zoomed) {
            zoomed = false
            win.x = normal.x
            win.y = normal.y
            win.width = normal.width
            win.height = normal.height
            return
        }
        normal = Qt.rect(win.x, win.y, win.width, win.height)
        const area = eshab.workArea(win.x + win.width / 2, win.y + win.height / 2)
        zoomed = true
        win.x = area.x
        win.y = area.y
        win.width = area.width
        win.height = area.height
    }

    function startStage() {
        if (!loaded || editor.broken || stage.status !== Loader.Null)
            return
        const files = { "image": "ImageStage", "crop": "CropStage", "boxes": "BoxesStage", "annotate": "AnnotateStage",
                        "order": "OrderStage", "waveform": "WaveStage", "video": "VideoStage", "info": "InfoStage", "pdf": "PdfStage" }
        if (files[preview])
            stage.setSource("editor/" + files[preview] + ".qml", { "host": win })
    }

    function takeInitial() {
        const found = editor.initialOptions
        if (!found)
            return
        const next = Object.assign({}, options)
        let any = false
        for (const key in found)
            if (key in next && found[key] !== "") { next[key] = found[key]; any = true }
        if (any)
            options = next
    }

    Component.onCompleted: {
        const start = {}
        for (const f of fields)
            if (f.key && f.type !== "button")
                start[f.key] = f.default
        options = start
        // Sized to fit the screen it opens on, in its middle.
        const area = eshab.workArea(-1, -1)
        width = Math.min(width, area.width - 24)
        height = Math.min(height, area.height - 24)
        x = area.x + Math.round((area.width - width) / 2)
        y = area.y + Math.round((area.height - height) / 2)
        if (loaded) {
            takeInitial()
            startStage()
        }
    }

    onLoadedChanged: {
        if (!loaded)
            return
        takeInitial()
        startStage()
    }

    onClosing: (close) => {
        if (editor.busy) {
            close.accepted = false
            leave()
        }
    }

    Connections {
        target: editor
        function onJobChanged() {
            if (win.leaving && !editor.busy)
                win.close()
        }
    }

    Timer {
        id: live
        interval: 140
        onTriggered: editor.preview(JSON.stringify(win.options))
    }

    // -- the glass ----------------------------------------------------------------------------
    Rectangle {
        id: shadowShape
        anchors.fill: card
        radius: card.radius
        color: "black"
        visible: false
        layer.enabled: true
    }
    MultiEffect {
        anchors.fill: shadowShape
        source: shadowShape
        visible: !win.zoomed
        blurEnabled: true
        blurMax: 32
        blur: 1.0
        opacity: Theme.dark ? 0.5 : 0.2
        anchors.topMargin: 6
        anchors.bottomMargin: -6
    }

    Backdrop {
        id: card
        anchors.fill: parent
        anchors.margins: win.margin
        window: win
        radius: win.zoomed ? 0 : 22
        opacity: 0
        scale: 0.985

        Component.onCompleted: appear.start()
        ParallelAnimation {
            id: appear
            NumberAnimation { target: card; property: "opacity"; to: 1; duration: Theme.base; easing.type: Easing.OutCubic }
            NumberAnimation { target: card; property: "scale"; to: 1; duration: Theme.slow; easing.type: Easing.OutBack; easing.overshoot: 1.1 }
        }

        // -- the title ----------------------------------------------------------------------
        Item {
            id: header
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            height: 64

            DragHandler {
                target: null
                onActiveChanged: {
                    if (!active)
                        return
                    if (win.zoomed)
                        win.toggleZoom()
                    win.startSystemMove()
                }
            }
            TapHandler {
                onDoubleTapped: win.toggleZoom()
            }

            Logo {
                id: mark
                anchors.left: parent.left
                anchors.leftMargin: 20
                anchors.verticalCenter: parent.verticalCenter
                size: 34
                progress: editor.busy ? Math.max(0.06, editor.progress) : (win.loaded ? -1 : 0.4)
            }
            Column {
                anchors.left: mark.right
                anchors.leftMargin: 12
                anchors.right: buttons.left
                anchors.rightMargin: 12
                anchors.verticalCenter: parent.verticalCenter
                spacing: 1
                // Aligned to the start of the line whatever the words' own
                // direction, so an English file name sits under an Arabic title.
                Text {
                    width: parent.width
                    horizontalAlignment: Text.AlignLeft
                    text: editor.title
                    color: Theme.text
                    elide: Text.ElideRight
                    font.family: Theme.fontFamily
                    font.pixelSize: 16
                    font.weight: Font.DemiBold
                }
                Text {
                    width: parent.width
                    horizontalAlignment: Text.AlignLeft
                    text: editor.subtitle
                    color: Theme.textSecondary
                    elide: Text.ElideMiddle
                    font.family: Theme.fontFamily
                    font.pixelSize: 12
                }
            }
            Row {
                id: buttons
                anchors.right: parent.right
                anchors.rightMargin: 10
                anchors.top: parent.top
                anchors.topMargin: 10
                spacing: 2
                WindowButton {
                    kind: "minimize"
                    label: win.word("window.minimize")
                    onClicked: win.showMinimized()
                }
                WindowButton {
                    kind: win.zoomed ? "restore" : "maximize"
                    label: win.zoomed ? win.word("window.restore") : win.word("window.maximize")
                    onClicked: win.toggleZoom()
                }
                WindowButton {
                    kind: "close"
                    label: win.word("ed.close")
                    onClicked: win.leave()
                }
            }
        }

        // -- the file and the options ----------------------------------------------------------
        Item {
            id: body
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: header.bottom
            anchors.bottom: footer.top
            anchors.leftMargin: 16
            anchors.rightMargin: 16

            Rectangle {
                id: stageBox
                anchors.left: parent.left
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                anchors.right: panel.visible ? panel.left : parent.right
                anchors.rightMargin: panel.visible ? 14 : 0
                radius: 16
                color: Theme.dark ? Qt.rgba(0, 0, 0, 0.24) : Qt.rgba(1, 1, 1, 0.5)
                border.width: 1
                border.color: Theme.dark ? Qt.rgba(1, 1, 1, 0.06) : Qt.rgba(0, 0, 0, 0.06)
                clip: true

                Loader {
                    id: stage
                    anchors.fill: parent
                    opacity: status === Loader.Ready ? 1 : 0
                    Behavior on opacity { NumberAnimation { duration: Theme.base } }
                }

                Column {
                    anchors.centerIn: parent
                    visible: !win.loaded
                    spacing: 14
                    Logo {
                        anchors.horizontalCenter: parent.horizontalCenter
                        size: 76
                        progress: 0.42
                    }
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: win.word("ed.loading")
                        color: Theme.textSecondary
                        font.family: Theme.fontFamily
                        font.pixelSize: 14
                    }
                }

                Column {
                    anchors.centerIn: parent
                    width: Math.min(parent.width - 60, 440)
                    visible: win.loaded && editor.broken
                    spacing: 8
                    Text {
                        width: parent.width
                        horizontalAlignment: Text.AlignHCenter
                        text: ""
                        font.family: Theme.iconFont
                        font.pixelSize: 30
                        color: "#E5484D"
                    }
                    Text {
                        width: parent.width
                        horizontalAlignment: Text.AlignHCenter
                        text: win.word("ed.failed")
                        color: Theme.text
                        font.family: Theme.fontFamily
                        font.pixelSize: 17
                        font.weight: Font.DemiBold
                    }
                    Text {
                        width: parent.width
                        horizontalAlignment: Text.AlignHCenter
                        text: editor.error
                        color: Theme.textSecondary
                        wrapMode: Text.WordWrap
                        font.family: Theme.fontFamily
                        font.pixelSize: 13
                    }
                }
            }

            Item {
                id: panel
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                width: Math.min(310, Math.max(250, body.width * 0.28))
                visible: win.shownFields > 0 && !editor.broken

                Flickable {
                    id: fieldScroll
                    anchors.fill: parent
                    contentHeight: fieldColumn.height + 16
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds

                    Column {
                        id: fieldColumn
                        x: 4
                        y: 6
                        width: fieldScroll.width - 10
                        spacing: 20

                        Repeater {
                            model: win.fields
                            FieldView {
                                width: fieldColumn.width
                                visible: win.shows(modelData)
                                field: modelData
                                value: win.options[modelData.key]
                                chooseWord: win.word("ed.choose")
                                noneWord: win.word("ed.none")
                                enabled: !editor.busy && win.loaded
                                onEdited: (v) => win.setOption(modelData.key, v)
                                onPressed: (key) => {
                                    if (win.stageItem && win.stageItem.act)
                                        win.stageItem.act(key)
                                }
                            }
                        }
                    }
                }
            }
        }

        // -- what is happening, and Save -----------------------------------------------------------
        Item {
            id: footer
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            anchors.leftMargin: 20
            anchors.rightMargin: 16
            height: 72

            Column {
                anchors.left: parent.left
                anchors.right: actions.left
                anchors.rightMargin: 18
                anchors.verticalCenter: parent.verticalCenter
                spacing: 7

                Text {
                    readonly property string trouble: editor.busy ? "" : (win.problem !== "" ? win.problem : (editor.broken ? "" : editor.error))
                    width: parent.width
                    text: editor.busy ? (editor.status !== "" ? editor.status : win.word("ed.working"))
                                      : (trouble !== "" ? trouble : (win.note !== "" ? win.note : win.spec.hint))
                    color: trouble !== "" ? "#E5484D" : Theme.textSecondary
                    wrapMode: Text.WordWrap
                    maximumLineCount: 2
                    elide: Text.ElideRight
                    font.family: Theme.fontFamily
                    font.pixelSize: 13
                }
                Rectangle {
                    visible: editor.busy
                    width: parent.width
                    height: 4
                    radius: 2
                    clip: true
                    color: Theme.dark ? Qt.rgba(1, 1, 1, 0.1) : Qt.rgba(0, 0, 0, 0.08)
                    Rectangle {
                        id: fill
                        readonly property bool known: editor.progress >= 0
                        property real sweep: 0
                        height: parent.height
                        radius: 2
                        color: Theme.accent
                        width: known ? parent.width * Fmt.clamp(editor.progress, 0, 1) : parent.width * 0.28
                        x: known ? (eshab.rtl ? parent.width - width : 0) : sweep
                        Behavior on width { enabled: fill.known; NumberAnimation { duration: Theme.base } }
                        NumberAnimation on sweep {
                            running: editor.busy && !fill.known
                            from: -fill.width
                            to: fill.parent ? fill.parent.width : 300
                            duration: 1100
                            loops: Animation.Infinite
                        }
                    }
                }
            }

            Row {
                id: actions
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                spacing: 10
                EButton {
                    text: win.word("ed.cancel")
                    onClicked: win.leave()
                }
                EButton {
                    kind: "primary"
                    text: editor.busy ? win.word("ed.working") : win.spec.action
                    enabled: win.canSave
                    onClicked: win.save()
                }
            }
        }
    }

    ResizeGrips {
        target: card
        window: win
        enabled: !win.zoomed
        visible: !win.zoomed
    }

    Shortcut {
        sequence: "Esc"
        onActivated: {
            if (win.stageItem && win.stageItem.dismiss && win.stageItem.dismiss())
                return
            win.leave()
        }
    }
    Shortcut {
        sequence: "Ctrl+S"
        onActivated: win.save()
    }
    Shortcut {
        sequences: [StandardKey.Undo]
        onActivated: if (win.stageItem && win.stageItem.undo) win.stageItem.undo()
    }
    Shortcut {
        sequences: [StandardKey.Redo]
        onActivated: if (win.stageItem && win.stageItem.redo) win.stageItem.redo()
    }
    Shortcut {
        sequences: [StandardKey.Delete]
        onActivated: if (win.stageItem && win.stageItem.deleteSelected) win.stageItem.deleteSelected()
    }
}
