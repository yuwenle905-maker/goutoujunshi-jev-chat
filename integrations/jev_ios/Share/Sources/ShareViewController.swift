import UIKit
import UniformTypeIdentifiers

@MainActor
final class ShareViewController: UIViewController {
    private let preview = UITextView()
    private let status = UILabel()
    private let save = UIButton(type: .system)
    private var incoming: SharedChatImport?
    private var task: Task<Void, Never>?

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .systemBackground
        preview.isEditable = false; preview.font = .preferredFont(forTextStyle: .body)
        status.numberOfLines = 0; status.text = "正在本机读取共享内容…"
        save.setTitle("保存到待导入，稍后在主 App 核对", for: .normal); save.isEnabled = false
        save.addAction(UIAction { [weak self] _ in self?.saveImport() }, for: .touchUpInside)
        let cancel = UIButton(type: .system); cancel.setTitle("取消", for: .normal)
        cancel.addAction(UIAction { [weak self] _ in self?.task?.cancel(); self?.extensionContext?.completeRequest(returningItems: nil) }, for: .touchUpInside)
        let stack = UIStackView(arrangedSubviews: [status, preview, save, cancel]); stack.axis = .vertical; stack.spacing = 12
        view.addSubview(stack); stack.translatesAutoresizingMaskIntoConstraints = false
        NSLayoutConstraint.activate([stack.topAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor, constant: 16), stack.leadingAnchor.constraint(equalTo: view.leadingAnchor, constant: 16), stack.trailingAnchor.constraint(equalTo: view.trailingAnchor, constant: -16), stack.bottomAnchor.constraint(equalTo: view.safeAreaLayoutGuide.bottomAnchor, constant: -16)])
        task = Task { [weak self] in await self?.receive() }
    }
    private func receive() async {
        do {
            let items = extensionContext?.inputItems.compactMap { $0 as? NSExtensionItem } ?? []
            let providers = items.flatMap { $0.attachments ?? [] }
            guard providers.count <= 1 else { throw GoutouError.invalid("每次请共享一份聊天文件或一张截图，避免混淆顺序和对象") }
            let text: String, source: String
            if let provider = providers.first {
                if provider.hasItemConformingToTypeIdentifier(UTType.image.identifier) {
                    let data = try await load(provider, type: UTType.image.identifier)
                    text = try await LocalOCR.recognize(data); source = "系统共享截图 · 本地识别"
                } else {
                    let types = [UTType.zip, .json, .commaSeparatedText, .plainText]
                    if let type = types.first(where: { provider.hasItemConformingToTypeIdentifier($0.identifier) }) {
                        let data = try await load(provider, type: type.identifier)
                        var name = provider.suggestedName ?? "共享内容"
                        if (name as NSString).pathExtension.isEmpty { name += "." + (type.preferredFilenameExtension ?? "txt") }
                        text = try ChatImport.text(data, filename: name); source = name
                    } else if provider.hasItemConformingToTypeIdentifier(UTType.fileURL.identifier) {
                        let pair = try await file(provider)
                        text = try ChatImport.text(pair.0, filename: pair.1); source = pair.1
                    } else { throw GoutouError.invalid("来源 App 没有提供可读聊天正文；请共享 TXT/CSV/JSON/ZIP 或截图，微信内部卡片不能直接解析") }
                }
            } else if let raw = items.compactMap({ $0.attributedContentText?.string }).first, !raw.isEmpty {
                text = try ChatImport.text(Data(raw.utf8), filename: "共享文字.txt"); source = "系统共享文字"
            } else { throw GoutouError.invalid("没有可导入的文字或文件") }
            try Task.checkCancellation()
            incoming = SharedChatImport(text: text, source: source)
            preview.text = text; status.text = "只在本机接收并加密暂存，不上传。保存后请打开狗头军师 → 使用 → 接收共享内容，再选择对象并核对。"; save.isEnabled = true
        } catch { status.text = error.localizedDescription }
    }
    private func load(_ provider: NSItemProvider, type: String) async throws -> Data {
        try await withCheckedThrowingContinuation { continuation in
            provider.loadItem(forTypeIdentifier: type, options: nil) { item, error in
                do {
                    if let error = error { throw error }
                    let data: Data
                    if let value = item as? Data { data = value }
                    else if let value = item as? String { data = Data(value.utf8) }
                    else if let url = item as? URL, url.isFileURL {
                        guard let size = try url.resourceValues(forKeys: [.fileSizeKey]).fileSize, size <= 20_000_000 else { throw GoutouError.invalid("共享文件过大") }
                        data = try Data(contentsOf: url)
                    } else if let image = item as? UIImage, let value = image.jpegData(compressionQuality: 0.85) { data = value }
                    else { throw GoutouError.invalid("此共享内容格式无法读取") }
                    guard data.count <= 20_000_000 else { throw GoutouError.invalid("共享内容过大") }
                    continuation.resume(returning: data)
                } catch { continuation.resume(throwing: error) }
            }
        }
    }
    private func file(_ provider: NSItemProvider) async throws -> (Data, String) {
        try await withCheckedThrowingContinuation { continuation in
            provider.loadItem(forTypeIdentifier: UTType.fileURL.identifier, options: nil) { item, error in
                do {
                    if let error = error { throw error }
                    guard let url = item as? URL, url.isFileURL, let size = try url.resourceValues(forKeys: [.fileSizeKey]).fileSize, size <= 8_000_000 else { throw GoutouError.invalid("文件无法读取或超过 8 MB") }
                    continuation.resume(returning: (try Data(contentsOf: url), url.lastPathComponent))
                } catch { continuation.resume(throwing: error) }
            }
        }
    }
    private func saveImport() {
        do {
            guard let incoming = incoming else { return }
            let store = try GoutouStore(); try store.importInbox.save(incoming)
            extensionContext?.completeRequest(returningItems: nil)
        } catch { status.text = error.localizedDescription }
    }
}
