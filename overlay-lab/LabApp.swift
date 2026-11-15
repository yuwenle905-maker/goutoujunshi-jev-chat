import UIKit

@main final class LabApp: UIResponder, UIApplicationDelegate {
    var window: UIWindow?
    func application(_ application: UIApplication, didFinishLaunchingWithOptions options: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {
        let w = UIWindow(frame: UIScreen.main.bounds)
        w.rootViewController = LabController(); w.makeKeyAndVisible(); window = w
        return true
    }
}

// This deliberately uses a normal app-owned UIWindow on the Simulator.
// It tests interaction/OCR/clipboard components, NOT TrollStore system hosting.
final class OverlayWindow: UIWindow {
    weak var bubble: UIView?
    weak var panel: UIView?
    override func hitTest(_ point: CGPoint, with event: UIEvent?) -> UIView? {
        for target in [panel,bubble].compactMap({ $0 }) where !target.isHidden {
            let local = target.convert(point,from:self)
            if target.point(inside:local,with:event) { return target.hitTest(local,with:event) }
        }
        return nil
    }
}

final class LabController: UIViewController {
    private var hud: OverlayWindow!
    private let bubble = UIButton(type:.system)
    private let panel = UIView()
    private let status = UILabel()
    private let recognized = UILabel()
    private let reply = UILabel()
    private let copyButton = UIButton(type:.system)
    private let messageInput = UITextView()
    private let probe = UILabel()
    private var dragStart = CGPoint.zero
    private let expected = "周六可以，下午见"
    override func viewDidLoad() {
        super.viewDidLoad(); view.backgroundColor = .systemBackground
        let title = UILabel(); title.text = "合成聊天 · 仅模拟器验证"; title.font = .preferredFont(forTextStyle:.headline)
        let chat = UILabel(); chat.text = "对方：周六一起喝咖啡吗？\n\n我：下午有空。"; chat.numberOfLines = 0
        chat.font = .systemFont(ofSize:24); chat.backgroundColor = UIColor.systemGreen.withAlphaComponent(0.14)
        chat.layer.cornerRadius = 16; chat.clipsToBounds = true; chat.accessibilityIdentifier = "fixtureChat"
        messageInput.font = .preferredFont(forTextStyle:.body); messageInput.accessibilityIdentifier = "chatInput"
        messageInput.backgroundColor = .secondarySystemBackground
        probe.numberOfLines = 0; probe.font = .preferredFont(forTextStyle:.caption1); probe.accessibilityIdentifier = "probe"
        let stack = UIStackView(arrangedSubviews:[title,chat,messageInput,probe]); stack.axis = .vertical; stack.spacing = 22
        stack.translatesAutoresizingMaskIntoConstraints = false; view.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo:view.safeAreaLayoutGuide.leadingAnchor,constant:24),
            stack.trailingAnchor.constraint(equalTo:view.safeAreaLayoutGuide.trailingAnchor,constant:-24),
            stack.topAnchor.constraint(equalTo:view.safeAreaLayoutGuide.topAnchor,constant:70),
            chat.heightAnchor.constraint(equalToConstant:180),messageInput.heightAnchor.constraint(equalToConstant:90)
        ])
    }
    override func viewDidAppear(_ animated: Bool) {
        super.viewDidAppear(animated)
        guard hud == nil else { return }
        hud = OverlayWindow(frame:view.window!.bounds); hud.windowLevel = .alert + 1
        let host = UIViewController(); host.view.backgroundColor = .clear; hud.rootViewController = host
        hud.bubble = bubble; hud.panel = panel
        bubble.frame = CGRect(x:view.bounds.width-74,y:100,width:56,height:56)
        bubble.backgroundColor = .systemTeal; bubble.layer.cornerRadius = 28; bubble.tintColor = .white
        bubble.setTitle("阿乐",for:.normal); bubble.accessibilityIdentifier = "aleBubble"
        bubble.addTarget(self,action:#selector(toggle),for:.touchUpInside)
        bubble.addGestureRecognizer(UIPanGestureRecognizer(target:self,action:#selector(drag(_:))))
        panel.frame = CGRect(x:20,y:220,width:view.bounds.width-40,height:360)
        panel.backgroundColor = .secondarySystemBackground; panel.layer.cornerRadius = 18; panel.isHidden = true
        panel.accessibilityIdentifier = "alePanel"
        status.text = "离线实验：未调用模型"; status.numberOfLines = 0; status.accessibilityIdentifier = "labStatus"
        recognized.numberOfLines = 0; recognized.accessibilityIdentifier = "recognized"
        reply.text = "测试建议："+expected; reply.numberOfLines = 0; reply.accessibilityIdentifier = "labReply"
        let capture = UIButton(type:.system); capture.setTitle("截图并识别合成聊天",for:.normal); capture.accessibilityIdentifier = "captureFixture"
        capture.addTarget(self,action:#selector(captureFixture),for:.touchUpInside)
        copyButton.setTitle("复制测试建议",for:.normal); copyButton.accessibilityIdentifier = "copyReply"
        copyButton.addTarget(self,action:#selector(copyReply),for:.touchUpInside); copyButton.isEnabled = false
        let contents = UIStackView(arrangedSubviews:[status,capture,recognized,reply,copyButton]); contents.axis = .vertical; contents.spacing = 16
        contents.translatesAutoresizingMaskIntoConstraints = false; panel.addSubview(contents)
        NSLayoutConstraint.activate([contents.topAnchor.constraint(equalTo:panel.topAnchor,constant:20),contents.leadingAnchor.constraint(equalTo:panel.leadingAnchor,constant:18),contents.trailingAnchor.constraint(equalTo:panel.trailingAnchor,constant:-18)])
        [capture,copyButton].forEach { $0.heightAnchor.constraint(greaterThanOrEqualToConstant:44).isActive = true }
        host.view.addSubview(panel); host.view.addSubview(bubble)
        hud.isHidden = false // Intentionally does NOT make the overlay key.
        if ProcessInfo.processInfo.arguments.contains("--expanded") { panel.isHidden = false }
    }
    @objc private func toggle() { panel.isHidden.toggle() }
    @objc private func drag(_ gesture: UIPanGestureRecognizer) {
        if gesture.state == .began { dragStart = bubble.center }
        let p = gesture.translation(in:hud)
        bubble.center = CGPoint(x:min(max(30,dragStart.x+p.x),hud.bounds.width-30),y:min(max(70,dragStart.y+p.y),hud.bounds.height-55))
    }
    @objc private func captureFixture() {
        guard let window = view.window else { return }
        let wasHidden = hud.isHidden; hud.isHidden = true
        let image = UIGraphicsImageRenderer(bounds:window.bounds).image { _ in window.drawHierarchy(in:window.bounds,afterScreenUpdates:true) }
        hud.isHidden = wasHidden
        guard let data = image.pngData() else { status.text = "截图失败"; return }
        // Also proves that the ordinary overlay did not become the app's key window.
        probe.text = "mainKey=\(window.isKeyWindow); screenshot=\(image.size.width)x\(image.size.height)"
        try? data.write(to:FileManager.default.urls(for:.documentDirectory,in:.userDomainMask)[0].appendingPathComponent("synthetic-capture.png"),options:.atomic)
        status.text = "正在运行阿乐辅助的真实本地OCR"
        Task { @MainActor in
            do {
                let text = try await LocalOCR.recognize(data)
                recognized.text = text
                status.text = text.contains("咖啡") ? "识别完成" : "识别结果需检查"
                copyButton.isEnabled = text.contains("咖啡")
            } catch { status.text = "识别失败："+error.localizedDescription }
        }
    }
    @objc private func copyReply() {
        UIPasteboard.general.setItems([["public.utf8-plain-text":expected]],options:[.localOnly:true])
        status.text = "已复制测试建议；未发送"
    }
}
