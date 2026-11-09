import QtQuick

// Caption button at Windows' own size (46 x 32), drawn on the glass.
Item {
    id: root

    property string kind: "close"   // close | minimize | maximize | restore
    property string label: ""
    signal clicked()

    width: 46
    height: 32
    Accessible.role: Accessible.Button
    Accessible.name: label

    Rectangle {
        anchors.fill: parent
        radius: 8
        color: root.kind === "close"
               ? (area.pressed ? "#B4282C" : "#C42B1C")
               : (Theme.dark ? Qt.rgba(1, 1, 1, area.pressed ? 0.14 : 0.08) : Qt.rgba(0, 0, 0, area.pressed ? 0.10 : 0.05))
        opacity: area.containsMouse ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: Theme.fast } }
    }

    Canvas {
        id: glyph
        anchors.centerIn: parent
        width: 10
        height: 10
        property color ink: root.kind === "close" && area.containsMouse ? "#FFFFFF" : Theme.text
        property string shape: root.kind
        onInkChanged: requestPaint()
        onShapeChanged: requestPaint()
        onPaint: {
            const ctx = getContext("2d")
            ctx.reset()
            ctx.strokeStyle = ink
            ctx.lineWidth = 1
            ctx.beginPath()
            if (shape === "close") {
                ctx.moveTo(0.5, 0.5); ctx.lineTo(9.5, 9.5)
                ctx.moveTo(9.5, 0.5); ctx.lineTo(0.5, 9.5)
            } else if (shape === "maximize") {
                ctx.rect(0.5, 0.5, 9, 9)
            } else if (shape === "restore") {
                ctx.rect(0.5, 2.5, 7, 7)
                ctx.moveTo(2.5, 2.5); ctx.lineTo(2.5, 0.5); ctx.lineTo(9.5, 0.5); ctx.lineTo(9.5, 7.5); ctx.lineTo(7.5, 7.5)
            } else {
                ctx.moveTo(0, 5.5); ctx.lineTo(10, 5.5)
            }
            ctx.stroke()
        }
    }

    MouseArea {
        id: area
        anchors.fill: parent
        hoverEnabled: true
        onClicked: root.clicked()
    }
}
