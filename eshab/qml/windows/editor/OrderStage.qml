import QtQuick
import Eshab

// Files to put in order: photos for a PDF, videos to join.
Item {
    id: root

    property var host
    readonly property bool ready: editor.itemList.length > (editor.toolKey === "vid.join" ? 1 : 0)
    readonly property string sorting: host.options.order !== undefined ? String(host.options.order) : "manual"
    property bool arranging: false

    function stateObject() {
        return { "order": grid.order() }
    }

    onSortingChanged: {
        if (sorting === "manual")
            return
        arranging = true
        grid.sortBy(sorting)
        arranging = false
    }

    OrderView {
        id: grid
        anchors.fill: parent
        anchors.margins: 18
        tile: 156
        onReordered: (order) => {
            editor.setOrder(JSON.stringify(order))
            if (!root.arranging && root.host.options.order !== undefined && root.host.options.order !== "manual")
                root.host.setOption("order", "manual")
        }
    }
}
