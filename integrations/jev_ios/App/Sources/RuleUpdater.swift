import Foundation
import SwiftUI

private final class RuleRedirectGuard: NSObject, URLSessionTaskDelegate {
    func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse,
                    newRequest request: URLRequest, completionHandler: @escaping (URLRequest?) -> Void) { completionHandler(nil) }
}

/// GET only, fixed public repository, no model credentials or user content.
private struct RuleDownloader {
    struct Commit: Decodable { let sha: String }
    struct Tree: Decodable {
        struct Entry: Decodable { let path: String; let type: String; let sha: String; let size: Int? }
        let tree: [Entry]; let truncated: Bool
    }
    let session: URLSession
    static let repository = "https://api.github.com/repos/shengjidaguai-china/goutoujunshi"
    func get(_ url: URL, limit: Int) async throws -> Data {
        guard url.scheme == "https", url.user == nil, url.password == nil,
              ["api.github.com", "raw.githubusercontent.com"].contains(url.host ?? "") else {
            throw GoutouError.invalid("规则下载地址无效")
        }
        var request = URLRequest(url: url)
        request.setValue("goutoujunshi-ios-rules", forHTTPHeaderField: "User-Agent")
        request.setValue("application/vnd.github+json", forHTTPHeaderField: "Accept")
        let (stream, response) = try await session.bytes(for: request)
        guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
            throw GoutouError.invalid("GitHub 规则下载失败（HTTP \((response as? HTTPURLResponse)?.statusCode ?? 0)），请稍后重试")
        }
        guard response.expectedContentLength <= Int64(limit) else { throw GoutouError.invalid("规则下载内容过大") }
        var data = Data()
        for try await byte in stream {
            if data.count >= limit { throw GoutouError.invalid("规则下载超过大小限制") }
            data.append(byte)
        }
        try Task.checkCancellation()
        return data
    }
    func download(current: String) async throws -> SkillRulePack? {
        let commit = try JSONDecoder().decode(Commit.self, from: await get(URL(string: Self.repository + "/commits/main")!, limit: 500_000))
        guard commit.sha.count == 40, commit.sha.allSatisfy({ $0.isHexDigit }) else { throw GoutouError.invalid("上游版本无效") }
        if commit.sha == current { return nil }
        let tree = try JSONDecoder().decode(Tree.self, from: await get(URL(string: Self.repository + "/git/trees/\(commit.sha)?recursive=1")!, limit: 2_000_000))
        guard !tree.truncated else { throw GoutouError.invalid("GitHub 文件列表不完整，保留旧规则") }
        let files = tree.tree.filter { $0.type == "blob" && SkillRulePack.validPath($0.path) }
        guard (2...128).contains(files.count), Set(files.map(\.path)).count == files.count,
              files.allSatisfy({ ($0.size ?? Int.max) <= 200_000 }),
              files.reduce(0, { $0 + ($1.size ?? 0) }) <= 4_000_000 else { throw GoutouError.invalid("上游规则文件数量或大小超限") }
        var documents = [String: String](), hashes = [String: String]()
        // Four concurrent requests bound memory and avoid creating one connection per file.
        for start in stride(from: 0, to: files.count, by: 4) {
            let batch = Array(files[start..<min(start + 4, files.count)])
            let rows = try await withThrowingTaskGroup(of: (String, String, String).self) { group in
                for entry in batch {
                    group.addTask {
                        var url = URL(string: "https://raw.githubusercontent.com/shengjidaguai-china/goutoujunshi/\(commit.sha)")!
                        for component in entry.path.split(separator: "/") { url.appendPathComponent(String(component)) }
                        let data = try await get(url, limit: 200_000)
                        guard SkillRulePack.blobHash(data) == entry.sha, let text = String(data: data, encoding: .utf8) else {
                            throw GoutouError.invalid("上游规则完整性校验失败：\(entry.path)")
                        }
                        return (entry.path, text, entry.sha)
                    }
                }
                var rows = [(String, String, String)]()
                for try await row in group { rows.append(row) }
                return rows
            }
            for (path, text, hash) in rows { documents[path] = text; hashes[path] = hash }
        }
        let pack = SkillRulePack(schema: 1, revision: commit.sha, documents: documents, hashes: hashes)
        try pack.validate(); return pack
    }
}

