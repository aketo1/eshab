import QtQuick

// A picture that changes gently: the new one loads behind the one on show,
// then fades in over it (a colour, a light or a background melts into the
// next instead of jumping).
Item {
    id: root

    property string source: ""
    property int fillMode: Image.PreserveAspectFit
    property int fade: 280
    property bool frontFirst: true
    readonly property Image front: frontFirst ? first : second
    readonly property bool ready: first.status === Image.Ready || second.status === Image.Ready
    readonly property real paintedWidth: front.paintedWidth
    readonly property real paintedHeight: front.paintedHeight
    readonly property size naturalSize: front.sourceSize

    onSourceChanged: {
        if (fadeIn.running) {           // a change still fading: let it arrive at once
            fadeIn.stop()
            fadeIn.target.opacity = 1
            settle()
        }
        const back = frontFirst ? second : first
        back.opacity = 0
        back.z = 1
        front.z = 0
        back.source = source
    }

    // The faded-in picture becomes the one on show; the other steps back.
    function settle() {
        if (!fadeIn.target)
            return
        frontFirst = fadeIn.target === first
        const old = frontFirst ? second : first
        old.opacity = 0
    }

    function arrived(picture) {
        if (String(picture.source) !== root.source || picture.status !== Image.Ready)
            return
        fadeIn.target = picture
        fadeIn.restart()
    }

    NumberAnimation {
        id: fadeIn
        property: "opacity"
        from: 0
        to: 1
        duration: root.fade
        easing.type: Easing.InOutQuad
        onFinished: root.settle()
    }

    Image {
        id: first
        anchors.fill: parent
        fillMode: root.fillMode
        asynchronous: true
        cache: false
        smooth: true
        mipmap: true
        opacity: 0
        visible: opacity > 0
        onStatusChanged: root.arrived(first)
    }
    Image {
        id: second
        anchors.fill: parent
        fillMode: root.fillMode
        asynchronous: true
        cache: false
        smooth: true
        mipmap: true
        opacity: 0
        visible: opacity > 0
        onStatusChanged: root.arrived(second)
    }
}
