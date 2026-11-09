import QtQuick
import QtQuick.Effects
import Eshab
import "editor"

// «إعدادات اسحب»: the look, the keys that open each wheel, how Eshab behaves,
// and how documents become PDF. Every choice applies at once (a new
// language after a restart, offered right here).
Window {
    id: win

    property int rev: 0
    readonly property var masks: eshab.maskChoices
    readonly property var wheelKeys: ["conversionWheelDragModifierMask", "toolsWheelDragModifierMask", "actionsWheelDragModifierMask"]
    readonly property bool clash: {
        const seen = {}
        for (const key of wheelKeys) {
            const mask = value(key)
            if (!mask) continue
            if (seen[mask]) return true
            seen[mask] = true
        }
        return false
    }

    width: 720
    height: 680
    minimumWidth: 560
    minimumHeight: 460
    color: "transparent"
    flags: Qt.Window | Qt.FramelessWindowHint
    title: eshab.tr("settings.title")

    LayoutMirroring.enabled: eshab.rtl
    LayoutMirroring.childrenInherit: true

    function value(key) { return win.rev >= 0 ? eshab.setting(key) : undefined }
    function put(key, v) { eshab.setSetting(key, v) }
    function choices(prefix, values) { return values.map((v) => ({ "value": v, "label": eshab.tr(prefix + v) })) }

    Connections {
        target: eshab
        function onChanged() { win.rev++ }
    }

    Rectangle {
        id: shadowShape
        anchors.fill: card
        radius: card.radius
        color: "black"
        visible: false
        layer.enabled: true
    }
    MultiEffect {
        anchors.fill: shadowShape
        source: shadowShape
        blurEnabled: true
        blurMax: 32
        blur: 1.0
        opacity: Theme.dark ? 0.5 : 0.2
        anchors.topMargin: 6
        anchors.bottomMargin: -6
    }

    Backdrop {
        id: card
        anchors.fill: parent
        anchors.margins: 18
        window: win
        radius: 22

        Item {
            id: header
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            height: 64
            DragHandler {
                target: null
                onActiveChanged: if (active) win.startSystemMove()
            }
            Logo {
                id: mark
                anchors.left: parent.left
                anchors.leftMargin: 20
                anchors.verticalCenter: parent.verticalCenter
                size: 34
            }
            Text {
                anchors.left: mark.right
                anchors.leftMargin: 12
                anchors.verticalCenter: parent.verticalCenter
                text: eshab.tr("settings.title")
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: 17
                font.weight: Font.DemiBold
            }
            WindowButton {
                anchors.right: parent.right
                anchors.rightMargin: 10
                anchors.top: parent.top
                anchors.topMargin: 10
                kind: "close"
                label: eshab.tr("settings.close")
                onClicked: win.close()
            }
        }

        Flickable {
            id: scroll
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: header.bottom
            anchors.bottom: parent.bottom
            anchors.leftMargin: 28
            anchors.rightMargin: 28
            anchors.bottomMargin: 18
            contentHeight: page.height + 12
            clip: true
            boundsBehavior: Flickable.StopAtBounds

            Column {
                id: page
                width: scroll.width
                spacing: 26

                // -- look -----------------------------------------------------------------
                Column {
                    width: parent.width
                    spacing: 12
                    Heading { text: eshab.tr("settings.section.look") }
                    Label { text: eshab.tr("about.material") }
                    Row {
                        anchors.left: parent.left
                        spacing: 10
                        Repeater {
                            model: ["honey", "clear", "ink"]
                            MaterialJar {
                                material: modelData
                                label: eshab.tr("material." + modelData)
                                selected: win.value("material") === modelData
                                onPicked: eshab.setMaterial(modelData)
                            }
                        }
                    }
                    Label { text: eshab.tr("settings.appearance.label") }
                    Segmented {
                        width: parent.width
                        options: win.choices("settings.appearance.", ["system", "light", "dark"])
                        value: win.value("appearanceTheme")
                        onPicked: (v) => win.put("appearanceTheme", v)
                    }
                    Label { text: eshab.tr("settings.language.label") }
                    Segmented {
                        width: parent.width
                        options: win.choices("settings.language.", ["ar", "en"])
                        value: win.value("language")
                        onPicked: (v) => win.put("language", v)
                    }
                    Rectangle {
                        visible: win.rev >= 0 && eshab.restartNeeded
                        width: parent.width
                        height: restartRow.height + 20
                        radius: 14
                        color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.14)
                        border.width: 1
                        border.color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.5)
                        Item {
                            id: restartRow
                            x: 14
                            y: 10
                            width: parent.width - 28
                            height: Math.max(restartText.implicitHeight, restartButton.height)
                            Text {
                                id: restartText
                                anchors.left: parent.left
                                anchors.right: restartButton.left
                                anchors.rightMargin: 12
                                anchors.verticalCenter: parent.verticalCenter
                                text: eshab.tr("settings.restart")
                                wrapMode: Text.WordWrap
                                color: Theme.text
                                font.family: Theme.fontFamily
                                font.pixelSize: 13
                            }
                            EButton {
                                id: restartButton
                                anchors.right: parent.right
                                anchors.verticalCenter: parent.verticalCenter
                                kind: "primary"
                                text: eshab.tr("settings.restart_now")
                                onClicked: eshab.restart()
                            }
                        }
                    }
                }

                // -- keys -------------------------------------------------------------------
                Column {
                    width: parent.width
                    spacing: 12
                    Heading { text: eshab.tr("settings.section.keys") }
                    Hint { text: eshab.tr("settings.wheels.intro") }
                    Repeater {
                        model: [["conversionWheelDragModifierMask", "settings.wheels.conversions"],
                                ["toolsWheelDragModifierMask", "settings.wheels.tools"],
                                ["actionsWheelDragModifierMask", "settings.wheels.actions"]]
                        Column {
                            width: page.width
                            spacing: 8
                            Label { text: eshab.tr(modelData[1]) }
                            Segmented {
                                width: parent.width
                                options: win.masks
                                value: win.value(modelData[0]) || ""
                                onPicked: (v) => win.put(modelData[0], v)
                            }
                        }
                    }
                    Text {
                        visible: win.clash
                        width: parent.width
                        text: eshab.tr("settings.wheels.same")
                        wrapMode: Text.WordWrap
                        color: "#E5484D"
                        font.family: Theme.fontFamily
                        font.pixelSize: 13
                    }
                }

                // -- the wheels' cards: order and hide -------------------------------------
                Column {
                    id: orderPart
                    width: parent.width
                    spacing: 10
                    property string mode: "conversion"
                    readonly property var cards: win.rev >= 0 ? eshab.wheelCards(mode) : []
                    Heading { text: eshab.tr("settings.order.title") }
                    Hint { text: eshab.tr("settings.order.hint") }
                    Segmented {
                        width: parent.width
                        options: [{ "value": "conversion", "label": eshab.tr("settings.wheels.conversions") },
                                  { "value": "tools", "label": eshab.tr("settings.wheels.tools") },
                                  { "value": "actions", "label": eshab.tr("settings.wheels.actions") }]
                        value: orderPart.mode
                        onPicked: (v) => orderPart.mode = v
                    }
                    Rectangle {
                        width: parent.width
                        height: Math.min(320, orderList.contentHeight + 12)
                        radius: 14
                        color: Theme.dark ? Qt.rgba(1, 1, 1, 0.04) : Qt.rgba(0, 0, 0, 0.03)
                        border.width: 1
                        border.color: Theme.glassRim
                        ListView {
                            id: orderList
                            anchors.fill: parent
                            anchors.margins: 6
                            clip: true
                            boundsBehavior: Flickable.StopAtBounds
                            model: orderPart.cards
                            delegate: Item {
                                id: cardRow
                                required property var modelData
                                required property int index
                                width: orderList.width
                                height: 40
                                Rectangle {
                                    anchors.fill: parent
                                    radius: 10
                                    color: rowHover.hovered ? (Theme.dark ? Qt.rgba(1, 1, 1, 0.06) : Qt.rgba(0, 0, 0, 0.04)) : "transparent"
                                }
                                HoverHandler { id: rowHover }
                                Row {
                                    anchors.left: parent.left
                                    anchors.leftMargin: 10
                                    anchors.verticalCenter: parent.verticalCenter
                                    spacing: 10
                                    opacity: cardRow.modelData.hidden ? 0.4 : 1
                                    Item {
                                        width: 22
                                        height: 22
                                        anchors.verticalCenter: parent.verticalCenter
                                        Image {
                                            anchors.fill: parent
                                            visible: cardRow.modelData.glyph !== ""
                                            sourceSize: Qt.size(44, 44)
                                            source: cardRow.modelData.glyph
                                                    ? "image://eshab/glyph/" + cardRow.modelData.glyph + "/" + (Theme.dark ? "F2F2F4" : "1C1C1E") : ""
                                        }
                                    }
                                    Text {
                                        anchors.verticalCenter: parent.verticalCenter
                                        text: cardRow.modelData.label
                                        color: Theme.text
                                        font.family: Theme.fontFamily
                                        font.pixelSize: 13
                                        font.strikeout: cardRow.modelData.hidden
                                    }
                                }
                                Row {
                                    anchors.right: parent.right
                                    anchors.rightMargin: 6
                                    anchors.verticalCenter: parent.verticalCenter
                                    spacing: 2
                                    Repeater {
                                        model: [["", -1, cardRow.index > 0], ["", 1, cardRow.index < orderPart.cards.length - 1],
                                                [cardRow.modelData.hidden ? "" : "", 0, true]]
                                        delegate: Rectangle {
                                            required property var modelData
                                            width: 30
                                            height: 30
                                            radius: 15
                                            visible: modelData[2]
                                            color: tap.containsMouse ? (Theme.dark ? Qt.rgba(1, 1, 1, 0.12) : Qt.rgba(0, 0, 0, 0.08)) : "transparent"
                                            Text {
                                                anchors.centerIn: parent
                                                text: modelData[0]
                                                font.family: Theme.iconFont
                                                font.pixelSize: 12
                                                color: modelData[1] === 0 && !cardRow.modelData.hidden ? Theme.accent : Theme.text
                                            }
                                            MouseArea {
                                                id: tap
                                                anchors.fill: parent
                                                hoverEnabled: true
                                                cursorShape: Qt.PointingHandCursor
                                                onClicked: modelData[1] === 0 ? eshab.toggleCard(orderPart.mode, cardRow.modelData.key)
                                                                              : eshab.moveCard(orderPart.mode, cardRow.modelData.key, modelData[1])
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                    Text {
                        text: eshab.tr("settings.order.reset")
                        color: Theme.accent
                        font.family: Theme.fontFamily
                        font.pixelSize: 13
                        font.underline: resetHit.containsMouse
                        MouseArea {
                            id: resetHit
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: eshab.resetCards(orderPart.mode)
                        }
                    }
                }

                // -- behaviour --------------------------------------------------------------
                Column {
                    width: parent.width
                    spacing: 6
                    Heading { text: eshab.tr("settings.section.behaviour") }
                    ESwitch {
                        width: parent.width
                        text: eshab.tr("settings.general.startup")
                        checked: win.rev >= 0 && eshab.startup
                        onToggled: (on) => eshab.setStartup(on)
                    }
                    ESwitch {
                        width: parent.width
                        text: eshab.tr("settings.shellmenu")
                        checked: win.rev >= 0 && eshab.shellMenu
                        onToggled: (on) => eshab.setShellMenu(on)
                    }
                    Text {
                        width: parent.width
                        text: eshab.tr("settings.shellmenu_hint")
                        wrapMode: Text.WordWrap
                        color: Theme.textSecondary
                        font.family: Theme.fontFamily
                        font.pixelSize: 12
                    }
                    ESwitch {
                        width: parent.width
                        text: eshab.tr("settings.general.fullscreen")
                        checked: !!win.value("suppressInFullscreen")
                        onToggled: (on) => win.put("suppressInFullscreen", on)
                    }
                    ESwitch {
                        width: parent.width
                        text: eshab.tr("settings.office")
                        checked: !!win.value("useOfficeForPdf")
                        onToggled: (on) => win.put("useOfficeForPdf", on)
                    }
                    Hint { text: eshab.tr("settings.office_hint") }
                }

                // -- documents to PDF ---------------------------------------------------------
                Column {
                    width: parent.width
                    spacing: 12
                    Heading { text: eshab.tr("settings.section.pdf") }
                    Label { text: eshab.tr("settings.formats.page_size") }
                    Segmented {
                        width: parent.width
                        options: win.choices("settings.formats.page_size.", ["a4", "letter"])
                        value: win.value("pdfPageSize")
                        onPicked: (v) => win.put("pdfPageSize", v)
                    }
                    Label { text: eshab.tr("settings.formats.margins") }
                    Segmented {
                        width: parent.width
                        options: win.choices("settings.formats.margins.", ["compact", "normal", "wide"])
                        value: win.value("pdfMarginPreset")
                        onPicked: (v) => win.put("pdfMarginPreset", v)
                    }
                    ESwitch {
                        width: parent.width
                        text: eshab.tr("settings.formats.page_numbers")
                        checked: !!win.value("pdfPageNumbers")
                        onToggled: (on) => win.put("pdfPageNumbers", on)
                    }
                }

                // -- about ----------------------------------------------------------------------
                Column {
                    width: parent.width
                    spacing: 10
                    Heading { text: eshab.tr("settings.section.about") }
                    Hint { text: eshab.version }
                    Row {
                        anchors.left: parent.left
                        spacing: 10
                        EButton {
                            text: eshab.tr("settings.guide")
                            onClicked: eshab.openGuide()
                        }
                        EButton {
                            text: eshab.tr("settings.folder")
                            onClicked: eshab.openSettingsFolder()
                        }
                    }
                }
            }
        }
    }

    // Titles fill the line and start where it starts (the right, in Arabic).
    component Heading: Text {
        width: parent ? parent.width : implicitWidth
        horizontalAlignment: Text.AlignLeft
        color: Theme.text
        font.family: Theme.fontFamily
        font.pixelSize: 16
        font.weight: Font.DemiBold
    }
    component Label: Text {
        width: parent ? parent.width : implicitWidth
        horizontalAlignment: Text.AlignLeft
        color: Theme.textSecondary
        font.family: Theme.fontFamily
        font.pixelSize: 13
        font.weight: Font.DemiBold
    }
    component Hint: Text {
        width: parent ? parent.width : 300
        horizontalAlignment: Text.AlignLeft
        wrapMode: Text.WordWrap
        color: Theme.textSecondary
        font.family: Theme.fontFamily
        font.pixelSize: 12
    }

    Shortcut { sequence: "Esc"; onActivated: win.close() }
}