@MainActor
final class RuleUpdateModel: ObservableObject {
    static let shared = RuleUpdateModel()
    @Published var version = ""
    @Published var fileCount = 0
    @Published var busy = false
    @Published var message = ""
    @Published var canRollback = false
    @Published var lastChecked = UserDefaults.standard.object(forKey: "rules.lastChecked") as? Date
    @Published var automatic = UserDefaults.standard.object(forKey: "rules.auto") as? Bool ?? true {
        didSet { UserDefaults.standard.set(automatic, forKey: "rules.auto") }
    }
    private var lastAttempt: Date?
    private var task: Task<Void, Never>?
    private func store() throws -> SkillRuleStore { try GoutouStore().skillRules }
    func reload() {
        do {
            let storage = try store(), pack = try storage.current()
            version = pack.revision; fileCount = pack.documents.count; canRollback = storage.canRollback
        } catch { message = "规则读取失败：\(error.localizedDescription)。可恢复内置规则。" }
    }
    func checkIfDue() {
        reload()
        guard automatic, !busy,
              Date().timeIntervalSince(lastChecked ?? .distantPast) >= 86400,
              Date().timeIntervalSince(lastAttempt ?? .distantPast) >= 3600 else { return }
        update()
    }
    func update() {
        guard !busy else { return }
        busy = true; lastAttempt = Date(); message = "正在下载并校验军师规则…"
        task = Task {
            let config = URLSessionConfiguration.ephemeral
            config.urlCache = nil; config.httpCookieStorage = nil
            config.timeoutIntervalForRequest = 30; config.timeoutIntervalForResource = 180
            let session = URLSession(configuration: config, delegate: RuleRedirectGuard(), delegateQueue: nil)
            defer { session.invalidateAndCancel(); busy = false; task = nil }
            do {
                let storage = try store()
                let current = (try? storage.current().revision) ?? ""
                let pack = try await RuleDownloader(session: session).download(current: current)
                try Task.checkCancellation()
                if let pack = pack { try storage.install(pack) }
                lastChecked = Date(); UserDefaults.standard.set(lastChecked, forKey: "rules.lastChecked")
                reload()
                message = pack == nil ? "已是最新规则" : "规则更新成功，下次分析开始使用新规则。"
            } catch is CancellationError { message = "已取消更新，原有规则保留。" }
            catch { message = "更新未完成，原有规则保留：\(error.localizedDescription)" }
        }
    }
    func cancel() { task?.cancel() }
    func reset() {
        guard !busy else { return }
        do { try store().reset(); reload(); message = "已恢复安装包内置规则。" }
        catch { message = error.localizedDescription }
    }
    func rollback() {
        guard !busy else { return }
        do { try store().rollback(); reload(); message = "已回退上一个规则版本。" }
        catch { message = error.localizedDescription }
    }
}

struct RuleSettingsSection: View {
    @ObservedObject private var rules = RuleUpdateModel.shared
    var body: some View {
        Section("狗头军师 Skill 规则") {
            Link("规则来源：原作者 goutoujunshi", destination: URL(string: "https://github.com/shengjidaguai-china/goutoujunshi/blob/main/SKILL.md")!)
            Text("规则版本：\(rules.version.prefix(12)) · \(rules.fileCount) 份文件").font(.caption)
            if let date = rules.lastChecked { Text("上次成功检查：\(date.formatted(date: .abbreviated, time: .shortened))").font(.caption) }
            Button { rules.update() } label: {
                HStack { if rules.busy { ProgressView() }; Text(rules.busy ? "正在更新…" : "一键同步更新规则") }
            }.disabled(rules.busy)
            if rules.busy { Button("取消更新") { rules.cancel() } }
            Toggle("每天自动检查规则", isOn: $rules.automatic)
            Text("开启后，主 App 回到前台时每天检查一次；iOS 不保证关闭 App 后每天后台运行。只下载规则，不上传聊天或密钥。完整主规则＋最多三份相关参考用于分析，更新无需重装 IPA。").font(.caption).foregroundStyle(.secondary)
            if !rules.message.isEmpty { Text(rules.message).font(.caption) }
            if rules.canRollback { Button("回退上一个规则版本") { rules.rollback() }.disabled(rules.busy) }
            Button("恢复安装包内置规则") { rules.reset() }.disabled(rules.busy)
        }.onAppear { rules.reload() }
    }
}
