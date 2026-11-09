import QtQuick

// The edges and corners of a frameless window, to size it like any other.
// A band around the card's edge, half outside it and half on it; the grips
// lie inside this item, so every part of them can be pressed.
Item {
    id: root

    property Item target
    property var window
    readonly property int band: 6

    anchors.fill: target
    anchors.margins: -band
    z: 100
    LayoutMirroring.enabled: false
    LayoutMirroring.childrenInherit: true

    function grab(edges) {
        if (enabled && window)
            window.startSystemResize(edges)
    }

    readonly property int span: band * 2      // how deep a grip reaches
    readonly property int corner: band * 4    // how long a corner grip is

    MouseArea {
        x: 0; y: root.corner
        width: root.span; height: root.height - root.corner * 2
        cursorShape: Qt.SizeHorCursor
        onPressed: root.grab(Qt.LeftEdge)
    }
    MouseArea {
        x: root.width - root.span; y: root.corner
        width: root.span; height: root.height - root.corner * 2
        cursorShape: Qt.SizeHorCursor
        onPressed: root.grab(Qt.RightEdge)
    }
    MouseArea {
        x: root.corner; y: 0
        width: root.width - root.corner * 2; height: root.span
        cursorShape: Qt.SizeVerCursor
        onPressed: root.grab(Qt.TopEdge)
    }
    MouseArea {
        x: root.corner; y: root.height - root.span
        width: root.width - root.corner * 2; height: root.span
        cursorShape: Qt.SizeVerCursor
        onPressed: root.grab(Qt.BottomEdge)
    }
    MouseArea {
        x: 0; y: 0
        width: root.corner; height: root.corner
        cursorShape: Qt.SizeFDiagCursor
        onPressed: root.grab(Qt.LeftEdge | Qt.TopEdge)
    }
    MouseArea {
        // Short, so it stays clear of the close button.
        x: root.width - root.corner; y: 0
        width: root.corner; height: root.span
        cursorShape: Qt.SizeBDiagCursor
        onPressed: root.grab(Qt.RightEdge | Qt.TopEdge)
    }
    MouseArea {
        x: 0; y: root.height - root.corner
        width: root.corner; height: root.corner
        cursorShape: Qt.SizeBDiagCursor
        onPressed: root.grab(Qt.LeftEdge | Qt.BottomEdge)
    }
    MouseArea {
        x: root.width - root.corner; y: root.height - root.corner
        width: root.corner; height: root.corner
        cursorShape: Qt.SizeFDiagCursor
        onPressed: root.grab(Qt.RightEdge | Qt.BottomEdge)
    }
}
