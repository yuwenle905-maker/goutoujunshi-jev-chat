import Foundation
import CryptoKit
import Darwin
#if os(iOS)
import Security
#endif

struct RememberedMessage: Codable, Equatable, Identifiable {
    var id = UUID()
    var speaker: String
    var text: String
    var importedAt = Date()
    var source: String
    var line: String { speaker + "：" + text }
}

struct SummaryVersion: Codable, Identifiable {
    var id = UUID()
    var text: String
    var createdAt = Date()
}

struct PersonMemory: Codable {
    var version = 1
    var enabled = false
    var revision = 0
    var messages = [RememberedMessage]()
    var summary = ""
    var summaries = [SummaryVersion]()
    var styleExamples: [ReplyStyleExample]? = nil
}

struct ReplyStyleExample: Codable, Identifiable {
    var id = UUID()
    var original: String
    var approved: String
    var changes: String
    var createdAt = Date()
}

struct MemoryMerge {
    var incoming: [RememberedMessage]
    var overlapping: Int
    var previousRevision: Int
    var added: Int { incoming.count - overlapping }
}

/// Shared App Group files are encrypted. No chat text or summary is stored in UserDefaults.
final class ChatMemoryStore {
    private let folder: URL
    private let key: SymmetricKey
    private let fileOwner: (uid_t, gid_t)?
    init(container: URL, key: SymmetricKey, fileOwner: (uid_t, gid_t)? = nil) {
        folder = container.appendingPathComponent("PersonMemory", isDirectory: true)
        self.key = key
        self.fileOwner = fileOwner
    }
    private func location(_ id: String) -> URL {
        let name = SHA256.hash(data: Data(id.utf8)).map { String(format: "%02x", $0) }.joined()
        return folder.appendingPathComponent(name + ".bin")
    }
    private func locked<T>(_ id: String, _ operation: (URL) throws -> T) throws -> T {
        guard !id.isEmpty, id.count <= 200 else { throw GoutouError.invalid("对象标识无效") }
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        let url = location(id)
        let fd = open(url.appendingPathExtension("lock").path, O_CREAT | O_RDWR, S_IRUSR | S_IWUSR)
        guard fd >= 0 else { throw GoutouError.invalid("无法锁定记忆文件") }
        defer { close(fd) }
        if let owner = fileOwner, fchown(fd, owner.0, owner.1) != 0 {
            throw GoutouError.invalid("无法设置共享记忆锁权限，旧数据未改动")
        }
        guard flock(fd, LOCK_EX) == 0 else { throw GoutouError.invalid("记忆正在写入，请重试") }
        defer { flock(fd, LOCK_UN) }
        return try operation(url)
    }
    private func read(_ url: URL) throws -> PersonMemory {
        guard FileManager.default.fileExists(atPath: url.path) else { return PersonMemory() }
        guard let size = try url.resourceValues(forKeys: [.fileSizeKey]).fileSize, size <= 8_000_000 else {
            throw GoutouError.invalid("记忆文件过大，未读取或覆盖，请先导出检查")
        }
        do {
            let sealed = try AES.GCM.SealedBox(combined: Data(contentsOf: url))
            let plaintext = try AES.GCM.open(sealed, using: key)
            let archive = try JSONDecoder().decode(PersonMemory.self, from: plaintext)
            guard archive.version == 1 else { throw GoutouError.invalid("记忆版本不支持") }
            return archive
        } catch { throw GoutouError.invalid("记忆读取或解密失败，原文件已保留，请勿卸载应用") }
    }
    private func write(_ archive: PersonMemory, _ url: URL) throws {
        guard archive.messages.count <= 10_000 else { throw GoutouError.invalid("此对象已达 10000 条记忆，请先导出整理，旧数据未删除") }
        let data = try JSONEncoder().encode(archive)
        guard data.count <= 7_000_000 else { throw GoutouError.invalid("此对象记忆过大，请先导出整理") }
        guard let sealed = try AES.GCM.seal(data, using: key).combined else { throw GoutouError.invalid("记忆加密失败") }
        if let owner = fileOwner {
            // Publish only a complete, fsynced ciphertext file already owned by
            // mobile. A crashing root HUD cannot leave an unreadable root-owned
            // replacement over the user's archive.
            let temp = folder.appendingPathComponent(".write-" + UUID().uuidString)
            let fd = open(temp.path, O_CREAT | O_EXCL | O_WRONLY | O_NOFOLLOW, S_IRUSR | S_IWUSR)
            guard fd >= 0 else { throw GoutouError.invalid("无法创建记忆暂存，旧数据未改动") }
            defer { close(fd); _ = unlink(temp.path) }
            guard fchown(fd, owner.0, owner.1) == 0 else { throw GoutouError.invalid("无法设置记忆归属，旧数据未改动") }
            #if os(iOS)
            try FileManager.default.setAttributes([.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication], ofItemAtPath: temp.path)
            #endif
            try sealed.withUnsafeBytes { raw in
                var offset = 0
                while offset < raw.count {
                    let n = Darwin.write(fd, raw.baseAddress!.advanced(by: offset), raw.count - offset)
                    if n < 0 && errno == EINTR { continue }
                    guard n > 0 else { throw GoutouError.invalid("记忆写入失败，旧数据未改动") }
                    offset += n
                }
            }
            guard fsync(fd) == 0, rename(temp.path, url.path) == 0 else { throw GoutouError.invalid("记忆提交失败，旧数据未改动") }
        } else {
            #if os(iOS)
            try sealed.write(to: url, options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
            #else
            try sealed.write(to: url, options: .atomic)
            #endif
        }
        var excluded = url
        var values = URLResourceValues(); values.isExcludedFromBackup = true
        try excluded.setResourceValues(values)
    }
    func load(_ id: String) throws -> PersonMemory { try locked(id) { try read($0) } }
    func enable(_ id: String, enabled: Bool) throws {
        try locked(id) { url in var archive = try read(url); archive.enabled = enabled; archive.revision += 1; try write(archive, url) }
    }
    static func messages(_ transcript: String, source: String) throws -> [RememberedMessage] {
        try Transcript(text: transcript, confirmed: true).validate()
        var result = [RememberedMessage]()
        for raw in transcript.components(separatedBy: .newlines) where !raw.trimmed.isEmpty {
            let line = raw.trimmed
            let prefix = ["我：", "我:", "对方：", "对方:"].first { line.hasPrefix($0) }
            if let prefix = prefix {
                let text = String(line.dropFirst(prefix.count)).trimmed
                guard !text.isEmpty else { throw GoutouError.invalid("有空白消息，请先修正") }
                result.append(RememberedMessage(speaker: prefix.hasPrefix("我") ? "我" : "对方", text: text, source: source))
            } else {
                guard !result.isEmpty else { throw GoutouError.invalid("保存记忆前，请将每条消息标为“我：”或“对方：”") }
                result[result.count - 1].text += "\n" + line
            }
        }
        guard !result.isEmpty else { throw GoutouError.invalid("没有可保存的消息") }
        return result
    }
    private static func overlap(_ old: [RememberedMessage], _ incoming: [RememberedMessage]) -> Int {
        guard !old.isEmpty, !incoming.isEmpty else { return 0 }
        for size in stride(from: min(old.count, incoming.count), through: 1, by: -1) {
            if old.suffix(size).map(\.line) == incoming.prefix(size).map(\.line) { return size }
        }
        return 0
    }
    func preview(_ id: String, transcript: String, source: String) throws -> MemoryMerge {
        let archive = try load(id)
        let incoming = try Self.messages(transcript, source: source)
        return MemoryMerge(incoming: incoming, overlapping: Self.overlap(archive.messages, incoming), previousRevision: archive.revision)
    }
    /// Only explicit preview confirmation may drop a matching prefix: repeated short replies can be real new events.
    func merge(_ id: String, plan: MemoryMerge, skipOverlap: Bool) throws -> Int {
        try locked(id) { url in
            var archive = try read(url)
            guard archive.enabled, archive.revision == plan.previousRevision else { throw GoutouError.invalid("对象记忆已变化，请重新预览合并") }
            let additions = skipOverlap ? Array(plan.incoming.dropFirst(plan.overlapping)) : plan.incoming
            archive.messages += additions; archive.revision += 1
            try write(archive, url)
            return additions.count
        }
    }
    func saveSummary(_ id: String, text: String, expectedRevision: Int) throws {
        guard text.count <= 6000 else { throw GoutouError.invalid("摘要最多 6000 字") }
        try locked(id) { url in
            var archive = try read(url)
            guard archive.revision == expectedRevision else { throw GoutouError.invalid("记忆已变化，请重新生成或核对摘要") }
            if !archive.summary.isEmpty { archive.summaries.append(SummaryVersion(text: archive.summary)) }
            archive.summary = text; archive.revision += 1; try write(archive, url)
        }
    }
    func deleteMessage(_ id: String, messageID: UUID) throws {
        try locked(id) { url in
            var archive = try read(url)
            archive.messages.removeAll { $0.id == messageID }
            // A removed source may invalidate the summary; retain it in local history but stop using it.
            if !archive.summary.isEmpty { archive.summaries.append(SummaryVersion(text: archive.summary)); archive.summary = "" }
            archive.revision += 1; try write(archive, url)
        }
    }
    func clear(_ id: String) throws { try locked(id) { try write(PersonMemory(), $0) } }
    func saveStyle(_ id: String, original: String, approved: String) throws {
        guard !original.trimmed.isEmpty, !approved.trimmed.isEmpty,
              original.count <= 1000, approved.count <= 1000, original != approved else {
            throw GoutouError.invalid("请修改为1–1000字的回复；原样候选不作为修改示例")
        }
        try locked(id) { url in
            var archive = try read(url)
            guard archive.enabled else { throw GoutouError.invalid("请先在当前对象的长期记忆中开启保存，再记录回复修改") }
            var changes = [approved.count < original.count ? "表达更简短" : "调整了表达细节"]
            if (original.contains("？") || original.contains("?")) && !(approved.contains("？") || approved.contains("?")) { changes.append("去掉了问句") }
            if original.contains("。") && !approved.contains("。") { changes.append("减少了句号") }
            var examples = archive.styleExamples ?? []
            examples.append(ReplyStyleExample(original: original, approved: approved, changes: changes.joined(separator: "；")))
            archive.styleExamples = Array(examples.suffix(8)); archive.revision += 1
            try write(archive,url)
        }
    }
    func clearStyles(_ id: String) throws {
        try locked(id) { url in
            var archive = try read(url); archive.styleExamples = []; archive.revision += 1; try write(archive,url)
        }
    }
    func context(_ id: String) throws -> String {
        let archive = try load(id)
        guard archive.enabled else { return "" }
        var lines = [String](), size = 0
        for message in archive.messages.reversed() {
            guard size + message.line.count <= 6000 else { break }
            lines.append(message.line); size += message.line.count + 1
        }
        let styles = (archive.styleExamples ?? []).map { "原候选：\($0.original)\n本人修改：\($0.approved)\n本地差异：\($0.changes)" }.joined(separator: "\n\n")
        return "历史资料仅供参考，以本轮原文及当前目标为准。导入时间不等于聊天发生时间，不把旧推测当事实。\n用户核对的长期摘要：\n" + archive.summary + "\n近期已核对聊天（较早到较晚）：\n" + lines.reversed().joined(separator: "\n") + (styles.isEmpty ? "" : "\n本对象本人审核修改（只参考表达，不能照搬旧事实）：\n" + styles)
    }
}

enum MemoryEncryptionKey {
    static func load() throws -> SymmetricKey {
        #if os(iOS)
        guard let group = Bundle.main.object(forInfoDictionaryKey: "GoutouKeychainGroup") as? String, !group.contains("$(") else {
            throw GoutouError.invalid("记忆加密钥匙串组未配置")
        }
        let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: "ai.goutoujunshi.memory-key.v1",
                                   kSecAttrAccount as String: "default", kSecAttrAccessGroup as String: group]
        func existing() throws -> Data? {
            var lookup = query; lookup[kSecReturnData as String] = true; lookup[kSecMatchLimit as String] = kSecMatchLimitOne
            var value: CFTypeRef?
            let status = SecItemCopyMatching(lookup as CFDictionary, &value)
            if status == errSecItemNotFound { return nil }
            guard status == errSecSuccess, let data = value as? Data, data.count == 32 else { throw GoutouError.invalid("无法读取记忆密钥，请检查共享钥匙串权限") }
            return data
        }
        if let data = try existing() { return SymmetricKey(data: data) }
        let key = SymmetricKey(size: .bits256)
        let data = key.withUnsafeBytes { Data($0) }
        var insert = query; insert[kSecValueData as String] = data
        insert[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        let status = SecItemAdd(insert as CFDictionary, nil)
        if status == errSecDuplicateItem, let data = try existing() { return SymmetricKey(data: data) }
        guard status == errSecSuccess else { throw GoutouError.invalid("无法保存记忆密钥（\(status)）") }
        return key
        #else
        throw GoutouError.invalid("测试需显式提供临时记忆密钥")
        #endif
    }
}
