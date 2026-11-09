import QtQuick
import Eshab

// Details as a label over a value. Values can be selected; with copying on,
// each has its own copy button.
ListView {
    id: root

    property var rows: []
    property bool copyable: false
    property string copyWord: ""
    property string copiedWord: ""
    property string emptyWord: ""

    model: rows
    clip: true
    spacing: 4
    boundsBehavior: Flickable.StopAtBounds

    Text {
        anchors.centerIn: parent
        visible: root.count === 0 && root.emptyWord !== ""
        text: root.emptyWord
        color: Theme.textSecondary
        font.family: Theme.fontFamily
        font.pixelSize: 14
    }

    delegate: Rectangle {
        id: row
        property bool copied: false
        width: ListView.view.width
        height: Math.max(46, words.implicitHeight + 18)
        radius: 10
        color: hover.hovered ? (Theme.dark ? Qt.rgba(1, 1, 1, 0.05) : Qt.rgba(0, 0, 0, 0.035)) : "transparent"

        HoverHandler { id: hover }

        Column {
            id: words
            anchors.left: parent.left
            anchors.right: copy.visible ? copy.left : parent.right
            anchors.leftMargin: 12
            anchors.rightMargin: 12
            anchors.verticalCenter: parent.verticalCenter
            spacing: 2
            Text {
                width: parent.width
                text: modelData.label
                color: Theme.textSecondary
                elide: Text.ElideRight
                font.family: Theme.fontFamily
                font.pixelSize: 12
            }
            TextEdit {
                width: parent.width
                text: modelData.value
                readOnly: true
                selectByMouse: true
                wrapMode: TextEdit.Wrap
                color: Theme.text
                selectionColor: Theme.accent
                selectedTextColor: Theme.onAccent
                font.family: Theme.fontFamily
                font.pixelSize: 14
            }
        }
        IconButton {
            id: copy
            visible: root.copyable
            anchors.right: parent.right
            anchors.rightMargin: 6
            anchors.verticalCenter: parent.verticalCenter
            icon: row.copied ? "" : ""
            tip: row.copied ? root.copiedWord : root.copyWord
            onClicked: {
                editor.copyText(modelData.value)
                row.copied = true
                again.restart()
            }
            Timer { id: again; interval: 1600; onTriggered: row.copied = false }
        }
    }
}
