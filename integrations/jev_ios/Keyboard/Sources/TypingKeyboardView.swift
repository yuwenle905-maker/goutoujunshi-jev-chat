import UIKit

/// Typing stays entirely on-device, including when keyboard Full Access is disabled.
@MainActor
final class TypingKeyboardView: UIView {
    private enum Layout { case letters, numbers, symbols }
    var onInsert: ((String) -> Void)?
    var onDelete: (() -> Void)?
    var onMove: ((Int) -> Void)?
    private var returnType: UIReturnKeyType = .default
    private weak var returnButton: UIButton?
    var onKeyboardButtonCreated: ((UIButton) -> Void)? { didSet { renderKeys() } }
    private var inputMode = UserDefaults.standard.string(forKey: "typingMode.v2") ?? "小鹤双拼"
    private var chinese: Bool { inputMode != "英文" }
    private var uppercase = false
    private var layout: Layout = .letters
    private var composition = PinyinComposition()
    private var engine: PinyinEngine?
    private var activeEngine: PinyinEngine? { engine }
    private var candidates = [PinyinCandidate]()
    private var lookupRevision = 0
    private let lookupQueue = DispatchQueue(label: "ai.goutoujunshi.pinyin", qos: .userInitiated)
    private let stack = UIStackView()
    private let preedit = KB.label("", size: 13)
    private let candidateScroll = UIScrollView()
    private let candidateRow = UIStackView()
    private let keys = UIStackView()
    private var deleteTimer: Timer?
    private var compact = false
    private var preeditHeight: NSLayoutConstraint!
    private var candidatesHeight: NSLayoutConstraint!
    private var keyHeight: CGFloat { compact ? 32 : 44 }

    var hasComposition: Bool { !composition.raw.isEmpty }

    func updateReturnKey(_ type: UIReturnKeyType) {
        returnType = type
        guard let button = returnButton else { return }
        let title: String
        switch type {
        case .send: title = "发送"
        case .search, .google, .yahoo: title = "搜索"
        case .go: title = "前往"
        case .next: title = "下一项"
        case .done: title = "完成"
        case .join: title = "加入"
        case .route: title = "路线"
        case .continue: title = "继续"
        default: title = chinese ? "换行" : "return"
        }
        button.configuration?.title = hasComposition ? "选字" : title
        let actionKey = type != .default && type != .emergencyCall
        button.configuration?.baseBackgroundColor = actionKey ? KB.primary : KB.highlight
        button.configuration?.baseForegroundColor = actionKey ? KB.onPrimary : KB.ink
        button.accessibilityLabel = hasComposition ? "确认当前拼音，不发送" : title
    }

