import QtQuick
import Eshab

// Details to read: what QR codes say (each one copyable), or what a PDF says
// about itself while its details are edited beside it.
Item {
    id: root

    property var host
    readonly property bool qr: host.spec.mode === "qr"
    readonly property bool ready: qr ? editor.infoRows.length > 0 : true

    function stateObject() {
        return {}
    }

    Text {
        id: heading
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 22
        text: root.qr ? root.host.word("ed.results") : root.host.word("ed.info")
        color: Theme.text
        font.family: Theme.fontFamily
        font.pixelSize: 15
        font.weight: Font.DemiBold
    }
    InfoList {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: heading.bottom
        anchors.bottom: parent.bottom
        anchors.margins: 14
        anchors.topMargin: 10
        rows: editor.infoRows
        copyable: root.qr
        copyWord: root.host.word("ed.copy")
        copiedWord: root.host.word("ed.copied")
        emptyWord: root.host.word("ed.nothing_found")
    }
}
