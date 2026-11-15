import Foundation
import CryptoKit
import Darwin

@main
struct MemoryChecks {
    static var count = 0
    static func check(_ name: String, _ condition: @autoclosure () throws -> Bool) throws {
        count += 1
        guard try condition() else { throw GoutouError.invalid("FAIL: " + name) }
    }
    static func rejects(_ name: String, _ operation: () throws -> Void) throws {
        count += 1
        do { try operation() } catch { return }
        throw GoutouError.invalid("FAIL: accepted " + name)
    }
    static func main() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let key = SymmetricKey(size: .bits256)
        let memory = ChatMemoryStore(container: directory, key: key)
        try memory.enable("alice", enabled: true)
        let original = "我：周六有空吗\n对方：下午有空"
        let plan = try memory.preview("alice", transcript: original, source: "test")
        try check("Initial merge keeps every message", try memory.merge("alice", plan: plan, skipOverlap: true) == 2)
        try check("Different people have separate contexts", try memory.context("bob").isEmpty)
        let next = try memory.preview("alice", transcript: "对方：下午有空\n我：那去看展吧", source: "test")
        try check("Only contiguous suffix-prefix overlap is proposed", next.overlapping == 1 && next.added == 1)
        try check("Explicit overlap skip appends once", try memory.merge("alice", plan: next, skipOverlap: true) == 1)
        try rejects("Stale plan cannot overwrite concurrent save") { _ = try memory.merge("alice", plan: next, skipOverlap: false) }
        let repeated = try memory.preview("alice", transcript: "我：那去看展吧", source: "test")
        try check("Repeated real message may be retained", try memory.merge("alice", plan: repeated, skipOverlap: false) == 1)
        let loaded = try memory.load("alice")
        try memory.saveSummary("alice", text: "对方说周六下午有空，邀约尚未确认。", expectedRevision: loaded.revision)
        try rejects("Stale summary cannot overwrite new memory") { try memory.saveSummary("alice", text: "旧草稿", expectedRevision: loaded.revision) }
        try check("Approved summary reaches context", try memory.context("alice").contains("邀约尚未确认"))
        try memory.deleteMessage("alice", messageID: loaded.messages[0].id)
        try check("Deleting a source invalidates current summary", try memory.load("alice").summary.isEmpty)
        let files = try FileManager.default.contentsOfDirectory(at: directory.appendingPathComponent("PersonMemory"), includingPropertiesForKeys: nil).filter { $0.pathExtension == "bin" }
        let encrypted = try Data(contentsOf: files[0])
        try check("Disk file does not contain chat plaintext", encrypted.range(of: Data("下午有空".utf8)) == nil)
        let reopened = ChatMemoryStore(container: directory, key: key)
        try check("Encrypted memory survives reopening", try reopened.load("alice").messages.count == 3)
        let wrong = ChatMemoryStore(container: directory, key: SymmetricKey(size: .bits256))
        try rejects("Wrong key must not reset memory") { _ = try wrong.load("alice") }
        try rejects("Unreviewed speakers cannot enter memory") { _ = try memory.preview("alice", transcript: "说话人待确认：你好", source: "test") }
        for index in 0..<10 { try memory.saveStyle("alice",original:"你好吗？\(index)",approved:"刚忙完\(index)") }
        try check("Edited replies retain latest eight examples", try memory.load("alice").styleExamples?.count == 8)
        try check("Style examples are recalled for their own person", try memory.context("alice").contains("本人修改：刚忙完9"))
        try check("Style examples do not cross people", try !memory.context("bob").contains("刚忙完9"))
        try check("Local comparison notices removed question", try memory.load("alice").styleExamples?.last?.changes.contains("去掉了问句") == true)
        try memory.clearStyles("alice")
        try check("Clear styles preserves chat history", try memory.load("alice").styleExamples?.isEmpty == true && !memory.load("alice").messages.isEmpty)
        try memory.enable("alice", enabled: false)
        try rejects("Disabled memory rejects new style samples") { try memory.saveStyle("alice",original:"old",approved:"new") }
        try check("Paused memory is not sent to models", try memory.context("alice").isEmpty)
        let ownedContainer = directory.appendingPathComponent("hud-owned")
        let owned = ChatMemoryStore(container: ownedContainer, key: key, fileOwner: (getuid(), getgid()))
        try owned.enable("hud-person", enabled: true)
        let ownedPlan = try owned.preview("hud-person", transcript: "对方：今天开心\n我：我也是", source: "synthetic")
        _ = try owned.merge("hud-person", plan: ownedPlan, skipOverlap: false)
        let appReader = ChatMemoryStore(container: ownedContainer, key: key)
        try check("HUD atomic archive is readable through normal app writer", try appReader.load("hud-person").messages.count == 2)
        let ownedFiles = try FileManager.default.contentsOfDirectory(at: ownedContainer.appendingPathComponent("PersonMemory"), includingPropertiesForKeys: nil)
        try check("HUD transaction leaves no temporary archive", !ownedFiles.contains { $0.lastPathComponent.hasPrefix(".write-") })
        for file in ownedFiles {
            let attributes = try FileManager.default.attributesOfItem(atPath: file.path)
            try check("Archive and lock preserve requested mobile owner", (attributes[.ownerAccountID] as? NSNumber)?.uint32Value == getuid())
            try check("Archive and lock remain owner-only", (attributes[.posixPermissions] as? NSNumber)?.intValue == 0o600)
        }
        let csv = "sender,message,timestamp\nme,你好,2026-10-01\nother,有空吗,2026-10-02"
        try check("CSV preserves explicit sender and timestamp", try ChatImport.text(Data(csv.utf8), filename: "chat.csv").contains("对方：[2026-10-02] 有空吗"))
        try check("Plain text does not guess sender", try ChatImport.text(Data("某人说的话".utf8), filename: "chat.txt") == "说话人待确认：某人说的话")
        let zipFixtures = [
            "UEsDBBQAAAAAAAqYV11dGY2cHwAAAB8AAAAIAAAAY2hhdC50eHTmiJHvvJrkvaDlpb0K5a+55pa577ya5pyJ56m65ZCXUEsBAhQAFAAAAAAACphXXV0ZjZwfAAAAHwAAAAgAAAAAAAAAAAAAAIABAAAAAGNoYXQudHh0UEsFBgAAAAABAAEANgAAAEUAAAAAAA==",
            "UEsDBBQAAAAIAAqYV11dGY2cJAAAAB8AAAAIAAAAY2hhdC50eHQBHwDg/+aIke+8muS9oOWlvQrlr7nmlrnvvJrmnInnqbrlkJdQSwECFAAUAAAACAAKmFddXRmNnCQAAAAfAAAACAAAAAAAAAAAAAAAgAEAAAAAY2hhdC50eHRQSwUGAAAAAAEAAQA2AAAASgAAAAAA"
        ]
        for fixture in zipFixtures {
            var zipped = Data(base64Encoded: fixture)!
            try check("Stored and deflate ZIP preserve Chinese transcript", try ChatImport.text(zipped, filename: "chat.zip") == "我：你好\n对方：有空吗")
            zipped[38] ^= 1
            try rejects("ZIP corruption does not enter memory") { _ = try ChatImport.text(zipped, filename: "chat.zip") }
        }
        try check("JSON imports explicit roles without guessing", try ChatImport.text(Data("[{\"sender\":\"other\",\"message\":\"下周见\"}]".utf8), filename: "chat.json") == "对方：下周见")
        try rejects("Broken ZIP is not partially imported") { _ = try ChatImport.text(Data("invalid".utf8), filename: "chat.zip") }
        try rejects("Unsupported file is not treated as text") { _ = try ChatImport.text(Data("x".utf8), filename: "chat.exe") }
        try check("Network allowlist rejects author and unrelated services", !HTTPTransport.permitted(URL(string: "https://example.com/collect")!))
        try check("Only exact official model endpoint is accepted", HTTPTransport.permitted(URL(string: "https://api.deepseek.com/chat/completions")!) && !HTTPTransport.permitted(URL(string: "https://api.deepseek.com/collect")!))
        print("PASS: \(count) encrypted memory, incremental merge, import and network privacy checks")
    }
}