    override init(frame: CGRect) {
        super.init(frame: frame)
        stack.axis = .vertical; stack.spacing = 5
        keys.axis = .vertical; keys.spacing = 12
        candidateRow.axis = .horizontal; candidateRow.spacing = 6
        candidateScroll.showsHorizontalScrollIndicator = false
        candidateScroll.delaysContentTouches = false
        addSubview(stack); stack.translatesAutoresizingMaskIntoConstraints = false
        candidateScroll.addSubview(candidateRow); candidateRow.translatesAutoresizingMaskIntoConstraints = false
        preedit.numberOfLines = 1
        preeditHeight = preedit.heightAnchor.constraint(equalToConstant: 16)
        candidatesHeight = candidateScroll.heightAnchor.constraint(equalToConstant: 44)
        preeditHeight.isActive = true; candidatesHeight.isActive = true
        [preedit, candidateScroll, keys].forEach { stack.addArrangedSubview($0) }
        NSLayoutConstraint.activate([
            stack.topAnchor.constraint(equalTo: topAnchor), stack.bottomAnchor.constraint(lessThanOrEqualTo: bottomAnchor),
            stack.leadingAnchor.constraint(equalTo: leadingAnchor), stack.trailingAnchor.constraint(equalTo: trailingAnchor),
            candidateRow.leadingAnchor.constraint(equalTo: candidateScroll.contentLayoutGuide.leadingAnchor),
            candidateRow.trailingAnchor.constraint(equalTo: candidateScroll.contentLayoutGuide.trailingAnchor),
            candidateRow.topAnchor.constraint(equalTo: candidateScroll.contentLayoutGuide.topAnchor),
            candidateRow.bottomAnchor.constraint(equalTo: candidateScroll.contentLayoutGuide.bottomAnchor),
            candidateRow.heightAnchor.constraint(equalTo: candidateScroll.frameLayoutGuide.heightAnchor)
        ])
        renderKeys(); renderCandidates()
        loadEngine()
    }
    private func loadEngine() {
        engine = nil; lookupRevision += 1
        guard chinese else { return }
        let mode = inputMode
        let resource = Bundle.main.url(forResource: "pinyin", withExtension: "tsv")
        lookupQueue.async { [weak self] in
            let text = resource.flatMap { try? String(contentsOf: $0, encoding: .utf8) }
            let engine = text.map { PinyinEngine(tsv: mode == "小鹤双拼" ? Flypy.dictionary($0) : $0) }
            DispatchQueue.main.async { [weak self] in
                guard let self = self, self.inputMode == mode else { return }
                self.engine = engine; self.refreshCandidates()
            }
        }
    }
    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }
    deinit { deleteTimer?.invalidate() }

    func clearComposition() {
        composition.clear(); lookupRevision += 1; candidates = []; renderCandidates()
        deleteTimer?.invalidate(); deleteTimer = nil
    }
    func setCompactLayout(_ value: Bool) {
        guard compact != value else { return }
        compact = value
        preeditHeight.constant = value ? 14 : 16
        preedit.font = .systemFont(ofSize: value ? 11 : 13)
        candidatesHeight.constant = value ? 32 : 44
        keys.spacing = value ? 5 : 12
        renderKeys(); renderCandidates()
    }
    override func didMoveToWindow() {
        super.didMoveToWindow()
        if window == nil { deleteTimer?.invalidate(); deleteTimer = nil }
    }
    private func key(_ title: String, identifier: String? = nil, utility: Bool = false, action: @escaping () -> Void) -> UIButton {
        let button = UIButton(type: .system)
        var config = UIButton.Configuration.filled()
        config.title = title; config.cornerStyle = .fixed
        config.background.cornerRadius = 6
        config.baseBackgroundColor = utility ? KB.highlight : KB.surface
        config.baseForegroundColor = KB.ink
        config.contentInsets = NSDirectionalEdgeInsets(top: 4, leading: 0, bottom: 4, trailing: 0)
        let fontSize: CGFloat = title.count > 1 ? 15 : (compact ? 25 : 29)
        config.titleTextAttributesTransformer = UIConfigurationTextAttributesTransformer { incoming in
            var result = incoming; result.font = .systemFont(ofSize: fontSize); return result
        }
        button.configuration = config
        button.layer.shadowColor = UIColor.black.cgColor
        button.layer.shadowOpacity = 0.12; button.layer.shadowRadius = 0
        button.layer.shadowOffset = CGSize(width: 0, height: 1)
        button.accessibilityIdentifier = identifier
        button.heightAnchor.constraint(equalToConstant: keyHeight).isActive = true
        button.addAction(UIAction { _ in action() }, for: .touchUpInside)
        return button
    }
    private func letterRow(_ text: String, insetRatio: CGFloat = 0) -> UIView {
        let row = keyRow(text.map { character in
            let raw = String(character)
            return key(uppercase && !chinese ? raw.uppercased() : raw, identifier: "typingKey_" + raw) { [weak self] in self?.type(raw) }
        })
        guard insetRatio > 0 else { return row }
        let wrapper = UIView(); wrapper.addSubview(row); row.translatesAutoresizingMaskIntoConstraints = false
        NSLayoutConstraint.activate([row.topAnchor.constraint(equalTo: wrapper.topAnchor), row.bottomAnchor.constraint(equalTo: wrapper.bottomAnchor),
                                     row.centerXAnchor.constraint(equalTo: wrapper.centerXAnchor),
                                     row.widthAnchor.constraint(equalTo: wrapper.widthAnchor, multiplier: 1 - insetRatio * 2)])
        return wrapper
    }
    private func keyRow(_ views: [UIView]) -> UIStackView {
        let row = UIStackView(arrangedSubviews: views)
        row.axis = .horizontal; row.spacing = compact ? 4 : 6; row.distribution = .fillEqually
        return row
    }
    private func deleteKey() -> UIButton {
        let button = key("⌫", identifier: "typingBackspace", utility: true) { [weak self] in self?.backspace() }
        button.accessibilityLabel = "删除"
        let hold = UILongPressGestureRecognizer(target: self, action: #selector(holdDelete(_:)))
        hold.minimumPressDuration = 0.4
        button.addGestureRecognizer(hold)
        return button
    }
    @objc private func holdDelete(_ gesture: UILongPressGestureRecognizer) {
        if gesture.state == .began {
            backspace()
            deleteTimer?.invalidate()
            deleteTimer = Timer.scheduledTimer(withTimeInterval: 0.09, repeats: true) { [weak self] _ in
                Task { @MainActor [weak self] in self?.backspace() }
            }
        } else if gesture.state == .ended || gesture.state == .cancelled || gesture.state == .failed {
            deleteTimer?.invalidate(); deleteTimer = nil
        }
    }
    private func renderKeys() {
        keys.arrangedSubviews.forEach { $0.removeFromSuperview() }
        switch layout {
        case .letters:
            keys.addArrangedSubview(letterRow("qwertyuiop"))
            keys.addArrangedSubview(letterRow("asdfghjkl", insetRatio: 0.05))
            let shift = key(chinese ? "分词" : "⇧", identifier: "typingShift", utility: true) { [weak self] in
                guard let self = self else { return }
                if self.chinese { self.composition.append("'"); self.refreshCandidates() }
                else { self.uppercase.toggle(); self.renderKeys() }
            }
            if !chinese && uppercase { shift.configuration?.baseBackgroundColor = KB.primary; shift.configuration?.baseForegroundColor = KB.onPrimary }
            shift.accessibilityLabel = chinese ? "拼音分隔符" : "切换大小写"
            let letters = keyRow("zxcvbnm".map { character in
                let raw = String(character)
                return key(uppercase && !chinese ? raw.uppercased() : raw, identifier: "typingKey_" + raw) { [weak self] in self?.type(raw) }
            })
            let third = UIStackView(arrangedSubviews: [shift, letters, deleteKey()])
            third.axis = .horizontal; third.spacing = 12; third.distribution = .fill
            shift.widthAnchor.constraint(equalTo: third.widthAnchor, multiplier: 0.11).isActive = true
            third.arrangedSubviews.last!.widthAnchor.constraint(equalTo: shift.widthAnchor).isActive = true
            keys.addArrangedSubview(third)
        case .numbers, .symbols:
            let rows = layout == .numbers ? ["1234567890", "-/:;()¥&@\""] : ["[]{}#%^*+=", "_\\|~<>€£•$"]
            rows.forEach { keys.addArrangedSubview(letterRow($0)) }
            let page = key(layout == .numbers ? "#+=" : "123", identifier: "typingSymbolPage", utility: true) { [weak self] in
                guard let self = self else { return }; self.layout = self.layout == .numbers ? .symbols : .numbers; self.renderKeys()
            }
            let punctuation = chinese ? ["，", "。", "？", "！", "、", "…", "'" ] : [",", ".", "?", "!", ":", ";", "'"]
            keys.addArrangedSubview(keyRow([page] + punctuation.map { value in key(value) { [weak self] in self?.insertPunctuation(value) } } + [deleteKey()]))
        }
        let alphabet = key(layout == .letters ? "123" : "ABC", identifier: "typingLayout", utility: true) { [weak self] in
            guard let self = self else { return }; self.commitComposition(); self.layout = self.layout == .letters ? .numbers : .letters; self.renderKeys()
        }
        let language = key(chinese ? "中/EN" : "EN/中", identifier: "typingLanguage", utility: true) {}
        language.menu = UIMenu(title: "输入方式", children: ["小鹤双拼", "中文全拼", "英文"].map { mode in
            UIAction(title: mode, state: inputMode == mode ? .on : .off) { [weak self] _ in
                guard let self = self else { return }
                self.commitComposition(); self.inputMode = mode; self.uppercase = false
                UserDefaults.standard.set(mode, forKey: "typingMode.v2")
                self.renderKeys(); self.loadEngine(); self.refreshCandidates()
            }
        })
        language.showsMenuAsPrimaryAction = true
        language.accessibilityLabel = "输入方式：\(inputMode)，点击选择英文、小鹤双拼或全拼"
        let globe = key("", identifier: "typingNextKeyboard", utility: true) {}
        globe.configuration?.image = UIImage(systemName: "globe")
        globe.accessibilityLabel = "切换到其他键盘"
        onKeyboardButtonCreated?(globe)
        let punctuation = key(chinese ? "，" : ",", identifier: "typingComma") { [weak self] in self?.insertPunctuation(self?.chinese == true ? "，" : ",") }
        let space = key(chinese ? "空格" : "space", identifier: "typingSpace") { [weak self] in
            guard let self = self else { return }
            if self.hasComposition { self.commitComposition() } else { self.onInsert?(" ") }
        }
        let enter = key("换行", identifier: "typingReturn", utility: true) { [weak self] in
            guard let self = self else { return }
            // A pending syllable is committed first; sending needs another deliberate tap.
            if self.hasComposition { self.commitComposition(); return }
            // Public keyboard API: the host decides whether Return submits or inserts a newline.
            self.onInsert?("\n")
        }
        returnButton = enter
        updateReturnKey(returnType)
        enter.menu = UIMenu(children: [UIAction(title: "插入换行") { [weak self] _ in
            self?.commitComposition(); self?.onInsert?("\n")
        }])
        let row = UIStackView(arrangedSubviews: [alphabet, globe, language, punctuation, space, enter])
        row.axis = .horizontal; row.spacing = 5; row.distribution = .fill
        alphabet.widthAnchor.constraint(equalTo: row.widthAnchor, multiplier: 0.105).isActive = true
        globe.widthAnchor.constraint(equalTo: row.widthAnchor, multiplier: 0.095).isActive = true
        language.widthAnchor.constraint(equalTo: row.widthAnchor, multiplier: 0.13).isActive = true
        punctuation.widthAnchor.constraint(equalTo: row.widthAnchor, multiplier: 0.075).isActive = true
        enter.widthAnchor.constraint(equalTo: row.widthAnchor, multiplier: 0.20).isActive = true
        space.accessibilityLabel = "空格，拼音输入时选第一个完整候选"
        keys.addArrangedSubview(row)
    }
    private func type(_ character: String) {
        if chinese && layout == .letters {
            composition.append(character); refreshCandidates()
        } else { onInsert?(uppercase && layout == .letters ? character.uppercased() : character) }
    }
    private func insertPunctuation(_ value: String) { commitComposition(); onInsert?(value) }
    private func backspace() {
        if composition.backspace() { refreshCandidates() } else { onDelete?() }
    }
    private func commitComposition() {
        guard hasComposition else { return }
        // Never insert an incomplete leading-word candidate while dropping the remaining syllables.
        let available = candidates.isEmpty ? (activeEngine?.candidates(for: composition.raw) ?? []) : candidates
        if let candidate = available.first, candidate.consumed == composition.raw.count,
           let text = composition.select(candidate) { onInsert?(text) }
        else { let text = composition.raw; composition.clear(); onInsert?(text) }
        refreshCandidates()
    }
    private func refreshCandidates() {
        lookupRevision += 1
        let revision = lookupRevision, raw = composition.raw
        candidates = []; renderCandidates()
        guard !raw.isEmpty, let engine = activeEngine else { return }
        lookupQueue.async { [weak self] in
            let result = engine.candidates(for: raw)
            DispatchQueue.main.async { [weak self] in
                guard let self = self, self.lookupRevision == revision, self.composition.raw == raw else { return }
                self.candidates = result; self.renderCandidates()
            }
        }
    }
    private func renderCandidates() {
        updateReturnKey(returnType)
        preedit.text = composition.raw.isEmpty ? "\(inputMode) · 本地输入 · 点中/EN切换" : composition.raw
        preedit.textColor = KB.secondary
        candidateRow.arrangedSubviews.forEach { $0.removeFromSuperview() }
        candidateScroll.contentOffset = .zero
        if composition.raw.isEmpty {
            for value in (chinese ? ["，", "。", "？"] : ["I", "The", "I'm"]) {
                candidateRow.addArrangedSubview(key(value) { [weak self] in self?.insertPunctuation(value) })
            }
        } else {
            for (index, candidate) in candidates.enumerated() {
                let button = key(candidate.text, identifier: "pinyinCandidate_\(index)") { [weak self] in
                    guard let self = self, let text = self.composition.select(candidate) else { return }
                    self.onInsert?(text); self.refreshCandidates()
                }
                button.accessibilityLabel = "拼音候选：" + candidate.text
                candidateRow.addArrangedSubview(button)
            }
            let raw = composition.raw
            candidateRow.addArrangedSubview(key(raw, identifier: "pinyinRaw") { [weak self] in
                guard let self = self, self.composition.raw == raw else { return }
                self.composition.clear(); self.onInsert?(raw); self.refreshCandidates()
            })
        }
        for case let button as UIButton in candidateRow.arrangedSubviews {
            let title = button.configuration?.title ?? ""
            let width = (title as NSString).size(withAttributes: [.font: UIFont.systemFont(ofSize: 20)]).width + 24
            button.widthAnchor.constraint(equalToConstant: max(44, width)).isActive = true
            if var config = button.configuration {
                config.baseBackgroundColor = .clear
                config.contentInsets = NSDirectionalEdgeInsets(top: 4, leading: 12, bottom: 4, trailing: 12)
                config.titleTextAttributesTransformer = UIConfigurationTextAttributesTransformer { incoming in
                    var result = incoming; result.font = .systemFont(ofSize: 20); return result
                }
                config.titleLineBreakMode = .byClipping
                button.configuration = config
            }
        }
    }
}
