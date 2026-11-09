import QtQuick
import Eshab

// A whole number with − and + beside it, kept between its limits.
Row {
    id: root

    property int value: 0
    property int from: 0
    property int to: 100
    property int stepSize: 1
    property string unit: ""
    signal moved(int value)

    spacing: 6

    function set(v) {
        v = Math.max(from, Math.min(to, Math.round(v)))
        if (v !== value) root.moved(v)
    }

    EButton {
        compact: true
        text: "−"
        enabled: root.value > root.from
        onClicked: root.set(root.value - root.stepSize)
    }
    ETextField {
        id: field
        width: 92
        height: 30
        numeric: true
        text: String(root.value)
        onEdited: (words) => { if (words !== "") root.set(parseInt(words)) }
        Connections {
            target: root
            function onValueChanged() { if (!field.activeFocus || field.text !== String(root.value)) field.text = String(root.value) }
        }
    }
    EButton {
        compact: true
        text: "+"
        enabled: root.value < root.to
        onClicked: root.set(root.value + root.stepSize)
    }
    Text {
        anchors.verticalCenter: parent.verticalCenter
        text: root.unit
        visible: root.unit !== ""
        color: Theme.textSecondary
        font.family: Theme.fontFamily
        font.pixelSize: 13
    }
}
