import Foundation

@main
struct RuleChecks {
    static var count = 0
    static func check(_ name: String, _ value: @autoclosure () throws -> Bool) throws {
        count += 1
        guard try value() else { throw GoutouError.invalid("FAIL: " + name) }
    }
    static func rejects(_ name: String, _ operation: () throws -> Void) throws {
        count += 1
        do { try operation() } catch { return }
        throw GoutouError.invalid("FAIL accepted: " + name)
    }
    static func main() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let store = SkillRuleStore(container: root)
        let bundled = try store.read(URL(fileURLWithPath: CommandLine.arguments[1]))
        try check("Full core and references bundled", bundled.documents.count >= 40)
        try check("Valid reference path", SkillRulePack.validPath("references/practical/中文.md"))
        for path in ["../SKILL.md", "references/../escape.md", "references//a.md", "references/%2e%2e/a.md", "references/a.swift", "https://example.org/x.md"] {
            try check("Reject unsafe path " + path, !SkillRulePack.validPath(path))
        }
        try store.install(bundled)
        try check("Installed archive roundtrips", try store.current().documents == bundled.documents)
        var tampered = bundled
        tampered.documents["SKILL.md"] = "## goutoujunshi changed without matching hash"
        try rejects("Hash mismatch") { try store.install(tampered) }
        try check("Failed update preserves current", try store.current().revision == bundled.revision)
        var second = bundled
        second.revision = String(repeating: "a", count: 40)
        try store.install(second)
        try check("Update activates new version", try store.current().revision == second.revision)
        try check("Previous version available", store.canRollback)
        try store.rollback()
        try check("Rollback returns previous version", try store.current().revision == bundled.revision)
        let context = bundled.context(goal: "暧昧升温", background: "", transcript: "对方：今天玩得开心")
        try check("Core reaches prompt", context.contains(bundled.documents["SKILL.md"]!))
        try check("Scene routing follows goal", context.contains("参考：references/practical/场景感"))
        try check("Not whole knowledge base each time", context.components(separatedBy: "参考：").count <= 4)
        try check("Mobile runtime contract explicit", context.contains("不强制首次问卷") && context.contains("模型不能自行保存"))
        let danger = bundled.context(goal: "自然接话", background: "遭遇跟踪威胁", transcript: "")
        try check("Safety guide prioritized", danger.contains("参考：references/knowledge/17-"))
        let system = GoutouGuidance.analysis(config: AppConfig(), strategy: .nudge, goal: "推进关系", rules: context)
        try check("Dynamic rules used in reply prompt", system.contains(context) && system.contains("只输出一个 JSON"))
        try Data("corrupt".utf8).write(to: root.appendingPathComponent("SkillRules-current.json"), options: .atomic)
        try rejects("Corrupt current rules fail visibly") { _ = try store.current() }
        print("Rule checks passed: \(count)")
    }
}
