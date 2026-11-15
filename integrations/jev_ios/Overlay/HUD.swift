import UIKit
import SwiftUI
import CryptoKit
import Darwin

@main @MainActor enum HUDEntry {
    static func main() {
        do {
            let data = FileHandle.standardInput.readDataToEndOfFile()
            let boot = try JSONDecoder().decode(AleOverlaySession.self, from: data)
            try boot.validate()
            HUDState.bootstrap = boot
            guard getuid() == 0, geteuid() == 0 else {
                HUDState.report("悬浮权限不足，请用TrollStore安装完整包"); exit(77)
            }
            let code = AleRunHUD()
            if code == 73 {
                HUDState.report("悬浮初始化失败（73）：\(AleEventFailure() ?? "未知阶段")；iOS \(UIDevice.current.systemVersion)")
            } else {
                HUDState.report("悬浮接口不可用（\(code)），主App仍可使用")
            }
            exit(code)
        } catch { exit(65) } // Never print the bootstrap or a decoding context.
    }
}

@MainActor final class HUDState: ObservableObject {
    static var bootstrap: AleOverlaySession!
    @Published var selectedID: String
    @Published var transcript = "" { didSet { if oldValue != transcript { invalidate(); confirmed = false } } }
    @Published var confirmed = false
    @Published var advice: Advice?
    @Published var reply = ""
    @Published var status = "选择对象，再读取聊天；核对后才会调用模型。"
    @Published var busy = false
    private var task: Task<Void, Never>?
    private var revision = 0
    private var original = ""
    let transport = HTTPTransport()
    let memory: ChatMemoryStore
    var onCapture: (() -> Void)?
    var onCollapse: (() -> Void)?
    var person: AleOverlaySession.Person { Self.bootstrap.people.first { $0.relationship.id == selectedID }! }
    init() {
        selectedID = Self.bootstrap.selectedID
        memory = ChatMemoryStore(container: URL(fileURLWithPath: Self.bootstrap.containerPath), key: SymmetricKey(data: Self.bootstrap.memoryKey),
            fileOwner: (Self.bootstrap.mobileUID, Self.bootstrap.mobileGID))
    }
    static func report(_ message: String) {
        guard let boot = bootstrap, let data = try? JSONSerialization.data(withJSONObject: ["message":message]) else { return }
        let url = URL(fileURLWithPath: boot.statusPath)
        try? data.write(to: url, options: .atomic)
        _ = chown(url.path, boot.mobileUID, boot.mobileGID); _ = chmod(url.path, S_IRUSR | S_IWUSR)
    }
    func invalidate() { revision += 1; task?.cancel(); task = nil; busy = false; advice = nil; reply = ""; original = "" }
    func switchPerson() { invalidate(); transcript = ""; confirmed = false; status = "已切换对象，旧聊天与候选已清除，请重新读取。" }
    func copyInput() {
        if let image = UIPasteboard.general.image, let data = image.jpegData(compressionQuality: 0.9) { recognize(data); return }
        guard let text = UIPasteboard.general.string, !text.trimmed.isEmpty else { status = "剪贴板没有文字或图片，请先在聊天App复制。"; return }
        transcript = text; status = "已读取文字；请标注我／对方并核对当前对象。"
    }
    func recognize(_ data: Data) {
        invalidate(); let marker = revision; busy = true; status = "本地识别截图…"
        task = Task { @MainActor in
            do {
                let text = try await LocalOCR.recognize(data, screenCapture: true)
                try Task.checkCancellation(); guard marker == revision else { return }
                task = nil; busy = false; transcript = text
                status = "识别完成；请核对我／对方和对象，再勾选确认。黑屏或受保护内容请改用复制／系统截图。"
            } catch { if marker == revision { busy = false; status = error.localizedDescription } }
        }
    }
    func generate() {
        guard !busy else { return }
        let context = person, text = Transcript(text: transcript, confirmed: confirmed)
        do { try text.validate(); try context.relationship.validate() } catch { status = error.localizedDescription; return }
        let marker = revision; busy = true; status = "正在分析并生成…"
        task = Task { @MainActor in
            do {
                let api = ModelAPI(transport: transport, config: Self.bootstrap.config, secrets: Self.bootstrap.secrets,
                    memoryContext: try memoryContext(context.relationship.id), ruleContext: context.rules)
                let result = try await GoutouPipeline(api: api).analyze(text, relationship: context.relationship)
                try Task.checkCancellation(); guard marker == revision else { return }
                advice = result; reply = result.candidates.first?.text ?? ""; original = reply
                busy = false; status = "已生成；可选候选、编辑后复制。没有发送任何消息。"
            } catch { if marker == revision { busy = false; status = error.localizedDescription } }
        }
    }
    func choose(_ candidate: Candidate) { reply = candidate.text; original = candidate.text }
    private func memoryContext(_ id: String) throws -> String {
        defer { mobileOwnership() }
        return try memory.context(id)
    }
    func copyReply() {
        guard !reply.trimmed.isEmpty else { status = "请先生成或填写回复。"; return }
        UIPasteboard.general.setItems([[UIPasteboard.typeAutomatic:reply]], options: [.localOnly:true])
        status = "已复制；回聊天App粘贴并检查接收人。"; onCollapse?()
    }
    private func mobileOwnership() {
        // Root helper shares only this app's encrypted archive folder. Return new
        // atomic files/locks to the app's original uid; never traverse elsewhere.
        let boot = Self.bootstrap!
        let folder = URL(fileURLWithPath: boot.containerPath).appendingPathComponent("PersonMemory", isDirectory: true)
        _ = chown(folder.path, boot.mobileUID, boot.mobileGID)
        for url in (try? FileManager.default.contentsOfDirectory(at: folder, includingPropertiesForKeys: [.isSymbolicLinkKey])) ?? [] {
            guard ["bin", "lock"].contains(url.pathExtension),
                  (try? url.resourceValues(forKeys: [.isSymbolicLinkKey]).isSymbolicLink) != true else { continue }
            _ = chown(url.path, boot.mobileUID, boot.mobileGID); _ = chmod(url.path, S_IRUSR | S_IWUSR)
        }
    }
    func remember() {
        do {
            defer { mobileOwnership() }
            guard confirmed else { throw GoutouError.invalid("请先核对对象和双方身份") }
            let id = selectedID
            guard try memory.load(id).enabled else { throw GoutouError.invalid("请先在主App为此对象开启长期记忆") }
            let plan = try memory.preview(id, transcript: transcript, source: "悬浮窗·用户核对")
            guard plan.overlapping == 0 else { throw GoutouError.invalid("存在重叠聊天，请回主App预览合并，未重复写入") }
            let added = try memory.merge(id, plan: plan, skipOverlap: false)
            status = "已加密保存\(added)条，只归档到当前对象。"
        } catch { status = error.localizedDescription }
    }
    func learnEdit() {
        do {
            defer { mobileOwnership() }
            try memory.saveStyle(selectedID, original: original, approved: reply)
            status = "已记住此对象的修改示例；不代表已发送。"
        } catch { status = error.localizedDescription }
    }
}

