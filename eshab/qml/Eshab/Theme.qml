pragma Singleton
import QtQuick

// Design tokens shared by every Eshab surface. The material colours match
// eshab/identity/mark.py so the app icon and the in-app logo agree.
QtObject {
    // honey | clear | ink — chosen by the user, honey by default.
    property string material: "honey"
    property bool dark: true

    readonly property var materials: ({
        "honey": { "light": "#FFD985", "deep": "#DB7817", "accent": "#F2A33A", "onAccent": "#3D2204", "alpha": 0.97, "rim": 0.55 },
        "clear": { "light": "#FFFFFF", "deep": "#D5DCE8", "accent": "#F2F4F8", "onAccent": "#1C1C1E", "alpha": 0.34, "rim": 1.0 },
        "ink":   { "light": "#B3BCFF", "deep": "#3138C8", "accent": "#5560F0", "onAccent": "#FFFFFF", "alpha": 0.97, "rim": 0.5 }
    })
    readonly property var current: materials[material] || materials["honey"]
    readonly property color accent: material === "clear" && !dark ? "#2B2D31" : current.accent
    readonly property color onAccent: material === "clear" && !dark ? "#FFFFFF" : current.onAccent

    // Neutral glass: the surfaces stay clear whatever the material is.
    readonly property color text: dark ? "#F5F5F7" : "#1C1C1E"
    readonly property color textSecondary: dark ? "#A1A1A6" : "#5B5B60"
    readonly property color glassFill: dark ? Qt.rgba(0.11, 0.11, 0.13, 0.62) : Qt.rgba(1, 1, 1, 0.62)
    readonly property color glassRim: dark ? Qt.rgba(1, 1, 1, 0.20) : Qt.rgba(1, 1, 1, 0.92)
    readonly property color glassShade: dark ? Qt.rgba(0, 0, 0, 0.35) : Qt.rgba(0, 0, 0, 0.12)

    readonly property string fontFamily: "Segoe UI"
    // Windows' own icon font: Fluent on Windows 11, MDL2 on Windows 10.
    readonly property string iconFont: Qt.fontFamilies().indexOf("Segoe Fluent Icons") >= 0 ? "Segoe Fluent Icons" : "Segoe MDL2 Assets"
    readonly property int radius: 14

    // Motion: short, springy, never longer than it needs to be.
    readonly property int fast: 140
    readonly property int base: 240
    readonly property int slow: 420
}
