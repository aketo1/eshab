import QtQuick
import Eshab

// One option of a tool, drawn from its description (eshab/editor_app.py):
// choice, slider, toggle, color, text, number, picture or button.
Column {
    id: root

    property var field: ({})
    property var value
    property string chooseWord: ""
    property string noneWord: ""
    signal edited(var value)
    signal pressed(string key)

    spacing: 8

    readonly property string kind: field.type || ""
    readonly property bool labelled: kind !== "toggle" && kind !== "button"

    function shown(v) {
        if (kind !== "slider")
            return ""
        const sign = field.centered && v > 0 ? "+" : ""
        return sign + Math.round(v) + (field.unit ? (field.unit === "°" ? "°" : " " + field.unit) : "")
    }

    Item {
        visible: root.labelled
        width: parent.width
        height: 18
        Text {
            anchors.left: parent.left
            anchors.right: amount.left
            anchors.rightMargin: 8
            text: root.field.label || ""
            color: Theme.text
            elide: Text.ElideRight
            font.family: Theme.fontFamily
            font.pixelSize: 13
            font.weight: Font.DemiBold
        }
        Text {
            id: amount
            anchors.right: parent.right
            visible: root.kind === "slider"
            text: root.shown(Number(root.value))
            color: Theme.textSecondary
            font.family: Theme.fontFamily
            font.pixelSize: 12
        }
    }

    Loader {
        width: parent.width
        sourceComponent: {
            switch (root.kind) {
            case "choice": return choiceKind
            case "slider": return sliderKind
            case "toggle": return toggleKind
            case "color": return colorKind
            case "text": return textKind
            case "number": return numberKind
            case "picture": return pictureKind
            case "button": return buttonKind
            }
            return null
        }
    }

    Component {
        id: choiceKind
        Segmented {
            options: root.field.options
            value: root.value
            onPicked: (v) => root.edited(v)
        }
    }
    Component {
        id: sliderKind
        ESlider {
            from: root.field.min
            to: root.field.max
            stepSize: root.field.step || 1
            value: Number(root.value)
            resetTo: root.field.default
            centered: !!root.field.centered
            onMoved: (v) => root.edited(v)
        }
    }
    Component {
        id: toggleKind
        ESwitch {
            text: root.field.label
            checked: !!root.value
            onToggled: (on) => root.edited(on)
        }
    }
    Component {
        id: colorKind
        ColorPick {
            colors: root.field.colors || []
            value: String(root.value || "#000000")
            onPicked: (v) => root.edited(v)
        }
    }
    Component {
        id: textKind
        ETextField {
            text: root.value === undefined || root.value === null ? "" : String(root.value)
            onEdited: (words) => root.edited(words)
        }
    }
    Component {
        id: numberKind
        ENumber {
            from: root.field.min
            to: root.field.max
            stepSize: root.field.step || 1
            value: Number(root.value)
            unit: root.field.unit || ""
            onMoved: (v) => root.edited(v)
        }
    }
    Component {
        id: pictureKind
        Row {
            spacing: 8
            Rectangle {
                width: 44
                height: 44
                radius: 10
                clip: true
                color: Theme.dark ? Qt.rgba(1, 1, 1, 0.06) : Qt.rgba(0, 0, 0, 0.05)
                border.width: 1
                border.color: Theme.glassRim
                Image {
                    anchors.fill: parent
                    anchors.margins: 1
                    visible: !!root.value
                    source: root.value ? "file:///" + String(root.value).replace(/\\/g, "/") : ""
                    fillMode: Image.PreserveAspectCrop
                    asynchronous: true
                    sourceSize: Qt.size(96, 96)
                }
                Text {
                    anchors.centerIn: parent
                    visible: !root.value
                    text: ""
                    font.family: Theme.iconFont
                    font.pixelSize: 16
                    color: Theme.textSecondary
                }
            }
            EButton {
                anchors.verticalCenter: parent.verticalCenter
                text: root.chooseWord
                onClicked: {
                    const chosen = editor.pickPicture()
                    if (chosen)
                        root.edited(chosen)
                }
            }
            IconButton {
                anchors.verticalCenter: parent.verticalCenter
                visible: !!root.value
                icon: ""
                tip: root.noneWord
                onClicked: root.edited("")
            }
        }
    }
    Component {
        id: buttonKind
        EButton {
            text: root.field.label
            onClicked: root.pressed(root.field.key)
        }
    }
}