private struct HUDPanel: View {
    @ObservedObject var model: HUDState
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Text("阿乐辅助").font(.headline)
                    Spacer()
                    Button("收起") { model.onCollapse?() }
                    Button("关闭") { exit(0) }
                }
                Picker("当前对象", selection: $model.selectedID) {
                    ForEach(HUDState.bootstrap.people, id: \.relationship.id) { p in
                        Text((p.relationship.sourceApp ?? "通用") + " · " + p.relationship.label).tag(p.relationship.id)
                    }
                }.onChange(of: model.selectedID) { _ in model.switchPerson() }
                Text(model.person.relationship.stage + " → " + model.person.relationship.goal).font(.caption)
                HStack {
                    Button("截取当前屏幕") { model.onCapture?() }.disabled(model.busy)
                    Button("读取剪贴板") { model.copyInput() }.disabled(model.busy)
                }.buttonStyle(.bordered)
                Text("聊天原文（我：／对方：）").font(.caption)
                TextEditor(text: $model.transcript).frame(minHeight: 105, maxHeight: 150)
                    .accessibilityIdentifier("hudTranscript").scrollContentBackground(.hidden)
                    .padding(4).background(Color(uiColor:.secondarySystemBackground)).clipShape(RoundedRectangle(cornerRadius:10))
                Toggle("已核对对象、内容和双方身份", isOn:$model.confirmed).font(.footnote)
                HStack {
                    Button(model.busy ? "正在处理…" : "分析并生成") { model.generate() }.disabled(model.busy || !model.confirmed)
                    if model.busy { Button("取消") { model.invalidate(); model.status = "已取消" } }
                    Button("记住聊天") { model.remember() }.disabled(model.busy || !model.confirmed)
                }.buttonStyle(.bordered)
                Text(model.status).font(.caption).foregroundStyle(.secondary).accessibilityIdentifier("hudStatus")
                if let advice = model.advice {
                    Text(advice.recommendation).font(.footnote)
                    ForEach(advice.candidates) { candidate in
                        Button { model.choose(candidate) } label: { Text(candidate.text).frame(maxWidth:.infinity, alignment:.leading) }
                            .buttonStyle(.bordered)
                    }
                    Text("推进建议：" + advice.nextStep).font(.caption)
                    Text("收住条件：" + advice.stopCondition).font(.caption)
                }
                Text("编辑回复").font(.caption)
                TextEditor(text:$model.reply).frame(height:75).scrollContentBackground(.hidden)
                    .padding(4).background(Color(uiColor:.secondarySystemBackground)).clipShape(RoundedRectangle(cornerRadius:10))
                HStack {
                    Button("复制回复") { model.copyReply() }.buttonStyle(.borderedProminent)
                    Button("学习这次修改") { model.learnEdit() }.disabled(model.busy)
                }
                Text("截图仅在点击后进行本地OCR。分析会把核对内容和本对象记忆发给所选模型；不自动监听、不自动发送。")
                    .font(.caption2).foregroundStyle(.secondary)
            }.padding(16)
        }.tint(Color(uiColor:BrandTheme.accent)).background(.regularMaterial)
    }
}

