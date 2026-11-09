import QtQuick
import Eshab
import "Fmt.js" as Fmt

// Hide parts of a photo: drag over each part; the boxes show the result.
Item {
    id: root

    property var host
    readonly property bool ready: frame.picture.ready && boxes.count > 0
    property bool searching: false

    function stateObject() {
        return { "boxes": boxes.list() }
    }

    function act(key) {
        if (key !== "faces" || searching)
            return
        searching = true
        faceSearch.start()          // after "Working…" has been drawn
    }

    Timer {
        id: faceSearch
        interval: 60
        onTriggered: {
            let found = []
            try { found = JSON.parse(editor.findFaces()) } catch (e) { found = [] }
            for (const face of found) {
                // A little room around each face, so hair and chin are hidden too.
                const grow = 0.18
                boxes.add(face.x - face.w * grow, face.y - face.h * grow, face.w * (1 + 2 * grow), face.h * (1 + 2 * grow))
            }
            root.searching = false
            root.host.note = found.length ? "" : root.host.word("ed.nothing_found")
        }
    }

    function deleteSelected() {
        boxes.remove(boxes.selected)
    }

    function undo() {
        boxes.remove(boxes.count - 1)
    }

    PictureFrame {
        id: frame
        anchors.fill: parent
        anchors.bottomMargin: 46
        inset: 28
        source: editor.sourceUrl
        sourceWidth: Math.max(1, editor.imageWidth)
        sourceHeight: Math.max(1, editor.imageHeight)

        BoxLayer {
            id: boxes
            sourceWidth: frame.sourceWidth
            sourceHeight: frame.sourceHeight
            scaleFactor: frame.scaleFactor
            originX: frame.originX
            originY: frame.originY
            mode: String(root.host.options.mode || "blur")
            tint: String(root.host.options.color || "#1C1C1E")
            pictureItem: frame.picture
        }
    }

    Row {
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 8
        spacing: 6
        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: root.searching ? root.host.word("ed.working") : Fmt.fill(root.host.word("ed.boxes"), { "n": boxes.count })
            color: Theme.textSecondary
            font.family: Theme.fontFamily
            font.pixelSize: 12
        }
        IconButton {
            icon: ""
            mirrorIcon: eshab.rtl
            tip: root.host.word("ed.undo")
            enabled: boxes.count > 0
            onClicked: root.undo()
        }
        IconButton {
            icon: ""
            tip: root.host.word("ed.clear")
            danger: true
            enabled: boxes.count > 0
            onClicked: boxes.clear()
        }
    }
}
