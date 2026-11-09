import QtQuick
import Eshab

// The collage's photos in one row, to put them in order.
Rectangle {
    id: root

    signal reordered(var order)
    function order() { return view.order() }

    radius: 14
    color: Theme.dark ? Qt.rgba(1, 1, 1, 0.04) : Qt.rgba(0, 0, 0, 0.03)

    OrderView {
        id: view
        anchors.fill: parent
        anchors.margins: 6
        strip: true
        onReordered: (order) => root.reordered(order)
    }
}