private final class PassThroughView: UIView {
    override func hitTest(_ point: CGPoint, with event: UIEvent?) -> UIView? {
        let hit = super.hitTest(point, with:event); return hit === self ? nil : hit
    }
}
@objc(AleHUDWindow) final class HUDWindow: UIWindow {
    var editing = false
    override var canBecomeKey: Bool { editing }
    @objc static func _isSystemWindow() -> Bool { true }
    @objc func _ignoresHitTest() -> Bool { false }
    @objc func _isWindowServerHostingManaged() -> Bool { false }
    @objc func _isSecure() -> Bool { true }
    @objc func _shouldCreateContextAsSecure() -> Bool { true }
}
private final class HUDController: UIViewController {
    let model = HUDState()
    let bubble = UIButton(type: .system)
    var panel: UIHostingController<HUDPanel>!
    override func loadView() { view = PassThroughView(); view.backgroundColor = .clear }
    override func viewDidLoad() {
        super.viewDidLoad()
        bubble.setTitle("阿乐", for:.normal); bubble.setTitleColor(BrandTheme.onPrimary, for:.normal)
        bubble.titleLabel?.font = .boldSystemFont(ofSize:16); bubble.backgroundColor = BrandTheme.primary
        bubble.layer.cornerRadius = 26; bubble.frame = CGRect(x:16, y:180, width:52, height:52)
        bubble.accessibilityIdentifier = "aleGlobalBubble"; bubble.accessibilityLabel = "阿乐辅助悬浮球"
        bubble.addTarget(self, action:#selector(toggle), for:.touchUpInside)
        bubble.addGestureRecognizer(UIPanGestureRecognizer(target:self, action:#selector(drag(_:))))
        view.addSubview(bubble)
        panel = UIHostingController(rootView:HUDPanel(model:model)); addChild(panel); view.addSubview(panel.view); panel.didMove(toParent:self)
        panel.view.layer.cornerRadius = 22; panel.view.clipsToBounds = true; panel.view.isHidden = true
        model.onCollapse = { [weak self] in self?.collapse() }
        model.onCapture = { [weak self] in self?.capture() }
    }
    override func viewDidLayoutSubviews() {
        super.viewDidLayoutSubviews()
        let safe = view.bounds.inset(by:UIEdgeInsets(top:max(view.safeAreaInsets.top,48), left:10, bottom:max(view.safeAreaInsets.bottom,20), right:10))
        panel.view.frame = CGRect(x:safe.minX, y:safe.minY + 8, width:safe.width, height:min(safe.height - 16, 650))
    }
    @objc func toggle() { panel.view.isHidden.toggle(); bubble.isHidden = !panel.view.isHidden }
    func collapse() {
        panel.view.endEditing(true)
        if let window = view.window as? HUDWindow { window.editing = false; window.resignKey() }
        panel.view.isHidden = true; bubble.isHidden = false
    }
    @objc func drag(_ pan: UIPanGestureRecognizer) {
        let d = pan.translation(in:view); pan.setTranslation(.zero, in:view)
        bubble.center = CGPoint(x:min(max(30,bubble.center.x+d.x),view.bounds.width-30), y:min(max(65,bubble.center.y+d.y),view.bounds.height-50))
    }
    func capture() {
        view.isHidden = true
        DispatchQueue.main.asyncAfter(deadline:.now()+0.25) { [weak self] in
            guard let self = self else { return }
            let image = AleScreenImage(); self.view.isHidden = false
            guard let data = image?.jpegData(compressionQuality:0.9) else {
                self.model.status = "此系统截屏接口不可用；可复制聊天文字或系统截图后复制图片，再点读取剪贴板。"; return
            }
            self.model.recognize(data)
        }
    }
}

@objc(AleHUDDelegate) final class HUDDelegate: NSObject, UIApplicationDelegate {
    var window: UIWindow?
    private var controller: HUDController?
    func application(_ application: UIApplication, didFinishLaunchingWithOptions options:[UIApplication.LaunchOptionsKey:Any]? = nil) -> Bool {
        let controller = HUDController(); self.controller = controller
        let window = HUDWindow(frame:UIScreen.main.bounds); self.window = window
        window.rootViewController = controller; window.windowLevel = .init(rawValue:10000010); window.isHidden = false
        guard AleHostWindow(window) else { HUDState.report("全局窗口托管失败，未伪装成启动成功"); exit(72) }
        NotificationCenter.default.addObserver(forName: UITextView.textDidBeginEditingNotification, object:nil, queue:.main) { [weak window] _ in
            guard let window = window else { return }; window.editing = true; window.makeKey()
        }
        let center = CFNotificationCenterGetDarwinNotifyCenter()
        CFNotificationCenterAddObserver(center, Unmanaged.passUnretained(self).toOpaque(), { _, observer, _, _, _ in
            guard let observer = observer else { return }
            let delegate = Unmanaged<HUDDelegate>.fromOpaque(observer).takeUnretainedValue()
            DispatchQueue.main.async { delegate.hideForLock() }
        }, "com.apple.springboard.lockstate" as CFString, nil, .deliverImmediately)
        controller.bubble.isHidden = true
        AleChooseEventRoute(window) { passed, detail in
            Task { @MainActor in
                guard passed else {
                    HUDState.report("悬浮内部触摸自检失败（75）：\(detail ?? "未收到按钮动作")；iOS \(UIDevice.current.systemVersion)")
                    exit(75)
                }
                controller.bubble.isHidden = false
                HUDState.report("悬浮已托管，内部按钮触摸自检通过。请回聊天App确认悬浮球显示、拖动及复制。")
            }
        }
        return true
    }
    private func hideForLock() {
        // Query rather than toggle: duplicate notifications cannot expose data.
        typealias Port = @convention(c) () -> mach_port_t
        typealias Lock = @convention(c) (mach_port_t, UnsafeMutablePointer<ObjCBool>, UnsafeMutablePointer<ObjCBool>) -> Void
        guard let handle = dlopen("/System/Library/PrivateFrameworks/SpringBoardServices.framework/SpringBoardServices", RTLD_NOW),
              let port = dlsym(handle,"SBSSpringBoardServerPort"), let query = dlsym(handle,"SBGetScreenLockStatus") else {
            window?.isHidden = true; controller?.model.invalidate(); return
        }
        var locked: ObjCBool = true, passcode: ObjCBool = true
        unsafeBitCast(query,to:Lock.self)(unsafeBitCast(port,to:Port.self)(), &locked, &passcode)
        window?.isHidden = locked.boolValue
        if locked.boolValue { controller?.model.invalidate(); controller?.collapse() }
    }
}
