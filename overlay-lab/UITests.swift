import XCTest

final class AleOverlayUITests: XCTestCase {
    private var app: XCUIApplication!
    override func setUpWithError() throws {
        continueAfterFailure = false
        app = XCUIApplication(bundleIdentifier:"ai.ale.overlaylab"); app.launch()
        XCTAssertTrue(app.buttons["aleBubble"].waitForExistence(timeout:12))
    }
    override func tearDownWithError() throws { app.terminate() }
    func test01BubbleTapAndDrag() {
        let bubble = app.buttons["aleBubble"], before = bubble.frame
        bubble.press(forDuration:0.2,thenDragTo:app.coordinate(withNormalizedOffset:CGVector(dx:0.2,dy:0.18)))
        XCTAssertGreaterThan(abs(bubble.frame.midX-before.midX),60)
        bubble.tap(); XCTAssertTrue(app.buttons["captureFixture"].waitForExistence(timeout:3))
        bubble.tap(); XCTAssertFalse(app.buttons["captureFixture"].exists)
        shot("01-drag-and-collapse")
    }
    func test02PassThroughAndSystemKeyboard() {
        let input = app.textViews["chatInput"]; input.tap(); input.typeText("system-keyboard-ok")
        XCTAssertTrue((input.value as? String ?? "").contains("system-keyboard-ok"))
        XCTAssertTrue(app.buttons["aleBubble"].exists)
        shot("02-underlying-input")
    }
    func test03ScreenshotOCRAndCrossAppCopy() {
        app.buttons["aleBubble"].tap(); app.buttons["captureFixture"].tap()
        let ready = app.staticTexts["识别完成"]
        XCTAssertTrue(ready.waitForExistence(timeout:30))
        XCTAssertTrue(app.staticTexts["recognized"].label.contains("咖啡"))
        XCTAssertTrue(app.staticTexts["probe"].label.contains("mainKey=true"))
        app.buttons["copyReply"].tap(); XCTAssertTrue(app.staticTexts["已复制测试建议；未发送"].exists)
        shot("03-captured-and-copied")
        let receiver = XCUIApplication(bundleIdentifier:"ai.ale.pastereceiver"); receiver.launch()
        let paste = receiver.descendants(matching:.any).matching(identifier:"receiverPaste").firstMatch
        XCTAssertTrue(paste.waitForExistence(timeout:10)); paste.tap()
        let input = receiver.textViews["receiverInput"]
        expectation(for:NSPredicate(format:"value CONTAINS %@","周六可以，下午见"),evaluatedWith:input)
        waitForExpectations(timeout:10)
        // Boundary proof: an ordinary UIWindow does not follow into another app.
        XCTAssertFalse(receiver.buttons["aleBubble"].exists)
        shot("04-real-cross-app-paste")
        receiver.terminate()
    }
    private func shot(_ name:String) {
        let attachment = XCTAttachment(screenshot:XCUIScreen.main.screenshot()); attachment.name = name; attachment.lifetime = .keepAlways; add(attachment)
    }
}
