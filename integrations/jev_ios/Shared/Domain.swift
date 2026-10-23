import Foundation
import CoreFoundation

enum GoutouError: LocalizedError {
    case invalid(String)
    case http(Int)
    case network
    case cancelled

    var errorDescription: String? {
        switch self {
        case .invalid(let text): return text
        case .http(let status):
            let hint = [401: "请检查密钥", 402: "请检查余额", 403: "请检查账号访问权限",
                        429: "请求过多，请稍后再试"][status] ?? "请检查模型、接口地址与服务状态"
            return "接口 HTTP \(status)：\(hint)"
        case .network: return "连接失败或超时，请检查网络与接口地址"
        case .cancelled: return "已取消"
        }
    }
}

enum Strategy: String, Codable, CaseIterable {
    case acknowledge = "承接", ease = "降压", tease = "调侃", nudge = "轻推"
    case meet = "约见", clarify = "澄清", stop = "收线"

    var guide: String {
        switch self {
        case .acknowledge: return "接住对方的分享与情绪，不急于解决或升级关系。"
        case .ease: return "忙、累、犹豫或追问过多时减少压力；一次忙碌不等于拒绝。"
        case .tease: return "只有双方接梗时轻松调侃，不嘲笑脆弱或忽视不适。"
        case .nudge: return "互惠但停滞时推进一小步，不索要承诺。"
        case .meet: return "有互惠与可信时间窗口时，提出具体、可拒绝的见面。"
        case .clarify: return "只澄清影响决策的一个关键未知，不审问、不读心。"
        case .stop: return "明确拒绝、要求停止联系或持续单边投入时停止推进。"
        }
    }
}

enum JudgeProvider: String, Codable, CaseIterable { case deepseek = "DeepSeek", jev = "TypeSafe Jev" }
enum ReplyProvider: String, Codable, CaseIterable { case deepseek = "DeepSeek", openrouter = "OpenRouter" }
enum OCRProvider: String, Codable, CaseIterable {
    case local = "Apple Vision · 本地", deepseek = "DeepSeek · 图片识别", openrouter = "OpenRouter · 图片识别"
}

struct AppConfig: Codable, Equatable {
    static let deepseekModels = ["deepseek-flash", "deepseek-v4-pro"]
    var judge: JudgeProvider = .deepseek
    var reply: ReplyProvider = .deepseek
    var ocr: OCRProvider = .local
    var deepseekModel = "deepseek-flash"
    var openrouterModel = "openrouter/free"
    var visionModel = ""
    var jevModel = "jev-latest"
    var tone = "稳健"
    var length = "简短"
    var count = 3
    var maxCharacters: Int { ["简短": 40, "适中": 70, "详细": 100][length] ?? 40 }

    func validate() throws {
        guard ["稳健", "会撩", "直接"].contains(tone), ["简短", "适中", "详细"].contains(length),
              (1...3).contains(count), !deepseekModel.trimmed.isEmpty,
              !openrouterModel.trimmed.isEmpty, !jevModel.trimmed.isEmpty,
              [deepseekModel, openrouterModel, visionModel, jevModel].allSatisfy({ $0.count <= 160 }) else {
            throw GoutouError.invalid("请核对模型 ID、口吻、长度和候选数量")
        }
        if ocr == .openrouter && visionModel.trimmed.isEmpty {
            throw GoutouError.invalid("OpenRouter 识图需要单独填写支持图片输入的模型 ID")
        }
    }
}

struct Relationship: Codable, Equatable, Identifiable {
    static let stages = ["未填写", "初识", "了解中", "暧昧", "约会中", "伴侣", "关系结束"]
    static let goals = ["自然接话", "重新破冰", "拉近距离", "轻松调情", "暧昧升温", "推进关系",
                        "主动邀约", "确认心意", "澄清关系", "修复冲突", "减少投入", "结束联系"]
    static let goalGuidance: [String: String] = [
        "自然接话": "先回应对方正在说的具体内容，自然延续话题，不强行升级关系。",
        "重新破冰": "在没有明确拒绝联系的前提下，用真实近况或共同话题重新开启一次轻量联系，不连发追问。",
        "拉近距离": "通过真实分享、共同兴趣和适度关心增加了解与熟悉感，不突然使用亲昵称呼或索取情绪回应。",
        "轻松调情": "根据双方接梗和互惠的依据，给一句轻松、有分寸的玩笑或欣赏；不尬撩、不冒犯，也不把礼貌当好感。",
        "暧昧升温": "在已有双向好感或暧昧互动时，增加一点个人化欣赏和亲近表达，观察对方是否接住；不凭空假定亲密。",
        "推进关系": "结合当前阶段与双方投入，主动提出一个具体、可拒绝的下一步，例如增加交流或见面；不要直接跳到承诺或逼对方表态。",
        "主动邀约": "结合共同兴趣与可行时间提出明确、低压力、可拒绝的邀约；时间未知先确认，不编造安排。",
        "确认心意": "真诚表达自己的好感，并询问对方是否愿意继续了解，给出不确定或拒绝的空间，不要求即时答复。",
        "澄清关系": "澄清双方对当前关系、期待或边界的一个关键分歧，不审问、不替对方定义关系。",
        "修复冲突": "先承接具体感受、说明责任和事实，再提出可执行的修复，不用调情掩盖冲突。",
        "减少投入": "按实际互惠调整联系和付出，把主动权交还一部分，不通过失联、嫉妒或冷暴力试探。",
        "结束联系": "清楚、简短地结束私人推进，尊重边界，不威胁、不反复发送告别。",
    ]
    static func guidance(for goal: String) -> String {
        goalGuidance[goal] ?? "先回应具体内容，未知保持未知。"
    }
    var id = UUID().uuidString
    var label = "当前对象"
    var stage = "未填写"
    var goal = "自然接话"
    var background = ""
    var notes = ""

