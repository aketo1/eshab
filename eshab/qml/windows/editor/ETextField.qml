import QtQuick
import Eshab

// One line of text on the glass. Arabic or English, it runs the way it is typed.
Rectangle {
    id: root

    property alias text: input.text
    property string placeholder: ""
    property bool numeric: false
    signal edited(string text)
    signal accepted()

    implicitHeight: 36
    implicitWidth: 240
    radius: 10
    color: Theme.dark ? Qt.rgba(0, 0, 0, 0.22) : Qt.rgba(1, 1, 1, 0.7)
    border.width: input.activeFocus ? 2 : 1
    border.color: input.activeFocus ? Theme.accent : Theme.glassRim

    function focusText() { input.forceActiveFocus(); input.selectAll() }

    TextInput {
        id: input
        anchors.fill: parent
        anchors.leftMargin: 12
        anchors.rightMargin: 12
        verticalAlignment: TextInput.AlignVCenter
        color: Theme.text
        selectionColor: Theme.accent
        selectedTextColor: Theme.onAccent
        font.family: Theme.fontFamily
        font.pixelSize: 14
        clip: true
        selectByMouse: true
        inputMethodHints: root.numeric ? Qt.ImhFormattedNumbersOnly : Qt.ImhNone
        validator: root.numeric ? digits : null
        onTextEdited: root.edited(text)
        onAccepted: root.accepted()
        IntValidator { id: digits; bottom: 0 }
    }
    Text {
        anchors.fill: input
        verticalAlignment: Text.AlignVCenter
        text: root.placeholder
        visible: !input.text && !input.activeFocus
        color: Theme.textSecondary
        opacity: 0.7
        font: input.font
        elide: Text.ElideRight
    }
}
