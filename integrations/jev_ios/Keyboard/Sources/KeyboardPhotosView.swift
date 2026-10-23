import UIKit
import Photos

/// Inline photo grid: does not present a system modal from a keyboard extension.
@MainActor
final class KeyboardPhotosView: UIView {
    var onImage: ((Data) -> Void)?
    var onMessage: ((String) -> Void)?
    private let stack = UIStackView()
    private let manager = PHCachingImageManager()
    private var generation = UUID()
    private var showingAll = false
    private var selectedRequest: PHImageRequestID?

    override init(frame: CGRect) {
        super.init(frame: frame)
        stack.axis = .vertical; stack.spacing = 8
        addSubview(stack); stack.translatesAutoresizingMaskIntoConstraints = false
        NSLayoutConstraint.activate([stack.topAnchor.constraint(equalTo: topAnchor), stack.leadingAnchor.constraint(equalTo: leadingAnchor),
            stack.trailingAnchor.constraint(equalTo: trailingAnchor), stack.bottomAnchor.constraint(equalTo: bottomAnchor)])
    }
    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }
    func load() {
        generation = UUID()
        stack.arrangedSubviews.forEach { $0.removeFromSuperview() }
        switch PHPhotoLibrary.authorizationStatus(for: .readWrite) {
        case .authorized, .limited: populate()
        case .notDetermined:
            stack.addArrangedSubview(KB.label("允许访问照片后，可直接选择已保存的截图。只读取你选择的图片，不会自动上传。", size: 14))
            stack.addArrangedSubview(KB.button("允许访问照片") { [weak self] in
                PHPhotoLibrary.requestAuthorization(for: .readWrite) { _ in
                    Task { @MainActor [weak self] in self?.load() }
                }
            })
        default:
            stack.addArrangedSubview(KB.label("未获照片权限。请在系统设置的隐私与安全性→照片中允许狗头军师访问；也可在主App选择截图，或在照片里复制截图后回键盘读取。", size: 14))
        }
    }
    private func populate() {
        let options = PHFetchOptions()
        options.sortDescriptors = [NSSortDescriptor(key: "creationDate", ascending: false)]
        options.fetchLimit = 60
        if !showingAll { options.predicate = NSPredicate(format: "(mediaSubtype & %d) != 0", PHAssetMediaSubtype.photoScreenshot.rawValue) }
        let assets = PHAsset.fetchAssets(with: .image, options: options)
        stack.addArrangedSubview(KB.button(showingAll ? "正在显示最近照片 · 改看截图" : "正在显示最近截图 · 改看全部照片") { [weak self] in
            guard let self = self else { return }; self.showingAll.toggle(); self.load()
        })
        stack.addArrangedSubview(KB.label("选择图片后先预览，再按配置识别；有限照片权限只显示已授权项目。", size: 12))
        if assets.count == 0 { stack.addArrangedSubview(KB.label("没有可访问的截图。可切换全部照片，或在主App用系统相册选图。", size: 14)); return }
        let current = generation
        for start in stride(from: 0, to: assets.count, by: 4) {
            var buttons = [UIView]()
            for index in start..<min(start + 4, assets.count) {
                let asset = assets.object(at: index), button = UIButton(type: .custom)
                button.clipsToBounds = true; button.layer.cornerRadius = 6
                button.backgroundColor = KB.highlight
                button.imageView?.contentMode = .scaleAspectFill
                button.heightAnchor.constraint(equalToConstant: 88).isActive = true
                button.accessibilityLabel = "聊天截图 \(index + 1)"
                manager.requestImage(for: asset, targetSize: CGSize(width: 170, height: 170), contentMode: .aspectFill, options: nil) { [weak self, weak button] image, _ in
                    Task { @MainActor in guard self?.generation == current else { return }; button?.setImage(image, for: .normal) }
                }
                button.addAction(UIAction { [weak self] _ in self?.select(asset) }, for: .touchUpInside)
                buttons.append(button)
            }
            while buttons.count < 4 { buttons.append(UIView()) }
            stack.addArrangedSubview(KB.row(buttons))
        }
    }
    private func select(_ asset: PHAsset) {
        if let selectedRequest = selectedRequest { manager.cancelImageRequest(selectedRequest) }
        onMessage?("正在读取所选截图…")
        let options = PHImageRequestOptions()
        options.deliveryMode = .highQualityFormat; options.resizeMode = .exact
        options.isNetworkAccessAllowed = true // Only the user-selected iCloud photo, if needed.
        let current = generation
        selectedRequest = manager.requestImage(for: asset, targetSize: CGSize(width: 2200, height: 2200), contentMode: .aspectFit, options: options) { [weak self] image, info in
            if info?[PHImageResultIsDegradedKey] as? Bool == true { return }
            Task { @MainActor in
                guard let self = self, self.generation == current else { return }
                guard let data = image?.jpegData(compressionQuality: 0.9) else {
                    self.onMessage?("无法读取图片，请检查照片权限或iCloud下载状态，也可到主App选图。"); return
                }
                self.onImage?(data)
            }
        }
    }
    func cancel() {
        generation = UUID()
        if let selectedRequest = selectedRequest { manager.cancelImageRequest(selectedRequest) }
        selectedRequest = nil; manager.stopCachingImagesForAllAssets()
    }
}
