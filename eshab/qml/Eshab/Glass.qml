import QtQuick

// Liquid glass: the frosted desktop behind this item, bent at the rim, with
// a neutral tint (or the material colour when selected), a lit rim and a
// soft shadow. Place it `pad` px larger than the glass on every side.
ShaderEffect {
    id: glass

    // Must be typed Item: a `var` is not picked up as the shader's texture.
    property Item frost: null             // an Image filled with the frosted backdrop
    property real frostWidth: frost ? frost.width : 1
    property real frostHeight: frost ? frost.height : 1
    property real fx: x                   // this item's position over the frost image
    property real fy: y
    property real radius: 18
    property real pad: 12
    property color tintColor: Theme.dark ? "#1C1C21" : "#FFFFFF"
    property real tintStrength: Theme.dark ? 0.58 : 0.62
    property color accentColor: Theme.accent
    property real accentStrength: 0
    property real rimStrength: 0.85
    property real shadowStrength: 0.26
    property real refraction: 5

    property vector4d frostRect: Qt.vector4d(fx / Math.max(1, frostWidth), fy / Math.max(1, frostHeight),
                                             width / Math.max(1, frostWidth), height / Math.max(1, frostHeight))
    property vector4d shape: Qt.vector4d(width, height, radius, pad)
    property vector4d tint: Qt.vector4d(tintColor.r, tintColor.g, tintColor.b, tintStrength)
    property vector4d accent: Qt.vector4d(accentColor.r, accentColor.g, accentColor.b, accentStrength)
    property vector4d light: Qt.vector4d(rimStrength, shadowStrength, refraction, Theme.dark ? 1 : 0)

    // Qt.resolvedUrl: as the root object, a bare relative path would resolve
    // against the file that uses Glass, not against this one.
    fragmentShader: Qt.resolvedUrl("shaders/glass.frag.qsb")
}