    func validate() throws {
        guard !label.trimmed.isEmpty, label.count <= 40, Self.stages.contains(stage),
              Self.goals.contains(goal), background.count <= 200, notes.count <= 200 else {
            throw GoutouError.invalid("请核对对象、阶段和目标；背景与备注各最多 200 字")
        }
    }
}

struct Transcript: Equatable {
    var text: String
    var confirmed: Bool

    struct PendingLine: Identifiable {
        var index: Int
        var text: String
        var id: Int { index }
    }
    static func pendingLines(in text: String) -> [PendingLine] {
        text.components(separatedBy: .newlines).enumerated().compactMap { index, line in
            guard line.contains("说话人待确认") || line.contains("[OCR待核对]") else { return nil }
            return PendingLine(index: index, text: line)
        }
    }
    static func resolveLine(in text: String, at index: Int, speaker: String?) -> String {
        var lines = text.components(separatedBy: .newlines)
        guard lines.indices.contains(index), pendingLines(in: text).contains(where: { $0.index == index }) else { return text }
        if let speaker = speaker {
            guard ["我", "对方"].contains(speaker) else { return text }
            var content = lines[index].trimmed
            for prefix in ["说话人待确认：", "说话人待确认:"] where content.hasPrefix(prefix) {
                content = String(content.dropFirst(prefix.count))
            }
            content = content.replacingOccurrences(of: "[OCR待核对]", with: "").trimmed
            lines[index] = speaker + "：" + content
        } else {
            lines.remove(at: index)
        }
        return lines.joined(separator: "\n")
    }

    func validate() throws {
        guard confirmed else { throw GoutouError.invalid("请先核对原文和双方身份，再确认分析") }
        guard !text.trimmed.isEmpty, text.count <= 12_000 else {
            throw GoutouError.invalid("请保留与当前问题有关的 1–12000 字对话")
        }
        let pending = Self.pendingLines(in: text)
        guard pending.isEmpty else {
            throw GoutouError.invalid("还有 \(pending.count) 行待核对。请在“待确认的消息”中选择“我说的／对方说的”；时间、昵称等非聊天内容可手动移除，然后重新勾选核对。")
        }
    }
    var myLines: [String] {
        text.components(separatedBy: .newlines).filter { $0.hasPrefix("我：") || $0.hasPrefix("我:") }
    }
}

struct Candidate: Codable, Equatable, Identifiable {
    var text: String
    var reason: String
    var tradeoff: String
    var weight: Int?
    var id: String { text }
}

struct Evidence: Codable, Equatable {
    var facts: [String]
    var unknowns: [String]
    var boundary: String
}

struct Decision: Codable, Equatable {
    var strategy: Strategy
    var confidence: Double?
    var probabilities: [String: Double]
    var model: String
    var method: String
    var evidence: Evidence

    var summary: String {
        if method == "deepseek_logprobs" {
            return "DeepSeek · \(strategy.rawValue) · 策略选择权重 \(Self.percent(confidence))\n三次标签轮换的首 token 相对权重；未经统计校准。"
        }
        if method == "jev" {
            return "Jev · \(strategy.rawValue) · 策略置信度 \(Self.percent(confidence))"
        }
        return "DeepSeek · \(strategy.rawValue) · 模型自评 \(Self.percent(confidence))\n策略 token 权重暂不可用，保留证据判断。"
    }
    static func percent(_ value: Double?) -> String {
        value.map { String(format: "%.0f%%", $0 * 100) } ?? "暂不可用"
    }
}

struct Advice: Codable, Equatable {
    var support: String
    var intent: String
    var intentConfidence: Double?
    var facts: [String]
    var hypotheses: [String]
    var unknowns: [String]
    var strategy: Strategy
    var recommendation: String
    var nextStep: String
    var stopCondition: String
    var question: String
    var candidates: [Candidate]
    var decision: Decision?
    var rankingStatus = "unavailable"

    var confidenceLabel: String { "判断把握 · \(Decision.percent(intentConfidence))（模型估计）" }
    static let weightNote = "百分比是本轮候选的相对推荐权重，合计 100%；不代表回复成功率。"
    static let intentNote = "意图把握是模型自评，未经统计校准；不能当作对方真实意图的已验证概率。"
}

