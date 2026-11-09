import QtQuick
import Eshab
import "Fmt.js" as Fmt

// Crop a photo: the box keeps what is inside it, in the chosen shape.
Item {
    id: root

    property var host
    readonly property bool ready: frame.picture.ready && crop.box.w >= 1 && crop.box.h >= 1

    function stateObject() {
        return { "box": crop.rounded() }
    }

    PictureFrame {
        id: frame
        anchors.fill: parent
        anchors.bottomMargin: 46
        inset: 28
        source: editor.sourceUrl
        sourceWidth: Math.max(1, editor.imageWidth)
        sourceHeight: Math.max(1, editor.imageHeight)

        CropBox {
            id: crop
            sourceWidth: frame.sourceWidth
            sourceHeight: frame.sourceHeight
            scaleFactor: frame.scaleFactor
            originX: frame.originX
            originY: frame.originY
            ratio: Fmt.ratio(root.host.options.aspect, frame.sourceWidth, frame.sourceHeight)
        }
    }

    IconButton {
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 8
        icon: ""
        text: root.host.word("ed.reset")
        onClicked: crop.reset()
    }
}
