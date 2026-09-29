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
  property bool reopenAfterCapture: false
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

  function beginCapture() {
    // Close our full-screen panel first. The system region picker is the
    // layer that freezes the desktop and can change the cursor on this GPU.
    if (tool.running) return
    root.mode = "capture"
    root.busy = true
    root.reopenAfterCapture = true
    root.close()
    captureDelay.spins = 0
    captureDelay.restart()
  }

  function run(args) {
    if (tool.running) return
    root.mode = args[0]
    root.busy = true
    root.status = ""
    root.toolOut = ""
    root.toolErr = ""
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

  // Status JSON is a few thousand characters. Anything past this is dropped
  // and the command is stopped, so the shell cannot hold an unbounded stream.
  readonly property int streamCap: 32000
  property string toolOut: ""
  property string toolErr: ""

  function appendStream(which, chunk) {
    var current = which === "out" ? root.toolOut : root.toolErr
    if (current.length >= root.streamCap) {
      if (tool.running) tool.running = false
      return
    }
    var piece = (current === "" ? "" : "\n") + String(chunk || "")
    if (current.length + piece.length > root.streamCap) {
      piece = piece.slice(0, root.streamCap - current.length)
      if (tool.running) tool.running = false
    }
    if (which === "out") root.toolOut += piece
    else root.toolErr += piece
  }

  Timer {
    id: captureDelay
    interval: 40
    repeat: true
    property int spins: 0
    onTriggered: {
      spins += 1
      if (!panel.open && !panel.visible) {
        stop()
        root.run(["capture", "--quiet"])
      } else if (spins > 40) {
        stop()
        root.run(["capture", "--quiet"])
      }
    }
  }

  Component.onCompleted: refresh()

  Process {
    id: tool
    stdout: SplitParser {
      onRead: function(line) { root.appendStream("out", line) }
    }
    stderr: SplitParser {
      onRead: function(line) { root.appendStream("err", line) }
    }
    onExited: function(code) {
      root.busy = false
      var err = String(root.toolErr || "").trim()
      if (root.mode === "status") {
        if (String(root.toolOut || "").trim() !== "") root.applyStatus(root.toolOut)
        if (err !== "") root.status = err
        else if (code !== 0 && root.status === "") root.status = "Machine check failed"
        return
      }
      if (err !== "") root.status = err
      var reopen = root.reopenAfterCapture
      root.reopenAfterCapture = false
      var failed = code !== 0 && root.status === ""
      Qt.callLater(function() {
        if (reopen) root.open()
        else root.run(["status"])
        if (failed && root.status === "") root.status = "That step did not finish"
      })
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
              textFormat: Text.PlainText
              text: "Devanagari"
              color: root.ink
              font.family: root.face
              font.pixelSize: Style.font.heading
            }

            Text {
              textFormat: Text.PlainText
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
                  textFormat: Text.PlainText
                  text: modelData.name || ""
                  color: root.ink
                  font.family: root.face
                  font.pixelSize: Style.font.body
                  width: parent.width
                  elide: Text.ElideRight
                }

                Text {
                  textFormat: Text.PlainText
                  width: parent.width
                  wrapMode: Text.WordWrap
                  text: modelData.detail || ""
                  color: root.ink
                  opacity: 0.55
                  font.family: root.face
                  font.pixelSize: Style.font.caption
                }

                Text {
                  textFormat: Text.PlainText
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

          Row {
            x: Style.space(4)
            spacing: Style.space(16)

            Text {
              textFormat: Text.PlainText
              text: root.busy && root.mode === "capture" ? "Selecting…" : "Capture"
              color: root.ink
              font.family: root.face
              font.pixelSize: Style.font.body
              font.underline: !root.busy

              MouseArea {
                anchors.fill: parent
                enabled: !root.busy
                cursorShape: Qt.PointingHandCursor
                onClicked: root.beginCapture()
              }
            }

            Text {
              textFormat: Text.PlainText
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
                onClicked: root.run(["last", "--copy", "--quiet"])
              }
            }
          }

          Column {
            width: parent.width - Style.space(8)
            x: Style.space(4)
            spacing: Style.space(6)
            visible: root.lastLine() !== ""

            Text {
              textFormat: Text.PlainText
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

          Text {
            textFormat: Text.PlainText
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
