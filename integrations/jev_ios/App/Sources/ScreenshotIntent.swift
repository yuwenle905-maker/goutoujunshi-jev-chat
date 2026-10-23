import AppIntents
import Combine
import Foundation
import UniformTypeIdentifiers

/// Shortcuts supplies an explicitly selected/captured image. This action never uploads it.
struct RecognizeChatScreenshotIntent: AppIntent {
    static var title: LocalizedStringResource = "识别聊天截图（按配置）"
    static var description = IntentDescription("接收截图并打开狗头军师，按识图配置处理。本地模式直接识别；DeepSeek 或 OpenRouter 先预览并确认上传。不会自动分析或发送消息。")
    static var openAppWhenRun: Bool = true

    @Parameter(title: "聊天截图", supportedTypeIdentifiers: ["public.image"], inputConnectionBehavior: .connectToPreviousIntentResult)
    var screenshot: IntentFile

    static var parameterSummary: some ParameterSummary {
        Summary("识别 \(\.$screenshot) 并打开核对页")
    }

    @MainActor
    func perform() async throws -> some IntentResult {
        try Task.checkCancellation()
        let jpeg = try LocalOCR.boundedJPEG(screenshot.data)
        try Task.checkCancellation()
        ScreenshotInbox.shared.submit(jpeg)
        return .result()
    }
}

/// Receives a system screenshot without opening the companion app. A fresh
/// request from the keyboard is required, so the result cannot target old chats.
struct SendChatScreenshotToKeyboardIntent: AppIntent {
    static var title: LocalizedStringResource = "截图交给键盘（按配置）"
    static var description = IntentDescription("接收系统截屏，按识图配置交给键盘。本地模式直接识别；DeepSeek 或 OpenRouter 在键盘预览后确认上传。不打开主 App，不会自动分析或发送。")
    static var openAppWhenRun: Bool = false

    @Parameter(title: "聊天截图", supportedTypeIdentifiers: ["public.image"], inputConnectionBehavior: .connectToPreviousIntentResult)
    var screenshot: IntentFile

    static var parameterSummary: some ParameterSummary {
        Summary("把 \(\.$screenshot) 交给键盘，按配置识别")
    }

    func perform() async throws -> some IntentResult {
        try Task.checkCancellation()
        let store = try GoutouStore()
        guard let request = store.captureMailbox.request(),
              request.relationship == store.relationship(), request.config == store.config() else {
            throw GoutouError.invalid("请先切换到狗头军师键盘，点“识图”→“收起键盘后截屏”或“小面板等待”，再运行这个快捷指令。等待有效期为 90 秒。")
        }
        do {
            let jpeg = try LocalOCR.boundedJPEG(screenshot.data, maxPixelSize: 2200,
                                                excludedBottomFraction: request.excludedBottomFraction)
            let result = try await CaptureOCR.prepare(jpeg, request: request)
            try Task.checkCancellation()
            guard request.relationship == store.relationship(), request.config == store.config() else {
                throw GoutouError.invalid("对象或配置已变化，请重新点“识图”")
            }
            try store.captureMailbox.publish(result)
        } catch {
            if !(error is CancellationError) {
                try? store.captureMailbox.publish(KeyboardCaptureResult(request: request, transcript: "",
                                                                         error: error.localizedDescription))
            }
            throw error
        }
        return .result()
    }
}

struct GoutouScreenshotShortcuts: AppShortcutsProvider {
    static var appShortcuts: [AppShortcut] {
        AppShortcut(intent: RecognizeChatScreenshotIntent(),
            phrases: ["用 \(.applicationName) 识别聊天截图"],
            shortTitle: "识别聊天截图", systemImageName: "viewfinder")
        AppShortcut(intent: SendChatScreenshotToKeyboardIntent(),
            phrases: ["用 \(.applicationName) 把截图交给键盘"],
            shortTitle: "截图交给键盘", systemImageName: "keyboard")
    }
}

/// Foreground intent and app use the same process; nothing is persisted to an App Group.
@MainActor
final class ScreenshotInbox: ObservableObject {
    static let shared = ScreenshotInbox()
    @Published private(set) var pending: Data?
    func submit(_ data: Data) { pending = data }
    func take() -> Data? {
        let image = pending
        pending = nil
        return image
    }
}
