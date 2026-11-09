import QtQuick
import Eshab
import "Fmt.js" as Fmt

// The PDF editor: pages down the side, the chosen page large.
//   change - click a line of text to rewrite it (or remove it); click a
//            picture to replace or remove it
//   add    - drag a box where new text goes
//   hide   - drag over what must not be seen; it is removed for good
// Pages can be turned, copied, moved and removed. Every change can be undone.
Item {
    id: root

    property var host
    property int current: 0
    property string tool: "edit"
    property var elements: []
    property var pageSize: [612, 792]
    property int hovered: -1
    property int chosen: -1
    property real zoom: 1
    property real renderScale: 1
    readonly property int count: editor.pdfCount
    readonly property bool ready: editor.canUndo
    readonly property real k: page.width / Math.max(1, pageSize[0])     // screen pixels per point
    readonly property real dpr: Screen.devicePixelRatio

    function stateObject() {
        return {}
    }

    function refresh() {
        if (current >= count)
            current = Math.max(0, count - 1)
        try {
            pageSize = JSON.parse(editor.pdfPageSize(current))
            elements = JSON.parse(editor.pdfElements(current))
        } catch (e) {
            elements = []
        }
        hovered = -1
        closeEditors()
    }

    function report(problem) {
        root.host.problem = problem || ""
    }

    function closeEditors() {
        chosen = -1
        writer.visible = false
        picker.visible = false
    }

    function undo() {
        if (writer.visible) { closeEditors(); return }
        if (editor.canUndo) editor.pdfUndo()
    }

    function redo() {
        if (editor.canRedo) editor.pdfRedo()
    }

    function dismiss() {
        if (writer.visible || picker.visible) {
            closeEditors()
            return true
        }
        return false
    }

    function elementAt(px, py) {
        const x = px / k, y = py / k
        let best = -1, area = Infinity
        for (let i = 0; i < elements.length; i++) {
            const r = elements[i].rect
            if (x >= r[0] - 1 && x <= r[2] + 1 && y >= r[1] - 1 && y <= r[3] + 1) {
                const a = (r[2] - r[0]) * (r[3] - r[1])
                if (a < area) { area = a; best = i }
            }
        }
        return best
    }

    Connections {
        target: editor
        function onPdfChanged() { root.refresh() }
    }
    onCurrentChanged: refresh()
    Component.onCompleted: refresh()

    // -- the toolbar --------------------------------------------------------------
    Item {
        id: bar
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 12
        height: 38

        Row {
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            spacing: 4
            Segmented {
                anchors.verticalCenter: parent.verticalCenter
                options: [
                    { "value": "edit", "label": root.host.word("ed.edit_mode") },
                    { "value": "add", "label": root.host.word("ed.add_text") },
                    { "value": "hide", "label": root.host.word("ed.redact_area") }
                ]
                value: root.tool
                onPicked: (v) => { root.closeEditors(); root.tool = v }
            }
            Item { width: 10; height: 1 }
            IconButton {
                icon: ""
                mirrorIcon: eshab.rtl
                tip: root.host.word("ed.undo")
                enabled: editor.canUndo
                onClicked: root.undo()
            }
            IconButton {
                icon: ""
                mirrorIcon: eshab.rtl
                tip: root.host.word("ed.redo")
                enabled: editor.canRedo
                onClicked: root.redo()
            }
        }
        Row {
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            spacing: 2
            IconButton {
                icon: ""
                tip: root.host.word("ed.rotate")
                onClicked: root.report(editor.pdfRotate(root.current))
            }
            IconButton {
                icon: ""
                tip: root.host.word("ed.duplicate")
                onClicked: {
                    const problem = editor.pdfDuplicate(root.current)
                    root.report(problem)
                    if (!problem) root.current = root.current + 1
                }
            }
            IconButton {
                icon: ""
                tip: root.host.word("ed.move_up")
                enabled: root.current > 0
                onClicked: root.current = editor.pdfMove(root.current, -1)
            }
            IconButton {
                icon: ""
                tip: root.host.word("ed.move_down")
                enabled: root.current < root.count - 1
                onClicked: root.current = editor.pdfMove(root.current, 1)
            }
            IconButton {
                icon: ""
                danger: true
                tip: root.host.word("ed.delete")
                enabled: root.count > 1
                onClicked: root.report(editor.pdfDeletePage(root.current))
            }
            Item { width: 8; height: 1 }
            IconButton {
                icon: ""
                tip: root.host.word("ed.fit_page")
                enabled: root.zoom !== 1
                onClicked: root.zoom = 1
            }
        }
    }

    // -- the pages down the side ------------------------------------------------
    ListView {
        id: thumbs
        anchors.left: parent.left
        anchors.top: bar.bottom
        anchors.bottom: parent.bottom
        anchors.margins: 12
        width: 132
        clip: true
        spacing: 10
        model: root.count
        currentIndex: root.current
        boundsBehavior: Flickable.StopAtBounds
        highlightMoveDuration: Theme.base
        delegate: Item {
            width: thumbs.width
            height: thumbImage.height + 26
            Rectangle {
                id: thumbFrame
                anchors.horizontalCenter: parent.horizontalCenter
                width: thumbImage.width + 6
                height: thumbImage.height + 6
                radius: 6
                color: "transparent"
                border.width: index === root.current ? 2 : 1
                border.color: index === root.current ? Theme.accent : Theme.glassRim
                Image {
                    id: thumbImage
                    anchors.centerIn: parent
                    width: thumbs.width - 22
                    height: width * 1.3
                    fillMode: Image.PreserveAspectFit
                    asynchronous: true
                    cache: false
                    smooth: true
                    source: editor.pdfRevision >= 0 && root.count > 0 ? editor.pdfPage(index, 0.3) : ""
                }
            }
            Text {
                anchors.top: thumbFrame.bottom
                anchors.topMargin: 3
                anchors.horizontalCenter: parent.horizontalCenter
                text: index + 1
                color: index === root.current ? Theme.text : Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: 11
            }
            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: root.current = index
            }
        }
    }

    // -- the page ---------------------------------------------------------------
    Flickable {
        id: view
        anchors.left: thumbs.right
        anchors.right: parent.right
        anchors.top: bar.bottom
        anchors.bottom: parent.bottom
        anchors.margins: 12
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        interactive: root.tool === "edit" && !writer.visible
        contentWidth: Math.max(width, page.width + 40)
        contentHeight: Math.max(height, page.height + 40)

        WheelHandler {
            acceptedModifiers: Qt.ControlModifier
            onWheel: (event) => {
                root.zoom = Fmt.clamp(root.zoom * (event.angleDelta.y > 0 ? 1.1 : 1 / 1.1), 0.5, 4)
            }
        }

        Item {
            id: page
            // A page is the same way round in Arabic.
            LayoutMirroring.enabled: false
            LayoutMirroring.childrenInherit: true
            x: Math.max(20, (view.contentWidth - width) / 2)
            y: 20
            width: Math.max(120, (view.width - 40) * root.zoom)
            height: width * root.pageSize[1] / Math.max(1, root.pageSize[0])
            onWidthChanged: sharpen.restart()

            Rectangle {
                anchors.fill: parent
                anchors.margins: -1
                color: "white"
                border.width: 1
                border.color: Qt.rgba(0, 0, 0, 0.25)
            }
            SmoothImage {
                id: sheet
                anchors.fill: parent
                fillMode: Image.Stretch
                source: editor.pdfRevision >= 0 && root.count > 0 ? editor.pdfPage(root.current, root.renderScale) : ""
            }
            Timer {
                id: sharpen
                interval: 160
                onTriggered: root.renderScale = Math.round(page.width / Math.max(1, root.pageSize[0]) * root.dpr * 100) / 100
            }
            Component.onCompleted: sharpen.start()

            // The element under the mouse, or the one being changed.
            Rectangle {
                readonly property int which: root.chosen >= 0 ? root.chosen : root.hovered
                readonly property var r: which >= 0 && which < root.elements.length ? root.elements[which].rect : null
                visible: r !== null && root.tool === "edit"
                x: r ? r[0] * root.k - 2 : 0
                y: r ? r[1] * root.k - 2 : 0
                width: r ? (r[2] - r[0]) * root.k + 4 : 0
                height: r ? (r[3] - r[1]) * root.k + 4 : 0
                color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.12)
                border.width: 1.5
                border.color: Theme.accent
                radius: 2
            }

            // A box being dragged out (new text, or an area to hide).
            Rectangle {
                id: draft
                visible: false
                color: root.tool === "hide" ? Qt.rgba(0, 0, 0, 0.55) : Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.12)
                border.width: 1.5
                border.color: root.tool === "hide" ? "black" : Theme.accent
            }

            MouseArea {
                anchors.fill: parent
                enabled: !writer.visible && !picker.visible
                hoverEnabled: true
                cursorShape: root.tool === "edit" ? (root.hovered >= 0 ? Qt.PointingHandCursor : Qt.ArrowCursor) : Qt.CrossCursor
                preventStealing: root.tool !== "edit"
                property point from
                onPositionChanged: (mouse) => {
                    if (root.tool === "edit") {
                        root.hovered = root.elementAt(mouse.x, mouse.y)
                        return
                    }
                    if (!pressed)
                        return
                    draft.visible = true
                    draft.x = Math.max(0, Math.min(from.x, mouse.x))
                    draft.y = Math.max(0, Math.min(from.y, mouse.y))
                    draft.width = Math.min(page.width, Math.max(from.x, mouse.x)) - draft.x
                    draft.height = Math.min(page.height, Math.max(from.y, mouse.y)) - draft.y
                }
                onExited: if (root.tool === "edit") root.hovered = -1
                onPressed: (mouse) => {
                    from = Qt.point(mouse.x, mouse.y)
                    draft.visible = false
                }
                onReleased: (mouse) => {
                    const k = root.k
                    if (root.tool === "edit") {
                        const hit = root.elementAt(mouse.x, mouse.y)
                        if (hit < 0)
                            return
                        root.chosen = hit
                        if (root.elements[hit].kind === "text") writer.openFor(hit)
                        else picker.openFor(hit)
                        return
                    }
                    const dragged = draft.visible && draft.width > 6 && draft.height > 6
                    if (root.tool === "hide") {
                        if (dragged)
                            root.report(editor.pdfRedact(root.current, draft.x / k, draft.y / k, (draft.x + draft.width) / k, (draft.y + draft.height) / k))
                        draft.visible = false
                        return
                    }
                    // New text: the dragged box, or a line's worth where it was clicked.
                    let x0 = draft.x, y0 = draft.y, w = draft.width, h = draft.height
                    if (!dragged) {
                        w = Math.min(page.width - mouse.x, 220 * k)
                        h = 22 * k
                        x0 = mouse.x
                        y0 = Math.max(0, mouse.y - h / 2)
                    }
                    draft.visible = false
                    writer.openNew(x0, y0, Math.max(40, w), Math.max(18, h))
                }
            }

            // Rewriting a line, or writing a new one.
            Rectangle {
                id: writer
                visible: false
                property bool adding: false
                property real size: 12
                // Light words (white on a coloured panel) are typed on a dark box.
                property bool lightInk: false
                z: 10
                color: lightInk ? Qt.rgba(0.08, 0.08, 0.1, 0.88) : Qt.rgba(1, 1, 1, 0.94)
                border.width: 2
                border.color: Theme.accent
                radius: 3

                function openFor(i) {
                    const e = root.elements[i]
                    adding = false
                    size = e.size
                    x = e.rect[0] * root.k - 4
                    y = e.rect[1] * root.k - 4
                    width = Math.max(160, (e.rect[2] - e.rect[0]) * root.k + 8)
                    height = Math.max(30, (e.rect[3] - e.rect[1]) * root.k + 8)
                    words.color = e.color
                    const ink = Qt.color(e.color)
                    lightInk = 0.2126 * ink.r + 0.7152 * ink.g + 0.0722 * ink.b > 0.6
                    words.text = e.text
                    visible = true
                    words.forceActiveFocus()
                    words.selectAll()
                }
                function openNew(px, py, w, h) {
                    adding = true
                    size = 12
                    x = px
                    y = py
                    width = Math.max(160, w)
                    height = Math.max(30, h)
                    words.color = "#1C1C1E"
                    lightInk = false
                    words.text = ""
                    visible = true
                    words.forceActiveFocus()
                }
                function apply() {
                    const k = root.k
                    let problem = ""
                    if (adding)
                        problem = editor.pdfAddText(root.current, x / k, y / k, (x + width) / k, (y + height) / k, words.text, size)
                    else if (words.text !== root.elements[root.chosen].text)
                        problem = editor.pdfEditText(root.current, root.chosen, words.text)
                    root.report(problem)
                    if (!problem)
                        root.closeEditors()
                }

                TextEdit {
                    id: words
                    anchors.fill: parent
                    anchors.margins: 4
                    wrapMode: TextEdit.Wrap
                    font.family: Fmt.hasArabic(text) ? "Tahoma" : "Arial"
                    font.pixelSize: Math.max(8, writer.size * root.k)
                    selectByMouse: true
                    selectionColor: Theme.accent
                    selectedTextColor: Theme.onAccent
                    Keys.onReturnPressed: (event) => {
                        if (event.modifiers & Qt.ShiftModifier) event.accepted = false
                        else writer.apply()
                    }
                    Keys.onEnterPressed: writer.apply()
                    Keys.onEscapePressed: root.closeEditors()
                    Text {
                        anchors.fill: parent
                        visible: words.text === ""
                        text: root.host.word("ed.type_here")
                        color: writer.lightInk ? "#B0B0B6" : "#8A8A8E"
                        font: words.font
                    }
                }

            }

            // The writer's buttons, above it (or below it at the top of the page).
            Rectangle {
                visible: writer.visible
                z: 11
                x: Fmt.clamp(writer.x, 0, Math.max(0, page.width - width))
                y: writer.y >= height + 6 ? writer.y - height - 6 : writer.y + writer.height + 6
                width: tools.width + 12
                height: 40
                radius: 20
                color: Theme.dark ? "#2B2B30" : "#FFFFFF"
                border.width: 1
                border.color: Theme.dark ? Qt.rgba(1, 1, 1, 0.14) : Qt.rgba(0, 0, 0, 0.12)
                Row {
                    id: tools
                    anchors.centerIn: parent
                    spacing: 2
                    IconButton {
                        icon: ""
                        text: root.host.word("ed.apply")
                        active: true
                        onClicked: writer.apply()
                    }
                    IconButton {
                        visible: writer.adding
                        icon: ""
                        tip: root.host.word("ed.size_pt")
                        enabled: writer.size > 6
                        onClicked: writer.size = Math.max(6, writer.size - 1)
                    }
                    Text {
                        visible: writer.adding
                        anchors.verticalCenter: parent.verticalCenter
                        text: Math.round(writer.size) + " pt"
                        color: Theme.text
                        font.family: Theme.fontFamily
                        font.pixelSize: 12
                    }
                    IconButton {
                        visible: writer.adding
                        icon: ""
                        tip: root.host.word("ed.size_pt")
                        enabled: writer.size < 96
                        onClicked: writer.size = Math.min(96, writer.size + 1)
                    }
                    IconButton {
                        visible: !writer.adding
                        icon: ""
                        danger: true
                        tip: root.host.word("ed.delete")
                        onClicked: {
                            const problem = editor.pdfDeleteElement(root.current, root.chosen)
                            root.report(problem)
                            if (!problem) root.closeEditors()
                        }
                    }
                    IconButton {
                        icon: ""
                        tip: root.host.word("ed.cancel")
                        onClicked: root.closeEditors()
                    }
                }
            }

            // A picture's choices.
            Rectangle {
                id: picker
                visible: false
                z: 10
                width: pickerRow.width + 12
                height: 40
                radius: 20
                color: Theme.dark ? "#2B2B30" : "#FFFFFF"
                border.width: 1
                border.color: Theme.dark ? Qt.rgba(1, 1, 1, 0.14) : Qt.rgba(0, 0, 0, 0.12)

                function openFor(i) {
                    const r = root.elements[i].rect
                    x = Fmt.clamp(r[0] * root.k, 0, Math.max(0, page.width - width))
                    y = r[1] * root.k > 50 ? r[1] * root.k - 46 : r[3] * root.k + 6
                    visible = true
                }

                Row {
                    id: pickerRow
                    anchors.centerIn: parent
                    spacing: 2
                    IconButton {
                        icon: ""
                        text: root.host.word("ed.replace_image")
                        onClicked: {
                            const problem = editor.pdfReplaceImage(root.current, root.chosen)
                            root.report(problem)
                            root.closeEditors()
                        }
                    }
                    IconButton {
                        icon: ""
                        danger: true
                        tip: root.host.word("ed.delete")
                        onClicked: {
                            const problem = editor.pdfDeleteElement(root.current, root.chosen)
                            root.report(problem)
                            root.closeEditors()
                        }
                    }
                    IconButton {
                        icon: ""
                        tip: root.host.word("ed.cancel")
                        onClicked: root.closeEditors()
                    }
                }
            }
        }
    }

    Rectangle {
        anchors.horizontalCenter: view.horizontalCenter
        anchors.bottom: view.bottom
        anchors.bottomMargin: 10
        width: pageWords.implicitWidth + 22
        height: 26
        radius: 13
        color: Qt.rgba(0, 0, 0, 0.55)
        Text {
            id: pageWords
            anchors.centerIn: parent
            text: Fmt.fill(root.host.word("ed.page"), { "n": (root.current + 1) + " / " + root.count })
            color: "white"
            font.family: Theme.fontFamily
            font.pixelSize: 12
        }
    }
}