enum ModelJSON {
    /// Accept a whole JSON object or one complete fenced block, never splice prose or multiple objects.
    static func object(_ raw: String) throws -> [String: Any] {
        var text = raw.trimmed
        if text.hasPrefix("```") {
            var lines = text.components(separatedBy: .newlines)
            guard ["```json", "```"].contains(lines.first?.lowercased() ?? ""), lines.last == "```", lines.count >= 3 else {
                throw GoutouError.invalid("模型未返回完整 JSON；请重试")
            }
            lines.removeFirst(); lines.removeLast()
            text = lines.joined(separator: "\n")
        }
        guard text.utf8.count <= 256_000,
              let object = try? JSONSerialization.jsonObject(with: Data(text.utf8)) as? [String: Any] else {
            throw GoutouError.invalid("模型返回格式不正确；请重试")
        }
        return object
    }

    static func string(_ object: [String: Any], _ key: String, limit: Int = 300) throws -> String {
        guard let value = object[key] as? String, value.count <= limit else {
            throw GoutouError.invalid("模型分析缺少字段或文字过长：\(key)")
        }
        return value.trimmed
    }
    static func number(_ raw: Any?) -> Double? {
        guard let value = raw as? NSNumber, CFGetTypeID(value) != CFBooleanGetTypeID(), value.doubleValue.isFinite else { return nil }
        return value.doubleValue
    }
    static func confidence(_ raw: Any?) throws -> Double? {
        if raw == nil || raw is NSNull { return nil }
        guard let value = number(raw), (0...1).contains(value) else {
            throw GoutouError.invalid("模型判断把握必须为 0–1 数字或 null")
        }
        return value
    }
    static func rows(_ raw: Any?) throws -> [String] {
        if raw == nil || raw is NSNull { return [] }
        let values: [Any]
        if let value = raw as? String { values = [value] }
        else if let value = raw as? [Any] { values = value }
        else if let value = raw as? [String: Any], Set(value.keys) == ["text"] { values = [value] }
        else { throw GoutouError.invalid("模型证据格式不正确；请重试") }
        guard values.count <= 20 else { throw GoutouError.invalid("模型证据过多") }
        return try values.compactMap { item in
            let row: String?
            if let object = item as? [String: Any], Set(object.keys) == ["text"] { row = object["text"] as? String }
            else { row = item as? String }
            guard let row = row, row.count <= 500 else { throw GoutouError.invalid("模型证据格式不正确；请重试") }
            return row.trimmed.isEmpty ? nil : row.trimmed
        }
    }
    static func candidates(_ raw: Any?, config: AppConfig) throws -> [Candidate] {
        guard let values = raw as? [[String: Any]], values.count <= config.count else {
            throw GoutouError.invalid("模型候选数量不正确")
        }
        var seen = Set<String>()
        return try values.map { value in
            let text = try string(value, "text", limit: config.maxCharacters)
            guard !text.isEmpty, seen.insert(text).inserted else { throw GoutouError.invalid("候选为空或重复，请重试") }
            return Candidate(text: text, reason: try string(value, "reason"), tradeoff: try string(value, "tradeoff"))
        }
    }
    static func advice(_ raw: String, config: AppConfig, decision: Decision) throws -> Advice {
        let data = try object(raw)
        guard let name = data["strategy"] as? String, let strategy = Strategy(rawValue: name), strategy == decision.strategy else {
            throw GoutouError.invalid("回复模型未遵循已选策略；未展示候选")
        }
        let facts = try rows(data["facts"])
        let intent = try string(data, "intent", limit: 80)
        let confidence = try confidence(data["intent_confidence"])
        guard !intent.isEmpty, confidence == nil || (!facts.isEmpty && !intent.contains("无法判断") && !intent.contains("证据不足")) else {
            throw GoutouError.invalid("证据不足时不能给出意图把握")
        }
        let candidates = try candidates(data["candidates"], config: config)
        if decision.evidence.boundary == "explicit_refusal" && (strategy != .stop || !candidates.isEmpty) {
            throw GoutouError.invalid("已识别停止联系的边界；本轮不生成推进候选")
        }
        return Advice(support: try string(data, "support"), intent: intent, intentConfidence: confidence,
                      facts: facts, hypotheses: try rows(data["hypotheses"]), unknowns: try rows(data["unknowns"]),
                      strategy: strategy, recommendation: try string(data, "recommendation"),
                      nextStep: try string(data, "next_step"), stopCondition: try string(data, "stop_condition"),
                      question: try string(data, "question"), candidates: candidates, decision: decision)
    }
    static func json(_ value: Any) throws -> String {
        guard let text = String(data: try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]), encoding: .utf8) else {
            throw GoutouError.invalid("无法整理本轮输入")
        }
        return text
    }
}

extension String { var trimmed: String { trimmingCharacters(in: .whitespacesAndNewlines) } }
