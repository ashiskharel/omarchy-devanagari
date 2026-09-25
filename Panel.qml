import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

Panel {
  id: root
  moduleName: "ashis.devanagari"
  ipcTarget: "ashis.devanagari"
  manageIpc: false

  property var anchorItem: null
  property bool openedFromHotkey: false
  property var hostWidget: null
  readonly property var barIdentity: hostWidget || root

  property var report: ({})
  property string status: ""
  property bool busy: false
  property string mode: ""
  readonly property var engines: report && report.engines ? report.engines : []
  readonly property var lastReading: report && report.last ? report.last : ({})
  readonly property string supportUrl: report && report.supportUrl ? report.supportUrl : ""
  readonly property color ink: bar ? bar.foreground : Color.foreground
  readonly property string face: bar ? bar.fontFamily : Style.font.family

  function toolPath() {
    var url = String(Qt.resolvedUrl("bin/devanagari"))
    if (url.indexOf("file://") === 0) url = url.slice(7)
    return decodeURIComponent(url)
  }

  function open() {
    openedFromHotkey = false
    setCenterHoverRevealSuppressed(false)
    root.controller.show()
    refresh()
  }

  function openFromHotkey() {
    openedFromHotkey = true
    root.controller.show()
    refresh()
    Qt.callLater(function() {
      if (root.opened) setCenterHoverRevealSuppressed(true)
    })
  }

  function close() {
    setCenterHoverRevealSuppressed(false)
    root.controller.hide()
  }

  function toggle() {
    if (root.opened) root.close()
    else root.openFromHotkey()
  }

  function switchPanel(direction) {
    if (root.bar && typeof root.bar.switchPanelFrom === "function")
      return root.bar.switchPanelFrom(root.barIdentity, direction)
    return false
  }

  function setCenterHoverRevealSuppressed(value) {
    if (root.bar && typeof root.bar.setCenterHoverRevealSuppressed === "function")
      root.bar.setCenterHoverRevealSuppressed(value)
    else if (root.bar && "centerHoverRevealSuppressed" in root.bar)
      root.bar.centerHoverRevealSuppressed = value
  }

  function refresh() {
    root.run(["status"])
  }

  function run(args) {
    if (tool.running) return
    root.mode = args[0]
    root.busy = true
    root.status = ""
    tool.command = [root.toolPath()].concat(args)
    tool.running = true
  }

  function applyStatus(raw) {
    try {
      root.report = JSON.parse(raw)
    } catch (e) {
      root.status = "The machine check returned something unreadable"
      return
    }
    root.status = ""
  }

  function openSupport() {
    if (!root.supportUrl) return
    Qt.openUrlExternally(root.supportUrl)
  }

  function lastLine() {
    var reading = root.lastReading
    if (!reading) return ""
    if (reading.error) return String(reading.error)
    if (reading.text) return String(reading.text)
    return ""
  }

  Component.onCompleted: refresh()

  Process {
    id: tool
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        if (root.mode === "status") root.applyStatus(text || "")
      }
    }
    stderr: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        var err = String(text || "").trim()
        if (err !== "") root.status = err
      }
    }
    onExited: function(code) {
      root.busy = false
      if (root.mode !== "status") {
        if (code !== 0 && root.status === "") root.status = "That step did not finish"
        root.run(["status"])
        return
      }
      if (code !== 0 && root.status === "") root.status = "Machine check failed"
    }
  }

  IpcHandler {
    target: root.ipcTarget
    function open(): void { root.openFromHotkey() }
    function close(): void { root.close() }
    function show(): void { root.openFromHotkey() }
    function hide(): void { root.close() }
    function toggle(): void { root.toggle() }
  }

  KeyboardPanel {
    id: panel
    anchorItem: root.anchorItem
    owner: root.barIdentity
    bar: root.bar
    open: root.opened
    centerOnBar: true
    focusTarget: keyCatcher
    contentWidth: panel.fittedContentWidth(Style.space(380))
    contentHeight: panel.fittedContentHeight(column.implicitHeight)

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      onCloseRequested: root.close()
      onTabRequested: function(direction) { root.switchPanel(direction) }

      Flickable {
        anchors.fill: parent
        contentWidth: width
        contentHeight: column.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        interactive: contentHeight > height

        Column {
          id: column
          width: parent.width
          spacing: Style.space(12)
          topPadding: Style.space(4)

          Column {
            width: parent.width - Style.space(8)
            x: Style.space(4)
            spacing: 2

            Text {
              text: "Devanagari"
              color: root.ink
              font.family: root.face
              font.pixelSize: Style.font.heading
            }

            Text {
              width: parent.width
              wrapMode: Text.WordWrap
              text: root.report && root.report.line ? root.report.line : (root.busy ? "Checking this machine…" : "No machine check yet")
              color: root.ink
              opacity: 0.75
              font.family: root.face
              font.pixelSize: Style.font.bodySmall
            }
          }

          Column {
            width: parent.width - Style.space(8)
            x: Style.space(4)
            spacing: Style.space(8)

            Repeater {
              model: root.engines

              delegate: Column {
                required property var modelData
                width: parent.width
                spacing: 2

                Text {
                  text: modelData.name || ""
                  color: root.ink
                  font.family: root.face
                  font.pixelSize: Style.font.body
                  width: parent.width
                  elide: Text.ElideRight
                }

                Text {
                  width: parent.width
                  wrapMode: Text.WordWrap
                  text: modelData.detail || ""
                  color: root.ink
                  opacity: 0.55
                  font.family: root.face
                  font.pixelSize: Style.font.caption
                }

                Text {
                  visible: modelData.action === "fetch" || modelData.action === "download"
                  text: modelData.action === "fetch" ? "Fetch Nepali data" : "Download weights"
                  color: root.ink
                  font.family: root.face
                  font.pixelSize: Style.font.bodySmall
                  font.underline: true

                  MouseArea {
                    anchors.fill: parent
                    enabled: !root.busy && parent.visible
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                      if (modelData.action === "fetch") root.run(["fetch"])
                      else root.run(["fetch", "--model", modelData.id])
                    }
                  }
                }
              }
            }
          }

          Column {
            width: parent.width - Style.space(8)
            x: Style.space(4)
            spacing: Style.space(6)
            visible: (root.lastReading.text || "") !== "" || (root.lastReading.error || "") !== ""

            Text {
              text: root.lastLine()
              width: parent.width
              wrapMode: Text.WordWrap
              color: root.ink
              font.family: root.face
              font.pixelSize: Style.font.body
              maximumLineCount: 8
              elide: Text.ElideRight
            }
          }

          Row {
            x: Style.space(4)
            spacing: Style.space(16)

            Text {
              text: root.busy && root.mode === "capture" ? "Selecting…" : "Capture"
              color: root.ink
              font.family: root.face
              font.pixelSize: Style.font.body
              font.underline: !root.busy

              MouseArea {
                anchors.fill: parent
                enabled: !root.busy
                cursorShape: Qt.PointingHandCursor
                onClicked: root.run(["capture", "--json"])
              }
            }

            Text {
              text: "Copy"
              color: root.ink
              opacity: (root.lastReading.text || "") !== "" ? 1 : 0.35
              font.family: root.face
              font.pixelSize: Style.font.body
              font.underline: !root.busy && (root.lastReading.text || "") !== ""

              MouseArea {
                anchors.fill: parent
                enabled: !root.busy && (root.lastReading.text || "") !== ""
                cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                onClicked: root.run(["last", "--copy"])
              }
            }
          }

          Text {
            x: Style.space(4)
            width: parent.width - Style.space(8)
            wrapMode: Text.WordWrap
            text: root.status !== "" ? root.status : (root.supportUrl ? "Free to use. Pay what you are comfortable with." : "Free to use. Pay what you are comfortable with, including nothing.")
            color: root.ink
            opacity: 0.5
            font.family: root.face
            font.pixelSize: Style.font.caption
            font.underline: root.status === "" && root.supportUrl !== ""

            MouseArea {
              anchors.fill: parent
              enabled: root.status === "" && root.supportUrl !== ""
              cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
              onClicked: root.openSupport()
            }
          }
        }
      }
    }
  }
}
